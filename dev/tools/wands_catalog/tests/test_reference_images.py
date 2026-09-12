import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generate_reference_images import fingerprint, safe_target, pending_jobs, require_approved_references
from audit_reference_images import parse_verdict
from prepare_catalog import sha256


class ReferenceImagesTest(unittest.TestCase):
    def test_uncertain_model_verdict_cannot_approve_reference(self):
        value = parse_verdict(json.dumps({"verdict": "pass", "confidence": .8, "observed_product": "chair", "issues": []}))
        self.assertFalse(value["approved"])
        value = parse_verdict(json.dumps({"verdict": "pass", "confidence": .99, "observed_product": "chair", "issues": ["Missing lamp"]}))
        self.assertFalse(value["approved"])

    def test_generation_requires_exact_reference_hash_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            jobs = [{"reference_images": [{"path": "A.jpg", "sha256": "new"}]}]
            path.write_text(json.dumps({"path": "A.jpg", "image_sha256": "old", "approved": True}) + "\n")
            with self.assertRaises(ValueError):
                require_approved_references(jobs, path)
            with self.assertRaises(ValueError):
                require_approved_references(jobs, None)
            path.write_text(json.dumps({"path": "A.jpg", "image_sha256": "new", "approved": True}) + "\n")
            require_approved_references(jobs, path)

    def test_paths_cannot_escape_output(self):
        for filename in ("../x.jpg", "/x.jpg", "x.png"):
            with self.assertRaises(ValueError):
                safe_target(Path("/tmp/out"), filename)

    def test_request_hash_covers_prompt_and_dimensions(self):
        self.assertNotEqual(fingerprint({"prompt": "a"}, {}), fingerprint({"prompt": "b"}, {}))
        self.assertNotEqual(fingerprint({}, {"width": 768}), fingerprint({}, {"width": 1024}))

    def test_resume_requires_matching_request_and_image_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            job = {"output_file": "x.jpg", "reference_images": [{"path": str(reference), "sha256": sha256(reference)}]}
            self.assertEqual(pending_jobs([job], root, {}), [job])
            (root / "x.jpg").write_bytes(b"generated")
            with self.assertRaises(ValueError):
                pending_jobs([job], root, {})
            record = {"status": "generated", "output_file": "x.jpg", "request_sha256": fingerprint(job, {}), "image_sha256": sha256(root / "x.jpg")}
            (root / "generation-events.jsonl").write_text(json.dumps(record) + "\n")
            self.assertEqual(pending_jobs([job], root, {}), [])
            with self.assertRaises(ValueError):
                pending_jobs([job], root, {"steps": 8})
            reference.write_bytes(b"modified")
            with self.assertRaises(ValueError):
                pending_jobs([job], root, {})


if __name__ == "__main__":
    unittest.main()
