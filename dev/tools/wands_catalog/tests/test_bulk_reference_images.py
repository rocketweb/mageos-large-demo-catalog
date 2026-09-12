import copy
import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_reference_images as auditor
from bulk_reference_images import apply_repairs, eligible_jobs, write_once
from generate_reference_images import fingerprint
from prepare_catalog import sha256
from repair_reference_images import CONFIG, prepare


class BulkReferenceTest(unittest.TestCase):
    def fixture(self):
        jobs = [{"sku": "variant", "reference_images": [{"path": "a.jpg", "sha256": "a"}]},
                {"sku": "bundle", "reference_images": [{"path": "a.jpg", "sha256": "a"}, {"path": "b.jpg", "sha256": "b"}]}]
        work = [{"path": "a.jpg", "image_sha256": "a", "evidence_sha256": "source-a"},
                {"path": "b.jpg", "image_sha256": "b", "evidence_sha256": "source-b"}]
        record = {**work[0], "model": "vision", "audit_version": auditor.AUDIT_VERSION,
                  "system_sha256": hashlib.sha256(auditor.SYSTEM.encode()).hexdigest(),
                  "status": "audited", "approved": True, "verdict": "pass", "confidence": .95,
                  "observed_product": "A chair", "issues": [], "completion": {"finish_reason": "stop"}}
        return jobs, work, record

    def test_bundle_requires_every_component_approved(self):
        jobs, work, record = self.fixture()
        accepted, withheld = eligible_jobs(jobs, work, [record], "vision")
        self.assertEqual([j["sku"] for j in accepted], ["variant"])
        self.assertEqual(withheld, [{"sku": "bundle", "unapproved_references": ["b.jpg"]}])

    def test_stale_or_low_confidence_audit_never_authorizes_generation(self):
        jobs, work, record = self.fixture()
        for patch in ({"image_sha256": "stale"}, {"evidence_sha256": "stale"}, {"model": "other"},
                      {"audit_version": "old"}, {"confidence": .1}, {"issues": ["missing part"]},
                      {"completion": {"finish_reason": "length"}}):
            with self.subTest(patch=patch):
                self.assertEqual(eligible_jobs(jobs, work, [{**record, **patch}], "vision")[0], [])

    def test_later_failure_revokes_earlier_approval(self):
        jobs, work, record = self.fixture()
        records = [record, {**record, "approved": False, "verdict": "fail"}]
        self.assertEqual(eligible_jobs(jobs, work, records, "vision")[0], [])

    def test_immutable_inputs_cannot_be_replaced_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.jsonl"
            write_once(path, "original")
            write_once(path, "original")
            with self.assertRaises(ValueError):
                write_once(path, "changed")
            self.assertEqual(path.read_text(), "original")

    def test_repair_manifest_is_bound_to_source_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.tsv"
            row = {"product_id": "1", "product_name": "Table", "product_class": "Coffee Tables", "product_features": "shape:octagon"}
            with source.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, row.keys(), delimiter="\t")
                writer.writeheader()
                writer.writerow(row)
            plan = [{"product_id": "1", "evidence_sha256": hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest(), "prompt": "Octagon table", "seed": 1}]
            repairs = prepare(plan, source, root)
            self.assertEqual(repairs[0]["output_file"], "WANDS-000001.jpg")
            with self.assertRaises(ValueError):
                prepare(plan * 2, source, root)
            with self.assertRaises(ValueError):
                prepare([{**plan[0], "evidence_sha256": "changed"}], source, root)

    def test_overlay_preserves_originals_and_rejects_untracked_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "WANDS-000001.jpg"
            image.write_bytes(b"repaired image")
            repair = {"product_id": "1", "output_file": image.name, "seed": 1, "prompt": "An octagonal table"}
            jobs = [{"sku": "a", "prompt": "Edit table", "reference_images": [{"path": "/original/WANDS-000001.jpg", "sha256": "original"}]}]
            snapshot = copy.deepcopy(jobs)
            with self.assertRaises(ValueError):
                apply_repairs(jobs, [repair], root)

            record = {"status": "generated", "output_file": image.name, "request_sha256": fingerprint(repair, CONFIG), "image_sha256": sha256(image)}
            (root / "generation-events.jsonl").write_text(json.dumps(record) + "\n")
            result = apply_repairs(jobs, [repair], root)
            self.assertEqual(jobs, snapshot)
            self.assertEqual(result[0]["reference_images"][0]["path"], str(image.resolve()))
            image.write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                apply_repairs(jobs, [repair], root)

    def test_bundle_prompt_preserves_reviewed_lamp_pair_count(self):
        from bulk_reference_images import bundle_prompt
        refs = [{"path": "/repairs/WANDS-017261.jpg", "role": "Accent Light"},
                {"path": "/original/WANDS-017873.jpg", "role": "Rug"}]
        prompt = bundle_prompt(refs)
        self.assertIn("TWO matching table lamps", prompt)
        self.assertIn("both lamps", prompt)
        self.assertNotIn("Show every referenced item once", prompt)


if __name__ == "__main__":
    unittest.main()
