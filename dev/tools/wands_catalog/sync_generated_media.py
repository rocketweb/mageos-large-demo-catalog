#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
import subprocess
from pathlib import Path
from typing import Any

MEDIA_FIELDS = ["sku", "base_image", "small_image", "thumbnail"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Attach newly generated WANDS images in resumable batches.")
    parser.add_argument("--project", required=True, type=Path, help="Mage-OS project root.")
    parser.add_argument("--prompts", required=True, type=Path)
    parser.add_argument("--image-dir", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--php", default="php", help="PHP executable used for bin/magento.")
    parser.add_argument("--batch-size", default=500, type=int)
    return parser.parse_args()


def load_state(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    state = json.loads(path.read_text(encoding="utf-8"))
    return set(state.get("imported_files", []))


def completed_rows(
    prompts_path: Path,
    image_dir: Path,
    imported_files: set[str],
    batch_size: int,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with prompts_path.open("r", encoding="utf-8") as prompt_stream:
        for line in prompt_stream:
            prompt: dict[str, Any] = json.loads(line)
            output_file = str(prompt["output_file"])
            if output_file in imported_files or not (image_dir / output_file).is_file():
                continue
            relative_path = f"/wands/{output_file}"
            skus = [str(sku) for sku in prompt.get("skus", [prompt["sku"]])]
            if len(skus) > batch_size:
                raise ValueError(
                    f"Image {output_file} maps to {len(skus)} products, exceeding batch size {batch_size}."
                )
            if rows and len(rows) + len(skus) > batch_size:
                break
            for sku in skus:
                rows.append(
                    {
                        "sku": sku,
                        "base_image": relative_path,
                        "small_image": relative_path,
                        "thumbnail": relative_path,
                    }
                )
            if len(rows) >= batch_size:
                break
    return rows


def write_csv_atomic(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp")
    with temporary_path.open("w", encoding="utf-8", newline="") as output_stream:
        writer = csv.DictWriter(output_stream, fieldnames=MEDIA_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        output_stream.flush()
        os.fsync(output_stream.fileno())
    os.replace(temporary_path, path)


def save_state_atomic(path: Path, imported_files: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp")
    temporary_path.write_text(
        json.dumps({"imported_files": sorted(imported_files)}, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def main() -> int:
    arguments = parse_args()
    lock_path = arguments.state.with_suffix(f"{arguments.state.suffix}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a+", encoding="utf-8") as lock_stream:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status": "skipped", "reason": "sync already running"}))
            return 0

        imported_files = load_state(arguments.state)
        rows = completed_rows(
            arguments.prompts,
            arguments.image_dir,
            imported_files,
            arguments.batch_size,
        )
        if not rows:
            print(json.dumps({"status": "idle", "new_images": 0, "imported_total": len(imported_files)}))
            return 0

        write_csv_atomic(arguments.output, rows)
        relative_csv = arguments.output.resolve().relative_to(arguments.project.resolve())
        command = [
            arguments.php,
            "bin/magento",
            "lab:wands:import",
            f"--file={relative_csv}",
        ]
        result = subprocess.run(
            command,
            cwd=arguments.project,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip())
        if result.returncode != 0:
            print(json.dumps({"status": "failed", "exit_code": result.returncode, "new_images": len(rows)}))
            return result.returncode

        imported_files.update(Path(row["base_image"]).name for row in rows)
        save_state_atomic(arguments.state, imported_files)
        print(
            json.dumps(
                {
                    "status": "imported",
                    "new_images": len(rows),
                    "imported_total": len(imported_files),
                }
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
