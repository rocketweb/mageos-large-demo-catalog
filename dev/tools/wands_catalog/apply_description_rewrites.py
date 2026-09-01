#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply completed oMLX or Kimi description records to import CSV copies.")
    parser.add_argument("--descriptions", required=True, type=Path, help="Generated JSON Lines descriptions.")
    parser.add_argument("--configurable-parents", required=True, type=Path, help="Generated configurable parent CSV.")
    parser.add_argument("--bundles", required=True, type=Path, help="Generated bundle CSV.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for rewritten CSV files.")
    parser.add_argument("--allow-partial", action="store_true", help="Keep deterministic copy when a rewrite is missing.")
    return parser.parse_args()


def load_descriptions(path: Path) -> dict[str, str]:
    descriptions: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("status") != "success":
                continue
            record_id = str(record.get("id", ""))
            description = record.get("description")
            if not record_id or not isinstance(description, str) or not description.strip():
                raise ValueError(f"Invalid successful description on line {line_number}")
            descriptions[record_id] = description.strip()
    return descriptions


def plain_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def rewrite_csv(source: Path, target: Path, descriptions: dict[str, str], allow_partial: bool) -> dict[str, int]:
    with source.open("r", encoding="utf-8", newline="") as source_stream:
        reader = csv.DictReader(source_stream)
        fields = reader.fieldnames
        if fields is None or "sku" not in fields or "description" not in fields:
            raise ValueError(f"{source} is not a product import CSV")
        rows = list(reader)

    missing = [row["sku"] for row in rows if row["sku"] not in descriptions]
    if missing and not allow_partial:
        raise ValueError(f"Missing {len(missing)} descriptions, beginning with {missing[0]}")
    rewritten = 0
    for row in rows:
        description = descriptions.get(row["sku"])
        if description is None:
            continue
        text = plain_text(description)
        row["description"] = description
        row["short_description"] = text[:252].rstrip() + ("..." if len(text) > 252 else "")
        row["meta_description"] = text[:255]
        rewritten += 1

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as target_stream:
        writer = csv.DictWriter(target_stream, fieldnames=fields, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(target)
    return {"rows": len(rows), "rewritten": rewritten, "missing": len(missing)}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    arguments = parse_args()
    descriptions = load_descriptions(arguments.descriptions)
    parent_target = arguments.output_dir / "configurable-parents.rewritten.csv"
    bundle_target = arguments.output_dir / "bundles.rewritten.csv"
    parent_result = rewrite_csv(
        arguments.configurable_parents,
        parent_target,
        descriptions,
        arguments.allow_partial,
    )
    bundle_result = rewrite_csv(arguments.bundles, bundle_target, descriptions, arguments.allow_partial)
    result = {
        "descriptions": len(descriptions),
        "configurable_parents": parent_result,
        "bundles": bundle_result,
        "configurable_parents_sha256": file_hash(parent_target),
        "bundles_sha256": file_hash(bundle_target),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
