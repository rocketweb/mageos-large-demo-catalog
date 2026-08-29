from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sync_generated_media import completed_rows


class SyncGeneratedMediaTest(unittest.TestCase):
    def test_only_returns_completed_files_not_already_imported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompts = root / "prompts.jsonl"
            images = root / "images"
            images.mkdir()
            prompt_rows = [
                {"sku": "WANDS-000001", "output_file": "WANDS-000001.jpg"},
                {"sku": "WANDS-000002", "output_file": "WANDS-000002.jpg"},
                {"sku": "WANDS-000003", "output_file": "WANDS-000003.jpg"},
            ]
            prompts.write_text(
                "".join(json.dumps(row) + "\n" for row in prompt_rows),
                encoding="utf-8",
            )
            (images / "WANDS-000001.jpg").touch()
            (images / "WANDS-000002.jpg").touch()

            rows = completed_rows(prompts, images, {"WANDS-000001.jpg"}, 500)

            self.assertEqual(rows, [
                {
                    "sku": "WANDS-000002",
                    "base_image": "/wands/WANDS-000002.jpg",
                    "small_image": "/wands/WANDS-000002.jpg",
                    "thumbnail": "/wands/WANDS-000002.jpg",
                }
            ])
