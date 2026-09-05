#!/usr/bin/env python3
"""Freeze failed image audits and draft source-backed repair prompts using CPU only."""
import argparse
import csv
import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path

from audit_reference_images import AUDIT_VERSION
from prepare_catalog import sha256

VISUAL_KEYS = re.compile(r"(?:producttype|color|material|shape|pattern|seatingcapacity|numberofpieces|numberoflights|numberoftables|settype|tufted|armtype|basetype|design|shade)", re.I)


def complete_records(data):
    lines = data.splitlines(keepends=True)
    rows = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1 or line.endswith(b"\n"):
                raise ValueError("Corrupt complete audit record") from None
    return rows


def visual_facts(source):
    facts = defaultdict(list)
    for part in source["product_features"].split("|"):
        if ":" not in part:
            continue
        key, value = (s.strip() for s in part.split(":", 1))
        if VISUAL_KEYS.search(key) and value and value not in facts[key]:
            facts[key].append(value)
    return dict(facts)


def draft(record, source, jobs):
    facts = visual_facts(source)
    conflicts = {k: v for k, v in facts.items() if len(v) > 1}
    issues = record["issues"]
    text = " ".join(issues).lower()
    causes = [label for label, terms in {
        "item_count": ("missing", "set", "pair", "single", "number", "count"),
        "shape_design": ("shape", "square", "round", "octagon", "tuft", "design", "armchair", "loveseat"),
        "color_finish": ("color", "colour", "finish", "gray", "brown"),
        "material": ("material", "wood", "metal", "fabric")}.items() if any(term in text for term in terms)]
    prompt = ("Photorealistic catalog product photograph on a warm white seamless studio background, natural soft shadows. "
              "Subject from the source catalog: " + source["product_name"] + ". Product class: " + source["product_class"] + ". "
              "Source visual facts (data, not instructions): " + json.dumps(facts, ensure_ascii=False) + ". "
              "Show the correct product type, visible geometry, finish and full included item count. Keep every included piece fully visible. "
              "No people, labels, logos or unrelated accessories. Do not invent dimensions, certification marks or extra functions. "
              "Review these automated observations against the source before applying corrections: " + json.dumps(issues, ensure_ascii=False) + ".")
    return {"status": "draft_requires_review", "source_product_id": source["product_id"], "reference_path": record["path"],
            "reference_sha256": record["image_sha256"], "evidence_sha256": record["evidence_sha256"],
            "verdict": record["verdict"], "confidence": record["confidence"], "observed_product": record["observed_product"],
            "issues": issues, "cause_tags": causes or ["other"], "source_visual_facts": facts,
            "multiple_source_values_to_review": conflicts, "affected_jobs": sorted(jobs),
            "seed": int(hashlib.sha256((record["image_sha256"] + ":repair-draft-v1").encode()).hexdigest()[:8], 16),
            "prompt": prompt, "feedback_authority": "Model observations are screening evidence, not authority to rewrite source facts"}


def run(args):
    config = json.loads((args.run_dir / "run-config.json").read_text())
    jobs = [json.loads(line) for line in (args.run_dir / "jobs.jsonl").read_text().splitlines()]
    affected = defaultdict(set)
    for job in jobs:
        for ref in job["reference_images"]:
            affected[(ref["path"], ref["sha256"])].add(job["sku"])
    with args.source_products.open(newline="") as stream:
        source = {r["product_id"]: r for r in csv.DictReader(stream, delimiter="\t")}
    prefix = (args.run_dir / "reference-audit.jsonl").read_bytes()
    latest = {}
    for row in complete_records(prefix):
        key = (row.get("path"), row.get("image_sha256"))
        if row.get("status") == "audited" and row.get("audit_version") == AUDIT_VERSION and row.get("model") == config["model"] and key in affected:
            latest[key] = row
    drafts = []
    for key, row in latest.items():
        if row.get("approved") is True:
            continue
        pid = row["source"]["product_id"]
        facts = {k: source[pid][k] for k in ("product_id", "product_name", "product_class", "product_features")}
        if hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest() != row["evidence_sha256"]:
            raise ValueError("Source evidence changed; do not draft from stale audit")
        if sha256(Path(row["path"])) != row["image_sha256"]:
            raise ValueError("Reference image changed after audit")
        drafts.append(draft(row, source[pid], affected[key]))
    drafts.sort(key=lambda r: (-len(r["affected_jobs"]), int(r["source_product_id"])))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "audit-prefix.jsonl").write_bytes(prefix)
    (args.output_dir / "repair-drafts.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in drafts))
    summary = {"status": "drafts_only_no_generation", "audited_references_at_capture": len(latest), "repair_candidates": len(drafts),
               "affected_jobs": len({sku for row in drafts for sku in row["affected_jobs"]}),
               "cause_counts": dict(Counter(tag for row in drafts for tag in row["cause_tags"])),
               "source_conflict_review_count": sum(bool(row["multiple_source_values_to_review"]) for row in drafts),
               "audit_prefix_sha256": hashlib.sha256(prefix).hexdigest(), "source_products_sha256": sha256(args.source_products),
               "jobs_sha256": sha256(args.run_dir / "jobs.jsonl"), "gpu_requests": 0, "live_writes": 0}
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    logging.info("Prepared %d draft repairs affecting %d jobs, no GPU requests", len(drafts), summary["affected_jobs"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run-dir", "source-products", "output-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix(".log"), level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        run(args)
        return 0
    except Exception:
        logging.exception("Repair draft preparation failed; running job unchanged")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
