#!/usr/bin/env python3
"""Review immutable nonpaired completion runs without rewriting their generation code."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import logging
import math
from pathlib import Path
import tempfile

from PIL import Image
from build_realism_review import write_json, write_jsonl
from catalog_repairs import read_jsonl
from component_completion import BATCHES, descriptor, finalize_cases, prepare, render, verify_output
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from review_catalog_component_pilot import CHECKS
from review_catalog_framing_pilot import measure_envelope
from run_catalog_media_pilot import verify_pins
from verify_catalog_repairs import check


def bind_observations(cases, notes, run_dir):
    indexed = {n['trial_id']: n for n in notes}
    check(len(indexed) == len(notes) == len(cases) and set(indexed) == {c['trial_id'] for c in cases}, 'Observation scope differs')
    rows = []
    for c in cases:
        n = indexed[c['trial_id']]; path = run_dir / c['candidate_filename']; s = c['settings']; b = c['source_case']['brief']
        check(n['image_sha256'] == sha256(path) and n['case_sha256'] == digest(c), 'Stale completion observation')
        check(n['review_method'] == 'direct_image_inspection' and
              all(isinstance(n[k], str) and n[k].strip() for k in ('review_date', 'finding', 'next_direction')), 'Incomplete review evidence')
        check(set(n['checks']) == CHECKS and all(v in {'pass', 'fail', 'uncertain'} for v in n['checks'].values()), 'Incomplete visual checks')
        box = n['estimated_subject_bbox']
        check(isinstance(box, list) and len(box) == 4 and all(type(v) in (float, int) and math.isfinite(v) for v in box), 'Invalid bounds')
        x1, y1, x2, y2 = box
        check(0 <= x1 < x2 <= s['width'] and 0 <= y1 < y2 <= s['height'], 'Bounds outside canvas')
        dims = b['component']['dimensions_cm']
        height = dims['lab_spec_height_cm'] if b['view'] == 'front elevation' else dims.get('lab_spec_length_cm', dims.get('lab_spec_depth_cm'))
        target = height / dims['lab_spec_width_cm']; observed = (y2 - y1) / (x2 - x1)
        with Image.open(path) as image:
            check(image.size == (s['width'], s['height']) and image.mode == 'RGB' and image.format == 'WEBP', 'Unexpected candidate image')
            diagnostics = measure_envelope(image)
        verdict = 'fail' if 'fail' in n['checks'].values() else 'uncertain' if 'uncertain' in n['checks'].values() else 'pass'
        rows.append({**n, 'case': c, 'image_path': str(path.resolve()), 'verdict': verdict,
                     'target_ratio': target, 'estimated_ratio': observed, 'relative_ratio_error': observed / target - 1,
                     'pixel_diagnostics': diagnostics, 'mask_ready': False, 'assembly_ready': False,
                     'publication_approved': False, 'reference_use_approved': False})
    return rows


def build(args):
    raw, pins, output = prepare(args)
    d = json.loads((output / 'run.json').read_text()); executed = read_jsonl(output / 'execution-cases.jsonl')
    verify_pins(d['inputs']); runtime = d['runtime']; pins = {**pins, **runtime['tokenizer_hashes']}
    cases = finalize_cases(raw, [c['source_case']['token_count'] for c in executed])
    check(not verify_output(output, cases, descriptor(cases, pins, runtime, args.batch)), 'Batch is incomplete')
    destination = args.review_dir
    check(not destination.exists() and not destination.is_symlink(), 'Use a fresh completion review directory')
    pins = {**pins, **{str(p): sha256(p) for p in output.iterdir() if p.name != '.pilot.lock'},
            str(args.observations.resolve()): sha256(args.observations), str(Path(__file__).resolve()): sha256(Path(__file__))}
    dest = destination.resolve()
    protected = {Path(p).parent for p in pins if Path(p).name in {'manifest.json', 'run.json'} or Path(p).suffix.lower() in {'.jpg', '.png', '.webp'}}
    check(not any(Path(p).is_relative_to(dest) for p in pins) and not any(dest.is_relative_to(p) for p in protected), 'Review overlaps source')
    rows = bind_observations(cases, json.loads(args.observations.read_text()), output)
    counts = Counter(r['verdict'] for r in rows)
    counts = {**{k: counts[k] for k in ('pass', 'fail', 'uncertain')}, 'reviewed': len(rows), 'mask_ready': 0, 'assembly_ready': 0, 'publication_approved': 0}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.' + destination.name + '-') as folder:
        stage = Path(folder); write_jsonl(stage / 'reviews.jsonl', rows); (stage / 'review.html').write_text(render(rows)); verify_pins(pins)
        write_json(stage / 'manifest.json', {'version': 'wands-component-completion-review-v1', 'batch': args.batch, 'inputs': pins,
                   'outputs': {p.name: sha256(p) for p in stage.iterdir()}, 'counts': counts, 'publication_approved': False})
        stage.rename(destination)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('layouts', 'readiness', 'selection', 'output-dir', 'observations', 'review-dir'):
        parser.add_argument('--' + flag, required=True, type=Path)
    parser.add_argument('--selection-sha256', required=True); parser.add_argument('--batch', choices=BATCHES, required=True)
    parser.add_argument('--json', action='store_true'); args = parser.parse_args()
    args.review_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.review_dir.with_name(args.review_dir.name + '.log'), level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        result = build(args); logging.info('Completion review: %s', json.dumps(result, sort_keys=True))
        if args.json: print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        logging.exception('Review stopped without changing the frozen run'); return 1


if __name__ == '__main__': raise SystemExit(main())
