from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_descriptions import completed_ids, normalize_description, request_payload


class GenerateDescriptionsTest(unittest.TestCase):
    def test_completed_ids_ignores_failed_and_truncated_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "descriptions.jsonl"
            path.write_text(
                json.dumps({"id": "A", "status": "success", "description": "<p>Done.</p>"})
                + "\n"
                + json.dumps({"id": "B", "status": "error", "error": "timeout"})
                + "\n"
                + '{"id":"truncated"',
                encoding="utf-8",
            )

            self.assertEqual(completed_ids(path), {"A"})

    def test_description_normalizer_requires_short_safe_html(self) -> None:
        self.assertEqual(
            normalize_description("```html\n<p>A useful product.</p>\n<p>Choose a size.</p>\n```"),
            "<p>A useful product.</p>\n<p>Choose a size.</p>",
        )
        with self.assertRaises(ValueError):
            normalize_description("<script>alert(1)</script><p>Product</p>")

    def test_request_payload_uses_openai_compatible_chat_contract(self) -> None:
        payload = request_payload("local-model", "Write the product description.")

        self.assertEqual(payload["model"], "local-model")
        self.assertEqual(payload["messages"][-1]["role"], "user")
        self.assertEqual(payload["messages"][-1]["content"], "Write the product description.")
        self.assertLessEqual(payload["max_tokens"], 500)


if __name__ == "__main__":
    unittest.main()
