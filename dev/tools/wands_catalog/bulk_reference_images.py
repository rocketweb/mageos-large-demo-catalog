#!/usr/bin/env python3
"""Quiet, resumable audit-gated bulk generation. Never publish generated media."""
import argparse
import csv
import fcntl
import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import audit_reference_images as auditor
from generate_reference_images import pending_jobs
from prepare_catalog import sha256
from repair_reference_images import CONFIG, prepare


def read_records(path):
    records = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def write_once(path, data):
    if path.exists():
        if path.read_text() != data:
            raise ValueError(f"Immutable run input changed: {path.name}; use a new run directory")
        return
    with path.open("x") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def apply_repairs(jobs, repairs, repair_dir):
    from generate_reference_images import completed, fingerprint
    records = completed(repair_dir / "generation-events.jsonl")
    replacements = {}
    for repair in repairs:
        path = repair_dir / repair["output_file"]
        record = records.get(path.name, {})
        if (record.get("request_sha256") != fingerprint(repair, CONFIG)
                or not path.is_file() or record.get("image_sha256") != sha256(path)):
            raise ValueError(f"Unverified generated repair file: {path.name}")
        replacements[path.stem] = {"path": str(path.resolve()), "sha256": sha256(path)}
    result = []
    for job in jobs:
        refs = [{**ref, **replacements.get(Path(ref["path"]).stem, {})} for ref in job["reference_images"]]
        updated = {**job, "reference_images": refs}
        if len(refs) > 1:
            updated["prompt"] = bundle_prompt(refs)
        result.append(updated)
    return result


def bundle_prompt(refs):
    # Reviewed identities/counts of the repaired components, bound to source facts
    # by prepare(). Other groups retain the exact count shown in their references.
    reviewed = {"WANDS-014081": "ONE light-brown two-seat loveseat",
                "WANDS-023338": "ONE light-gray octagonal coffee table",
                "WANDS-017261": "TWO matching table lamps, both lamps fully visible side by side",
                "WANDS-042963": "ONE tufted velvet desk chair"}
    groups = [f"Reference {index}: " + reviewed.get(Path(ref["path"]).stem,
              "the complete " + ref.get("role", "product") + " group exactly as pictured, including every piece")
              for index, ref in enumerate(refs, 1)]
    return ("Photorealistic studio product assortment photograph on a warm white seamless background. "
            "Required contents: " + "; ".join(groups) + ". "
            "Arrange all of these complete product groups together with generous spacing so every object is visible. "
            "Keep the exact shape, color, pattern and construction of every reference product. "
            "When a reference shows a pair or set, show the entire pair or set. No missing pieces, no extra products, "
            "no labels, no logos. This image depicts the default bundle selections only.")


def eligible_jobs(jobs, work, records, model):
    current = {(t["path"], t["image_sha256"]): t["evidence_sha256"] for t in work}
    decisions = {}
    for record in records:
        key = (record.get("path"), record.get("image_sha256"))
        if (key not in current or record.get("evidence_sha256") != current[key]
                or record.get("model") != model or record.get("audit_version") != auditor.AUDIT_VERSION
                or record.get("system_sha256") != hashlib.sha256(auditor.SYSTEM.encode()).hexdigest()):
            continue
        try:
            verdict = auditor.parse_verdict(json.dumps(record))
        except ValueError:
            decisions[key] = False
            continue
        decisions[key] = (record.get("status") == "audited" and record.get("approved") is True
                          and verdict["approved"]
                          and record.get("completion", {}).get("finish_reason") == "stop")
    accepted, withheld = [], []
    for job in jobs:
        missing = [r["path"] for r in job["reference_images"] if not decisions.get((r["path"], r["sha256"]), False)]
        if missing:
            withheld.append({"sku": job["sku"], "unapproved_references": missing})
        else:
            accepted.append(job)
    return accepted, withheld


def state(root, value):
    temp = root / "status.tmp"
    temp.write_text(json.dumps({"pid": os.getpid(), **value}, indent=2) + "\n")
    os.replace(temp, root / "status.json")


def run(args):
    root = args.run_dir
    repairs = prepare(json.loads(args.repair_plan.read_text()), args.source_products, args.repair_dir)
    jobs = apply_repairs([json.loads(line) for line in args.jobs.read_text().splitlines() if line.strip()], repairs, args.repair_dir)
    config = {"source_jobs_sha256": sha256(args.jobs), "source_products_sha256": sha256(args.source_products),
              "repair_plan_sha256": sha256(args.repair_plan), "model": args.model,
              "image_python": str(args.image_python.resolve()), "image_config": CONFIG,
              "audit_policy": auditor.AUDIT_VERSION,
              "tool_sha256": {name: sha256(Path(__file__).with_name(name)) for name in (
                  "bulk_reference_images.py", "audit_reference_images.py", "generate_reference_images.py", "repair_reference_images.py")}}
    write_once(root / "run-config.json", json.dumps(config, sort_keys=True, indent=2) + "\n")
    queue_path = root / "jobs.jsonl"
    write_once(queue_path, "".join(json.dumps(j, sort_keys=True) + "\n" for j in jobs))
    with args.source_products.open(newline="") as stream:
        source = {r["product_id"]: r for r in csv.DictReader(stream, delimiter="\t")}
    work = auditor.tasks(jobs, source)
    if args.prepare_only:
        state(root, {"status": "prepared", "jobs": len(jobs), "references": len(work)})
        return
    audit_path = root / "reference-audit.jsonl"
    media = root / "media"
    media.mkdir(exist_ok=True)
    audit_args = argparse.Namespace(jobs=queue_path, source_products=args.source_products, output=audit_path,
                                    model=args.model, env_file=args.env_file, reference_id=None, limit=args.audit_batch)
    done_auditing = False
    rounds = 0
    while True:
        accepted, withheld = eligible_jobs(jobs, work, read_records(audit_path), args.model)
        # Checks current file hashes even on resume; stale output never gets overwritten.
        pending = pending_jobs(accepted, media, CONFIG)
        state(root, {"status": "generating" if pending else "auditing", "total_jobs": len(jobs),
                     "eligible_jobs": len(accepted), "generated_jobs": len(accepted) - len(pending),
                     "withheld_jobs": len(withheld), "references": len(work)})
        if pending:
            data = "".join(json.dumps(j, sort_keys=True) + "\n" for j in accepted)
            selected = root / ("eligible-" + hashlib.sha256(data.encode()).hexdigest()[:16] + ".jsonl")
            write_once(selected, data)
            logging.info("Generating %d pending images from %d approved jobs", len(pending), len(accepted))
            command = [str(args.image_python), str(Path(__file__).with_name("generate_reference_images.py")),
                       "--jobs", str(selected), "--reference-audit", str(audit_path), "--output-dir", str(media)]
            subprocess.run(command, check=True, env={**os.environ, "HF_HUB_OFFLINE": "1"})
            state(root, {"status": "auditing", "total_jobs": len(jobs), "eligible_jobs": len(accepted),
                         "generated_jobs": len(accepted), "withheld_jobs": len(withheld), "references": len(work)})
        if done_auditing:
            write_once(root / "withheld-jobs.jsonl", "".join(json.dumps(r) + "\n" for r in withheld))
            state(root, {"status": "complete_with_withheld" if withheld else "generated_pending_visual_acceptance",
                         "total_jobs": len(jobs), "generated_jobs": len(accepted), "withheld_jobs": len(withheld)})
            logging.info("Completed generation: %d images, %d jobs withheld, visual acceptance pending", len(accepted), len(withheld))
            return
        counts = auditor.audit(audit_args)
        logging.info("Audit batch: %s", json.dumps(counts))
        rounds += 1
        done_auditing = counts["audited_this_run"] == 0
        if args.round_limit and rounds >= args.round_limit:
            # Useful for bounded smoke tests. Next invocation generates newly eligible jobs.
            state(root, {"status": "paused_at_round_limit", "rounds": rounds})
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--source-products", type=Path, required=True)
    parser.add_argument("--repair-plan", type=Path, required=True)
    parser.add_argument("--repair-dir", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--image-python", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--audit-batch", type=int, default=20)
    parser.add_argument("--round-limit", type=int)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.audit_batch < 1 or (args.round_limit is not None and args.round_limit < 1):
        parser.error("Batch and round limits must be positive")
    args.run_dir.mkdir(parents=True, exist_ok=True)
    with (args.run_dir / "bulk.log").open("a", buffering=1) as log, \
            (args.run_dir / ".pipeline.lock").open("a") as lock, \
            (args.run_dir / "reference-audit.lock").open("a") as audit_lock:
        os.dup2(log.fileno(), sys.stdout.fileno())
        os.dup2(log.fileno(), sys.stderr.fileno())
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        locked = False
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(audit_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
            run(args)
            return 0
        except Exception:
            logging.exception("Bulk workflow stopped; resume with identical inputs after resolving the error")
            if locked:
                state(args.run_dir, {"status": "failed", "log": "bulk.log"})
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
