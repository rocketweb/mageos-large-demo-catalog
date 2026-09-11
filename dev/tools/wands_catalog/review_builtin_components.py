#!/usr/bin/env python3
"""Bind built-in image results to direct observations without inventing model telemetry."""
import argparse
from html import escape
import json
import logging
from pathlib import Path
import tempfile

from PIL import Image
from build_component_readiness import inventory, render
from build_realism_review import write_json, write_jsonl
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from run_catalog_component_pilot import verify_layouts
from run_catalog_media_pilot import verify_pins
from verify_catalog_repairs import check


CHECKS = {'appearance_and_view', 'identity_and_construction', 'no_text_or_extras',
          'proportions', 'single_complete_component', 'synthetic_provenance'}


def verdict(checks):
    check(set(checks) == CHECKS and all(v in {'pass', 'uncertain', 'fail'} for v in checks.values()),
          'Missing or invalid visual check')
    return 'fail' if 'fail' in checks.values() else 'uncertain' if 'uncertain' in checks.values() else 'pass'


def validate_records(rows, known):
    check(rows and len({(r['asset_requirement_id'], r['attempt']) for r in rows}) == len(rows),
          'Empty or duplicate generation attempts')
    for r in rows:
        check(r['asset_requirement_id'] in known and type(r['attempt']) is int and r['attempt'] > 0,
              'Unknown asset or invalid attempt')
        check(r['generator'] == 'built-in image_gen' and r.get('seed') is None and
              r.get('model_version') is None and 'token_count' not in r, 'Unverified runtime metadata')
        check(r['prompt'].strip() and r['finding'].strip() and
              r['review_method'] == 'direct_image_inspection', 'Missing prompt or direct observation')


def convert_native(source, expected_hash, target):
    check(not target.exists() and not target.is_symlink(), 'Conversion would overwrite evidence')
    check(sha256(source) == expected_hash, 'Native image changed')
    with Image.open(source) as image:
        check(image.format == 'PNG' and image.mode == 'RGB',
              'Native source must be RGB PNG; preserve generated alpha through a separate explicit path')
        image.load()
        image.save(target, 'WEBP', lossless=True, exact=True)
        with Image.open(target) as converted:
            check(converted.mode == 'RGB' and converted.size == image.size and
                  converted.tobytes() == image.tobytes(), 'Conversion changed decoded pixels')
    check(sha256(source) == expected_hash, 'Native image changed during conversion')


def restore_history(assets, source_rows):
    indexes = {source: {(digest(r['case']), r['image_sha256']): r for r in rows}
               for source, rows in source_rows.items()}
    result = []
    for asset in assets:
        for h in asset['history']:
            source = h['review_source']
            row = indexes.get(source, {}).get((h['execution_case_sha256'], h['image_sha256']))
            check(row is not None and row['finding'] == h['finding'] and row['verdict'] == h['verdict'],
                  'Baseline history is missing or changed')
            result.append({**row, 'review_source': source})
    return result


def build(args):
    output = args.output_dir.resolve()
    check(not output.exists() and not output.is_symlink(), 'Use a fresh review output directory')
    briefs, pins = verify_layouts(args.layouts)
    known = {b['asset_requirement_id']: b for b in briefs}
    baseline = args.baseline.resolve()
    manifest_path = baseline / 'manifest.json'
    baseline_manifest = json.loads(manifest_path.read_text())
    check(baseline_manifest['version'] == 'wands-component-repair-review-v1' and
          baseline_manifest['publication_approved'] is False, 'Wrong baseline')
    incoming = {**baseline_manifest['inputs'], str(manifest_path): sha256(manifest_path),
                **{str(baseline / k): v for k, v in baseline_manifest['outputs'].items()}}
    check(all(k not in pins or pins[k] == v for k, v in incoming.items()), 'Conflicting baseline provenance')
    verify_pins(incoming)
    pins.update(incoming)
    rows = json.loads(args.records.read_text())
    validate_records(rows, known)
    for r in rows:
        verdict(r['checks'])
        for key, hash_key in (('native_path', 'native_sha256'), ('reference_path', 'reference_sha256')):
            path = Path(r[key]).resolve()
            check(str(path) not in pins or pins[str(path)] == r[hash_key], 'Conflicting image provenance')
            pins[str(path)] = r[hash_key]
    for path in (args.records, Path(__file__), Path(__file__).with_name('build_component_readiness.py')):
        pins[str(path.resolve())] = sha256(path)
    check(not any(Path(p).is_relative_to(output) or output.is_relative_to(Path(p).parent)
                  for p in pins if Path(p).suffix in {'.png', '.webp'} or Path(p).name == 'manifest.json'),
          'Output overlaps protected evidence')
    verify_pins(pins)
    old_assets = read_jsonl(baseline / 'assets.proposed.jsonl')
    sources = {h['review_source'] for a in old_assets for h in a['history']}
    source_rows = {}
    for source in sources:
        path = Path(source) / 'reviews.jsonl'
        check(pins.get(str(path.resolve())) == sha256(path), 'Unpinned baseline review source')
        source_rows[source] = read_jsonl(path)
    reviews = restore_history(old_assets, source_rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.' + output.name + '-') as folder:
        stage = Path(folder)
        new_reviews, selection, cards = [], [], []
        for r in rows:
            key = r['asset_requirement_id']
            filename = key + '-builtin-v' + str(r['attempt']) + '.webp'
            target = stage / filename
            convert_native(Path(r['native_path']), r['native_sha256'], target)
            case = {'asset_requirement_id': key, 'brief': known[key], 'generation': r}
            review = {'case': case, 'verdict': verdict(r['checks']), 'checks': r['checks'],
                      'image_path': str(output / filename), 'image_sha256': sha256(target),
                      'finding': r['finding'], 'review_source': str(output),
                      'review_date': r['review_date'], 'review_method': r['review_method'],
                      'native_sha256': r['native_sha256'], 'publication_approved': False}
            reviews.append(review)
            new_reviews.append(review)
            h = lambda x: escape(str(x), quote=True)
            cards.append('<article><h2>' + h(key) + ' / attempt ' + str(r['attempt']) + '</h2><p>' +
                         h(review['verdict']) + ': ' + h(r['finding']) + '</p><img src="' +
                         h((output / filename).as_uri()) + '" alt="' + h(known[key]['component']['label']) +
                         '"><details><summary>Actual prompt and provenance</summary><pre>' +
                         h(json.dumps(r, indent=2)) + '</pre></details></article>')
        assets, families, counts = inventory(briefs, reviews)
        new_hashes = {r['image_sha256'] for r in new_reviews}
        for a in assets:
            c = a['proposed_candidate']
            if a['status'] == 'initial_visual_pass' and c['image_sha256'] in new_hashes:
                selection.append({'asset_requirement_id': a['asset_requirement_id'],
                                  'image_path': c['image_path'], 'image_sha256': c['image_sha256'],
                                  'initial_visual_pass': True})
        write_jsonl(stage / 'reviews.jsonl', reviews)
        write_jsonl(stage / 'assets.proposed.jsonl', assets)
        write_jsonl(stage / 'families.jsonl', families)
        write_json(stage / 'cutout-selection.json', selection)
        (stage / 'review.html').write_text(render(assets, families, counts).replace(
            '</h1>', '</h1><p><a href="attempts.html">Built-in generation attempts and actual prompts</a></p>', 1))
        (stage / 'attempts.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>Built-in component repairs</title>'
            '<style>body{font:17px/1.5 system-ui;max-width:1100px;margin:auto;padding:24px;background:#eef2ef}'
            'article{background:white;padding:24px;margin:24px 0}img{max-width:100%;height:620px;object-fit:contain}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere}h2{overflow-wrap:anywhere}</style>'
            '<h1>Built-in component generation</h1><p>Synthetic lab assets. Direct visual review is separate from '
            'cutout acceptance, complete-assortment acceptance and publication. Native PNGs are retained; '
            'WebP copies preserve every decoded RGB pixel and original canvas. Model version, seeds and '
            'token usage were not exposed by the tool and are not invented.</p>' + ''.join(cards) + '</html>')
        verify_pins(pins)
        # This is the same repair-inventory interchange contract, with explicit backend provenance.
        write_json(stage / 'manifest.json', {'version': 'wands-component-repair-review-v1',
            'adapter_version': 'wands-builtin-component-review-v1', 'generation_backend': 'built-in image_gen',
            'inputs': pins, 'outputs': {p.name: sha256(p) for p in sorted(stage.iterdir())},
            'counts': {**counts, 'builtin_attempts': len(rows), 'new_cutout_candidates': len(selection)},
            'publication_approved': False})
        stage.rename(output)
    return {**counts, 'builtin_attempts': len(rows), 'new_cutout_candidates': len(selection)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('records', 'layouts', 'baseline', 'output-dir'):
        parser.add_argument('--' + flag, required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        logging.info('Built-in component review: %s', json.dumps(build(args), sort_keys=True))
        return 0
    except Exception:
        logging.exception('Review stopped without publication')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
