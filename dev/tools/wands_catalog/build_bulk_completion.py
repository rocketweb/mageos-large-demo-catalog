#!/usr/bin/env python3
"""Prepare the user-authorized bulk test-catalog update and resumable image queue."""
import argparse
import copy
import hashlib
import json
import logging
from pathlib import Path

from build_realism_review import write_json, write_jsonl
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from reconcile_catalog_media import make_contract
from run_catalog_media_pilot import compile_prompt
from verify_catalog_repairs import check, verify_packet


def image_case(root, child):
    selected = copy.deepcopy(root)
    selected['gallery_target'] = {'sku': child['sku'], 'options': child['variant_options']}
    review = {'root_sku': root['sku'], 'selected_sku': child['sku'],
              'selected_options': child['variant_options'], 'reference': child.get('reference'),
              'sale_unit': child['catalog_fields']['lab_sale_unit'],
              'design': child['dimension_design'], 'executable': False}
    contract = make_contract(selected, [] if child['sku'] == root['sku'] else [child], review)
    textile = any(word in root['name'].lower() for word in ('nursery', 'pillowcase', 'sham', 'curtain'))
    framing = ('Front-facing or overhead textile product view, each included textile clearly visible and separated.'
               if textile else 'Three-quarter product view. Show the complete sale unit with space between included objects.')
    prompt = compile_prompt({'acceptance_contract': contract, 'pilot_case': {'framing': framing}})
    digest = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()
    return {'sku': child['sku'], 'root_sku': root['sku'], 'output_file': child['sku']+'-bulk-'+digest[:12]+'.jpg',
            'seed': int(digest[:8], 16), 'prompt': prompt, 'contract': contract, 'definition_sha256': digest}


def build(args):
    check(not args.output_dir.exists(), 'Choose a fresh bulk output directory')
    verify_packet(args.definitions)
    roots = read_jsonl(args.definitions/'candidate-products.jsonl')
    children = read_jsonl(args.definitions/'candidate-children.jsonl')
    changes = read_jsonl(args.definitions/'changes.proposed.jsonl')
    retirements = read_jsonl(args.definitions/'retirements.proposed.jsonl')
    changed = {row['sku'] for row in changes}
    selected = [row for row in roots+children if row['sku'] in changed]
    check(len(selected) == len(changed) == 603 and len(retirements) == 64, 'Unexpected correction scope')
    repaired = [row for row in roots if row.get('repair')]
    check(len(repaired) == 93, 'Unexpected corrected-media family count')
    assignments = read_jsonl(args.assignments) if args.assignments.suffix == '.jsonl' else json.loads(args.assignments.read_text())
    existing = {row['target_sku']: row for row in assignments}
    jobs, reuse, parent_media = [], [], []
    for root in repaired:
        family = [row for row in children if row['parent_sku'] == root['sku']] if root['kind'] == 'configurable' else [root]
        check(bool(family), 'Configurable family has no children')
        for child in sorted(family, key=lambda row: row['sku']):
            job = image_case(root, child)
            if child['sku'] in existing:
                image = existing[child['sku']]['image']
                path = args.exports/image['file']
                check(sha256(path) == image['sha256'], 'Reviewed pilot image drift')
                reuse.append({**job, 'source': str(path.resolve()), 'source_sha256': image['sha256']})
            else:
                jobs.append(job)
        parent_media.append({'root_sku': root['sku'], 'default_child_sku': root['gallery_target']['sku'],
                             'policy': 'Parent hero represents this explicitly selected default variant; children keep their own images.'})
    check(len(reuse) == 5, 'All five completed assortments must be reused')
    args.output_dir.mkdir(parents=True)
    write_jsonl(args.output_dir/'products.jsonl', selected)
    write_jsonl(args.output_dir/'retirements.jsonl', retirements)
    write_jsonl(args.output_dir/'image-jobs.jsonl', jobs)
    write_jsonl(args.output_dir/'reused-images.jsonl', reuse)
    write_jsonl(args.output_dir/'parent-media.jsonl', parent_media)
    write_json(args.output_dir/'scope.json', {'product_updates': len(selected), 'retained_disabled_children': len(retirements),
        'affected_skus': len(selected)+len(retirements), 'corrected_media_families': len(repaired),
        'new_images': len(jobs), 'reused_images': len(reuse), 'configurable_to_simple': 5,
        'decisions': 'User delegated synthetic catalog and media decisions for bulk demo completion. No per-product approval required.',
        'target': 'relevance.comtom.lab', 'images_in_git': False, 'applied': False})
    files = [args.definitions/'manifest.json', args.assignments, Path(__file__)]
    write_json(args.output_dir/'manifest.json', {'version': 'wands-bulk-completion-v1',
        'inputs': {str(p.resolve()): sha256(p) for p in files},
        'outputs': {p.name: sha256(p) for p in args.output_dir.iterdir() if p.is_file()}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('definitions', 'assignments', 'exports', 'output-dir'):
        parser.add_argument('--'+option, type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'), level=logging.INFO)
    try:
        build(args)
        logging.info('Bulk catalog and image queue prepared')
    except Exception:
        logging.exception('Bulk preparation failed')
        raise SystemExit(1)
