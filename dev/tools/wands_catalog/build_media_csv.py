#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Magento media update CSV for completed WANDS images.")
    parser.add_argument("--prompts", required=True, type=Path)
    parser.add_argument("--image-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    missing = 0
    with arguments.prompts.open("r", encoding="utf-8") as prompt_stream, arguments.output.open(
        "w", encoding="utf-8", newline=""
    ) as output_stream:
        writer = csv.DictWriter(output_stream, fieldnames=["sku", "base_image", "small_image", "thumbnail"])
        writer.writeheader()
        for line in prompt_stream:
            prompt = json.loads(line)
            image_path = arguments.image_dir / prompt["output_file"]
            if not image_path.is_file():
                missing += 1
                continue
            relative_path = f"/wands/{prompt['output_file']}"
            writer.writerow(
                {
                    "sku": prompt["sku"],
                    "base_image": relative_path,
                    "small_image": relative_path,
                    "thumbnail": relative_path,
                }
            )
            written += 1
    print(json.dumps({"media_rows": written, "missing_images": missing}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
