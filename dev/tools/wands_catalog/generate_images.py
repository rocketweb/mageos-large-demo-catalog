#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Iterator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate resumable WANDS product images with MFLUX.")
    parser.add_argument("--prompts", required=True, type=Path, help="Prepared image-prompts.jsonl file.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Magento media import directory.")
    parser.add_argument("--model", default="flux2-klein-4b", help="MFLUX model alias.")
    parser.add_argument("--quantize", default=4, type=int, choices=(3, 4, 5, 6, 8))
    parser.add_argument("--width", default=768, type=int)
    parser.add_argument("--height", default=768, type=int)
    parser.add_argument("--steps", default=4, type=int)
    parser.add_argument("--quality", default=88, type=int)
    parser.add_argument("--start-index", default=0, type=int, help="Zero-based queue position to begin at.")
    parser.add_argument("--limit", type=int, help="Maximum queue rows to inspect after start-index.")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate images that already exist.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect the selected queue without loading a model.")
    return parser.parse_args()


def queue_rows(path: Path, start_index: int, limit: int | None) -> Iterator[tuple[int, dict[str, Any]]]:
    selected = 0
    with path.open("r", encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            if index < start_index:
                continue
            if limit is not None and selected >= limit:
                break
            yield index, json.loads(line)
            selected += 1


def load_model(model_name: str, quantize: int):
    from mflux.models.common.config.model_config import ModelConfig

    if model_name.startswith("z-image"):
        from mflux.models.z_image.variants import ZImage

        return ZImage(model_config=ModelConfig.from_name(model_name), quantize=quantize)

    from mflux.models.flux2.variants import Flux2Klein

    return Flux2Klein(model_config=ModelConfig.from_name(model_name), quantize=quantize)


def append_event(path: Path, event: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def save_image_atomic(image, output_path: Path, quality: int) -> None:
    temporary_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    if output_path.suffix.lower() in (".jpg", ".jpeg"):
        image.convert("RGB").save(
            temporary_path,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )
    else:
        image.save(temporary_path, format="WEBP", quality=quality, method=6)
    os.replace(temporary_path, output_path)


def main() -> int:
    arguments = parse_args()
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = arguments.output_dir / "generation-events.jsonl"
    selected_rows = list(queue_rows(arguments.prompts, arguments.start_index, arguments.limit))
    pending_rows = [
        (index, row)
        for index, row in selected_rows
        if arguments.overwrite or not (arguments.output_dir / row["output_file"]).is_file()
    ]

    if arguments.dry_run:
        print(
            json.dumps(
                {
                    "selected": len(selected_rows),
                    "pending": len(pending_rows),
                    "already_complete": len(selected_rows) - len(pending_rows),
                    "model": arguments.model,
                    "quantize": arguments.quantize,
                    "width": arguments.width,
                    "height": arguments.height,
                    "steps": arguments.steps,
                },
                indent=2,
            )
        )
        return 0

    if not pending_rows:
        print(json.dumps({"generated": 0, "skipped": len(selected_rows), "failed": 0}, indent=2))
        return 0

    model_started = time.monotonic()
    model = load_model(arguments.model, arguments.quantize)
    model_load_seconds = round(time.monotonic() - model_started, 2)
    generated = 0
    failed = 0

    for queue_index, row in pending_rows:
        output_path = arguments.output_dir / row["output_file"]
        started = time.monotonic()
        try:
            generated_image = model.generate_image(
                seed=int(row["seed"]),
                prompt=str(row["prompt"]),
                width=arguments.width,
                height=arguments.height,
                guidance=1.0,
                num_inference_steps=arguments.steps,
            )
            save_image_atomic(generated_image.image, output_path, arguments.quality)
            event = {
                "status": "generated",
                "queue_index": queue_index,
                "sku": row["sku"],
                "output_file": row["output_file"],
                "seed": int(row["seed"]),
                "model": arguments.model,
                "quantize": arguments.quantize,
                "width": arguments.width,
                "height": arguments.height,
                "steps": arguments.steps,
                "seconds": round(time.monotonic() - started, 2),
            }
            generated += 1
        except Exception as exception:  # noqa: BLE001
            event = {
                "status": "failed",
                "queue_index": queue_index,
                "sku": row.get("sku"),
                "output_file": row.get("output_file"),
                "error_type": type(exception).__name__,
                "error": str(exception),
                "seconds": round(time.monotonic() - started, 2),
            }
            failed += 1
        append_event(progress_path, event)
        print(json.dumps(event, ensure_ascii=False), flush=True)

    print(
        json.dumps(
            {
                "generated": generated,
                "skipped": len(selected_rows) - len(pending_rows),
                "failed": failed,
                "model_load_seconds": model_load_seconds,
            },
            indent=2,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
