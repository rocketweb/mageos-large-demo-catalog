#!/usr/bin/env python3
"""Append five completion reviews to frozen component history; never assign live media."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import tempfile

from build_component_readiness import inventory, render, VERSIONS
from build_realism_review import write_json, write_jsonl
from catalog_repairs import read_jsonl
from component_completion import BATCHES
from prepare_catalog import sha256
from run_catalog_component_pilot import verify_layouts
from run_catalog_media_pilot import verify_pins
from verify_catalog_repairs import check


def merge_pins(pins, incoming):
    check(all(k not in pins or pins[k] == v for k, v in incoming.items()), 'Conflicting review provenance')
    pins.update(incoming)


def consolidate(briefs, baseline, additions):
    assets, _, _ = inventory(briefs, baseline)
    expected = {a['asset_requirement_id'] for a in assets if a['status'] != 'initial_visual_pass'}
    actual = [r['case'].get('source_case', r['case'])['asset_requirement_id'] for r in additions]
    check(len(actual) == len(set(actual)) and set(actual) == expected, 'Completion scope differs from remaining components')
    return inventory(briefs, baseline + additions)


def read_packet(packet, pins, version):
    packet = packet.resolve(); m = json.loads((packet / 'manifest.json').read_text())
    check(m['version'] == version and m['publication_approved'] is False, 'Unexpected packet or approval state')
    check(set(m['outputs']) == {'reviews.jsonl', 'review.html'} and
          {p.name for p in packet.iterdir()} == {'manifest.json', *m['outputs']}, 'Unexpected review contents')
    incoming = {**m['inputs'], str(packet / 'manifest.json'): sha256(packet / 'manifest.json'),
                **{str(packet / k): v for k, v in m['outputs'].items()}}
    verify_pins(incoming); merge_pins(pins, incoming)
    rows = read_jsonl(packet / 'reviews.jsonl')
    for r in rows:
        check(pins.get(str(Path(r['image_path']).resolve())) == r['image_sha256'], 'Candidate image is not pinned')
        check(r['publication_approved'] is False and r['assembly_ready'] is False and r['mask_ready'] is False, 'Unexpected review acceptance')
    return [{**r, 'review_source': str(packet)} for r in rows], m


def build(layouts, baseline, additions, output):
    check(not output.exists() and not output.is_symlink(), 'Use a fresh readiness directory')
    check(len(baseline) == 3 and len(additions) == 5 and len({p.resolve() for p in baseline + additions}) == 8, 'Provide eight distinct review passes')
    briefs, pins = verify_layouts(layouts); old = []; new = []
    for packet, version in zip(baseline, VERSIONS):
        rows, _ = read_packet(packet, pins, version); old.extend(rows)
    for packet, batch in zip(additions, BATCHES):
        rows, m = read_packet(packet, pins, 'wands-component-completion-review-v1')
        check(m['batch'] == batch and all(r['case']['batch'] == batch for r in rows), 'Completion batch order changed')
        new.extend(rows)
    assets, families, counts = consolidate(briefs, old, new)
    for name in ('completion_readiness.py', 'build_component_readiness.py'):
        p = Path(__file__).with_name(name).resolve(); merge_pins(pins, {str(p): sha256(p)})
    dest = output.resolve()
    protected = {Path(p).parent for p in pins if Path(p).name == 'manifest.json' or Path(p).suffix.lower() in {'.jpg', '.png', '.webp'}}
    check(not any(Path(p).is_relative_to(dest) for p in pins) and not any(dest.is_relative_to(p) for p in protected), 'Readiness overlaps source')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.' + output.name + '-') as folder:
        stage = Path(folder); write_jsonl(stage / 'assets.proposed.jsonl', assets); write_jsonl(stage / 'families.jsonl', families)
        html = render(assets, families, counts)
        html = html.replace('</div><p class="notice">', '<p><strong>' + str(counts['failed']) + '</strong>failed component types</p></div><p class="notice">', 1)
        (stage / 'review.html').write_text(html); verify_pins(pins)
        write_json(stage / 'manifest.json', {'version': 'wands-component-readiness-v2', 'inputs': pins,
                   'outputs': {p.name: sha256(p) for p in sorted(stage.iterdir())}, 'counts': counts,
                   'mask_execution_approved': False, 'publication_approved': False})
        stage.rename(output)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layouts', required=True, type=Path); parser.add_argument('--baseline', required=True, nargs=3, type=Path)
    parser.add_argument('--completion', required=True, nargs=5, type=Path); parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--json', action='store_true'); args = parser.parse_args(); args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_name(args.output_dir.name + '.log'), level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        result = build(args.layouts, args.baseline, args.completion, args.output_dir)
        logging.info('Readiness summary: %s', json.dumps(result, sort_keys=True))
        if args.json: print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        logging.exception('Readiness stopped without changing media or approval'); return 1


if __name__ == '__main__': raise SystemExit(main())
