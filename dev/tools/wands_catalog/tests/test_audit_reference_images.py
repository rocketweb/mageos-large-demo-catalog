import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_reference_images as module
from prepare_catalog import sha256


VALID = json.dumps({"verdict": "pass", "confidence": .95,
                    "observed_product": "A chair", "issues": []})


def response(content=VALID, finish="stop"):
    return io.StringIO(json.dumps({"choices": [{"finish_reason": finish,
                                               "message": {"content": content}}]}))


class AuditReferenceTest(unittest.TestCase):
    def run_audit(self, root, replies):
        image = root / "WANDS-000001.jpg"
        image.write_bytes(b"fixture")
        source = root / "source.tsv"
        source.write_text("product_id\tproduct_name\tproduct_class\tproduct_features\n1\tChair\tChairs\t\n")
        jobs = root / "jobs.jsonl"
        jobs.write_text(json.dumps({"reference_images": [{"path": str(image), "sha256": sha256(image)}]}) + "\n")
        args = Namespace(jobs=jobs, source_products=source, output=root / "audit.jsonl",
                         model="fixture-vision", limit=1, env_file=None, reference_id=None)
        with patch.dict(os.environ, {"OMLX_API_KEY": "test-only"}), \
                patch.object(module.urllib.request, "urlopen", side_effect=replies) as request:
            result = module.audit(args)
        return result, request

    def test_length_finish_is_retried_even_with_parseable_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, request = self.run_audit(root, [response(finish="length"), response()])
            self.assertEqual(request.call_count, 2)
            payloads = [json.loads(call.args[0].data) for call in request.call_args_list]
            self.assertGreater(payloads[1]["max_tokens"], payloads[0]["max_tokens"])
            self.assertEqual(result["approved_this_run"], 1)
            self.assertEqual(len((root / "audit.jsonl").read_text().splitlines()), 1)

    def test_repeated_truncation_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "incomplete|invalid"):
                self.run_audit(root, [response(finish="length"), response(finish="length")])
            self.assertFalse((root / "audit.jsonl").exists())

    def test_malformed_json_is_retried_once(self):
        with tempfile.TemporaryDirectory() as directory:
            result, request = self.run_audit(Path(directory), [response('{"verdict":"pass'), response()])
            self.assertEqual(request.call_count, 2)
            self.assertEqual(result["audited_this_run"], 1)

    def test_filtered_response_cannot_approve(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                self.run_audit(root, [response(finish="content_filter"), response(finish="content_filter")])
            self.assertFalse((root / "audit.jsonl").exists())

    def test_non_object_verdict_rejected_cleanly(self):
        with self.assertRaises(ValueError):
            module.parse_verdict("[]")

    def test_model_cannot_replace_pinned_reference_identity(self):
        value = json.loads(VALID)
        value.update(path="different.jpg", image_sha256="forged", source={})
        verdict = module.parse_verdict(json.dumps(value))
        self.assertEqual(set(verdict), {"verdict", "confidence", "observed_product", "issues", "approved"})

    def test_interrupted_final_record_does_not_swallow_resumed_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "audit.jsonl"
            output.write_text('{"status":"aud')
            self.run_audit(root, [response()])
            _, requests = self.run_audit(root, [])
            self.assertEqual(requests.call_count, 0)
            self.assertTrue(output.read_text().startswith('{"status":"aud\n'))

    def test_cli_failure_is_quiet_and_key_is_absent_from_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = root / ".env"
            env.write_text('OMLX-KEY="private-test-value${invalid}"\n')
            result = subprocess.run([sys.executable, str(Path(module.__file__)),
                                     "--jobs", str(root / "missing"),
                                     "--source-products", str(root / "missing"),
                                     "--output", str(root / "audit.jsonl"),
                                     "--env-file", str(env), "--model", "fixture"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout + result.stderr, "")
            log = (root / "audit.log").read_text()
            self.assertIn("Invalid OMLX-KEY format", log)
            self.assertNotIn("private-test-value", log)

    def test_explicit_env_file_reads_only_named_key_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text("UNRELATED=$(touch /do-not-execute)\nOMLX-KEY='test-key' # comment\n")
            with patch.dict(os.environ, {"OMLX_API_KEY": "stale"}):
                self.assertEqual(module.load_api_key(env), "test-key")
                self.assertEqual(os.environ["OMLX_API_KEY"], "stale")

    def test_duplicate_or_interpolated_key_fails_without_value_in_error(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            for value in ("OMLX-KEY=first-secret\nOMLX-KEY=second-secret\n", "OMLX-KEY=${secret}\n"):
                env.write_text(value)
                with self.assertRaises(ValueError) as raised:
                    module.load_api_key(env)
                self.assertNotIn("secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
