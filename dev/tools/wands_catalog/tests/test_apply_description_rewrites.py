from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apply_description_rewrites import load_descriptions, rewrite_csv


class ApplyDescriptionRewritesTest(unittest.TestCase):
    def test_rewrites_copy_and_fails_closed_when_a_sku_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            descriptions_path = root / "descriptions.jsonl"
            descriptions_path.write_text(
                json.dumps(
                    {
                        "id": "SKU-1",
                        "status": "success",
                        "description": "<p>New product copy.</p><p>Choose the right size.</p>",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            source = root / "source.csv"
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=["sku", "description", "short_description", "meta_description"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "sku": "SKU-1",
                        "description": "Old",
                        "short_description": "Old",
                        "meta_description": "Old",
                    }
                )
                writer.writerow(
                    {
                        "sku": "SKU-2",
                        "description": "Keep",
                        "short_description": "Keep",
                        "meta_description": "Keep",
                    }
                )

            descriptions = load_descriptions(descriptions_path)
            with self.assertRaises(ValueError):
                rewrite_csv(source, root / "strict.csv", descriptions, allow_partial=False)

            result = rewrite_csv(source, root / "partial.csv", descriptions, allow_partial=True)
            self.assertEqual(result, {"rows": 2, "rewritten": 1, "missing": 1})
            with (root / "partial.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["description"], "<p>New product copy.</p><p>Choose the right size.</p>")
            self.assertEqual(rows[1]["description"], "Keep")


if __name__ == "__main__":
    unittest.main()
