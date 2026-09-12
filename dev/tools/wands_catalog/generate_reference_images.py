#!/usr/bin/env python3
"""Quiet, resumable local MFLUX reference edits. Never replace original media."""
import argparse
import fcntl
import hashlib
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

from prepare_catalog import sha256
from generate_images import append_event


def fingerprint(job, config):
    return hashlib.sha256(json.dumps({"job": job, "config": config}, sort_keys=True).encode()).hexdigest()


def safe_target(root, filename):
    if Path(filename).name != filename or not filename.lower().endswith(".jpg"):
        raise ValueError("Output must be a plain JPEG filename")
    path = root / filename
    if path.is_symlink():
        raise ValueError("Output symlinks are not allowed")
    return path


def completed(path):
    records = {}
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("status") == "generated":
                records[record["output_file"]] = record
    return records


def pending_jobs(jobs, root, config):
    records, pending, refs = completed(root / "generation-events.jsonl"), [], {}
    seen = set()
    for job in jobs:
        target = safe_target(root, job["output_file"])
        if target.name in seen:
            raise ValueError("Duplicate output filename")
        seen.add(target.name)
        if not job.get("reference_images"):
            raise ValueError("Reference editing requires an input image")
        for reference in job["reference_images"]:
            path = Path(reference["path"])
            if path not in refs:
                refs[path] = sha256(path)
            if refs[path] != reference["sha256"]:
                raise ValueError(f"Reference changed: {path.name}")
        record = records.get(target.name)
        if target.exists():
            if not record or record.get("request_sha256") != fingerprint(job, config):
                raise ValueError(f"Existing untracked or stale image: {target.name}; use a new output directory")
            if sha256(target) != record.get("image_sha256"):
                raise ValueError(f"Image content changed: {target.name}; use a new output directory")
            continue
        pending.append(job)
    return pending


def require_approved_references(jobs, audit_path):
    if audit_path is None:
        raise ValueError("An image-reference audit is required before bulk generation")
    decisions = {}
    for line in audit_path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        decisions[(record["path"], record["image_sha256"])] = record.get("approved") is True
    missing = {(r["path"], r["sha256"]) for job in jobs for r in job["reference_images"] if not decisions.get((r["path"], r["sha256"]), False)}
    if missing:
        raise ValueError(f"{len(missing)} references remain unapproved; repair or audit before generating")


def run(args):
    config = {"model": "flux2-klein-4b", "quantize": 4, "steps": args.steps, "width": args.width, "height": args.height}
    jobs = [json.loads(line) for line in args.jobs.read_text().splitlines() if line.strip()]
    if args.sku:
        requested = set(args.sku)
        jobs = [j for j in jobs if j["sku"] in requested]
        if {j["sku"] for j in jobs} != requested:
            raise ValueError("Requested SKU is absent from queue")
    pending = pending_jobs(jobs, args.output_dir, config)
    summary = {"selected": len(jobs), "already_complete": len(jobs) - len(pending), "pending": len(pending), "generated": 0, "failed": 0, "dry_run": args.dry_run}
    if args.dry_run or not pending:
        return summary
    if args.limit is not None:
        pending = pending[:args.limit]
    require_approved_references(pending, args.reference_audit)
    logging.info("Loading local reference model; %s jobs selected for this run", len(pending))
    from mflux.models.common.config.model_config import ModelConfig
    from mflux.models.flux2.variants import Flux2KleinEdit
    model = Flux2KleinEdit(model_config=ModelConfig.from_name(config["model"]), quantize=config["quantize"])
    events = args.output_dir / "generation-events.jsonl"
    for job in pending:
        target = safe_target(args.output_dir, job["output_file"])
        started = time.monotonic()
        try:
            # Recheck at the point of use, including long-running batches.
            for reference in job["reference_images"]:
                if sha256(Path(reference["path"])) != reference["sha256"]:
                    raise ValueError("Reference changed after preflight")
            output = model.generate_image(seed=int(job["seed"]), prompt=job["prompt"],
                                          image_paths=[Path(r["path"]) for r in job["reference_images"]],
                                          width=args.width, height=args.height, guidance=1.0, num_inference_steps=args.steps)
            with tempfile.NamedTemporaryFile(dir=args.output_dir, suffix=".jpg") as temp:
                output.image.convert("RGB").save(temp.name, format="JPEG", quality=90, optimize=True)
                with open(temp.name, "rb") as stream:
                    os.fsync(stream.fileno())
                # link is atomic and fails if a target appeared after preflight.
                os.link(temp.name, target)
            event = {"status": "generated", "sku": job["sku"], "output_file": target.name,
                     "request_sha256": fingerprint(job, config), "image_sha256": sha256(target),
                     "seconds": round(time.monotonic() - started, 2), "visual_acceptance": "pending", "config": config}
            append_event(events, event)
            summary["generated"] += 1
            logging.info("Generated %s (%ss)", job["sku"], event["seconds"])
        except Exception as exc:
            summary["failed"] += 1
            append_event(events, {"status": "failed", "sku": job["sku"], "error": str(exc)})
            logging.exception("Failed %s; stopping so a systematic failure cannot exhaust the queue", job["sku"])
            break
    summary["pending"] -= summary["generated"]
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sku", action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--reference-audit", type=Path)
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.width <= 0 or args.height <= 0 or args.width % 16 or args.height % 16 or args.steps <= 0:
        parser.error("Dimensions must be positive multiples of 16 and steps positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    saved_stdout = os.dup(sys.stdout.fileno())
    with (args.output_dir / "generation.log").open("a", buffering=1) as log, (args.output_dir / ".generation.lock").open("a") as lock:
        os.dup2(log.fileno(), sys.stdout.fileno())
        os.dup2(log.fileno(), sys.stderr.fileno())
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            summary = run(args)
            logging.info("Summary: %s", json.dumps(summary, sort_keys=True))
            if args.json:
                os.write(saved_stdout, (json.dumps(summary, indent=2) + "\n").encode())
            return int(summary["failed"] > 0)
        except Exception:
            logging.exception("Generation failed; original media unchanged")
            return 1
        finally:
            os.close(saved_stdout)


if __name__ == "__main__":
    raise SystemExit(main())
