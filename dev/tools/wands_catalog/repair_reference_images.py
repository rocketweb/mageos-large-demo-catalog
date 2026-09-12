#!/usr/bin/env python3
"""Regenerate explicitly reviewed reference defects with local MFLUX, quietly."""
import argparse
import csv
import fcntl
import hashlib
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

from audit_reference_images import append_audit
from generate_images import load_model
from generate_reference_images import completed, fingerprint, safe_target
from prepare_catalog import sha256

CONFIG = {"model": "flux2-klein-4b", "quantize": 4, "width": 768, "height": 768, "steps": 4}


def prepare(plan, source_path, output_dir):
    with source_path.open(newline="") as stream:
        source = {r["product_id"]: r for r in csv.DictReader(stream, delimiter="\t")}
    seen, jobs = set(), []
    for repair in plan:
        product_id = repair["product_id"]
        if not isinstance(product_id, str) or not product_id.isdigit() or product_id not in source:
            raise ValueError("Unknown repair product ID")
        if product_id in seen:
            raise ValueError("Duplicate repair product ID")
        seen.add(product_id)
        facts = {k: source[product_id][k] for k in ("product_id", "product_name", "product_class", "product_features")}
        if hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest() != repair["evidence_sha256"]:
            raise ValueError("Repair source evidence changed; review prompt before regeneration")
        if not isinstance(repair.get("prompt"), str) or not repair["prompt"].strip():
            raise ValueError("A reviewed repair prompt is required")
        job = {**repair, "output_file": f"WANDS-{int(product_id):06d}.jpg"}
        safe_target(output_dir, job["output_file"])
        jobs.append(job)
    return jobs


def run(args):
    jobs = prepare(json.loads(args.plan.read_text()), args.source_products, args.output_dir)
    events = args.output_dir / "generation-events.jsonl"
    done = completed(events)
    pending = []
    for job in jobs:
        target = safe_target(args.output_dir, job["output_file"])
        if target.exists():
            record = done.get(target.name, {})
            if record.get("request_sha256") != fingerprint(job, CONFIG) or record.get("image_sha256") != sha256(target):
                raise ValueError("Stale or untracked repair output; use a new versioned directory")
        else:
            pending.append(job)
    logging.info("Repair queue: %d total, %d pending", len(jobs), len(pending))
    if not pending or args.dry_run:
        return
    model = load_model(CONFIG["model"], CONFIG["quantize"])
    for job in pending:
        started = time.monotonic()
        output = model.generate_image(seed=int(job["seed"]), prompt=job["prompt"], width=768, height=768,
                                      guidance=1.0, num_inference_steps=4)
        target = safe_target(args.output_dir, job["output_file"])
        with tempfile.NamedTemporaryFile(dir=args.output_dir, suffix=".jpg") as temp:
            output.image.convert("RGB").save(temp.name, format="JPEG", quality=92)
            with open(temp.name, "rb") as stream:
                os.fsync(stream.fileno())
            os.link(temp.name, target)
        append_audit(events, {"status": "generated", "output_file": target.name,
                             "request_sha256": fingerprint(job, CONFIG), "image_sha256": sha256(target),
                             "source_evidence_sha256": job["evidence_sha256"], "prompt": job["prompt"],
                             "config": CONFIG, "visual_acceptance": "pending"})
        logging.info("Generated repair %s in %.1fs; acceptance pending", target.name, time.monotonic() - started)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--source-products", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "generation.log").open("a", buffering=1) as log, (args.output_dir / ".generation.lock").open("a") as lock:
        os.dup2(log.fileno(), sys.stdout.fileno())
        os.dup2(log.fileno(), sys.stderr.fileno())
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(args)
            return 0
        except Exception:
            logging.exception("Reference repair stopped; originals unchanged")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
