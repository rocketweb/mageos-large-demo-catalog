#!/usr/bin/env python3
"""Verify and render a completed pilot's visual observations. No model calls or image approval."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from html import escape
import json
import logging
from pathlib import Path
import tempfile

from PIL import Image
from build_realism_review import write_json, write_jsonl
from catalog_repairs import read_jsonl
from plan_catalog_media_repairs import CHECKS, SETTINGS
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from run_catalog_media_pilot import compile_prompt, pending_cases, verify_pins, verify_plan
from verify_catalog_repairs import check

BINDINGS = ('image_sha256', 'definition_sha256', 'runtime_prompt_sha256')


def classify(observation):
    checks = observation['checks']
    check(isinstance(checks, dict) and set(checks) == set(CHECKS), 'Missing or unexpected visual checks')
    check(all(v in {'pass', 'fail', 'uncertain'} for v in checks.values()), 'Unreviewed or invalid visual check')
    check(observation.get('review_method') == 'direct_image_inspection', 'Expected direct image observations')
    check(all(isinstance(observation.get(k), str) and observation[k].strip()
              for k in ('finding', 'next_direction', 'review_date')), 'Incomplete visual observation')
    return 'fail' if 'fail' in checks.values() else 'uncertain' if 'uncertain' in checks.values() else 'pass'


def bind_observations(cases, observations, run_dir):
    indexed = {o['root_sku']: o for o in observations}
    check(len(indexed) == len(observations), 'Duplicate visual observation')
    check(set(indexed) == {c['root_sku'] for c in cases}, 'Visual observation scope differs from pilot')
    rows = []
    for case in cases:
        image_path = run_dir / case['candidate_filename']
        observation = indexed[case['root_sku']]
        expected = {**{k: case[k] for k in BINDINGS if k != 'image_sha256'}, 'image_sha256': sha256(image_path)}
        check(all(observation.get(k) == v for k, v in expected.items()), 'Stale visual observation: ' + case['root_sku'])
        # Derived last: an input cannot turn a failed screen into approval.
        rows.append({**observation, 'verdict': classify(observation), 'candidate_path': str(image_path),
                     'original_reference': case['original_reference_evidence'], 'contract': case['acceptance_contract'],
                     'challenge': case['pilot_case']['challenge'], 'token_count': case['token_count'],
                     'runtime_prompt': case['runtime_prompt'], 'publication_approved': False,
                     'reference_use_approved': False, 'bulk_generation_approved': False})
    return rows


def verify_run(plan_dir, run_dir):
    descriptor = json.loads((run_dir / 'run.json').read_text())
    planned, pins = verify_plan(plan_dir, descriptor['approved_plan_sha256'])
    runner = Path(__file__).with_name('run_catalog_media_pilot.py')
    check(sha256(runner) == descriptor['runner_sha256'], 'Pilot runner changed')
    pins[str(runner.resolve())] = descriptor['runner_sha256']
    pins.update(descriptor['runtime']['tokenizer_hashes'])
    cases = read_jsonl(run_dir / 'execution-cases.jsonl')
    check(descriptor['settings'] == SETTINGS and descriptor['max_attempts'] == len(planned), 'Run settings changed')
    check(digest(cases) == descriptor['cases_sha256'], 'Execution case digest changed')
    check(len(cases) == len(planned), 'Execution case count changed')
    for case, proposal in zip(cases, planned):
        prompt = compile_prompt(proposal)
        token = digest({'plan_case': proposal, 'runtime_prompt': prompt, 'settings': SETTINGS})[:16]
        expected = {**proposal, 'runtime_prompt': prompt,
                    'runtime_prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                    'candidate_filename': proposal['root_sku'] + '-hero-' + token + '.webp',
                    'token_count': case['token_count']}
        check(case == expected and type(case['token_count']) is int and 0 < case['token_count'] <= 512,
              'Execution case differs from approved plan')
    check(not pending_cases(cases, run_dir), 'Pilot is incomplete; do not render a complete review')
    allowed = {'run.json', 'execution-cases.jsonl', 'events.jsonl', '.pilot.lock'} | {
        name for c in cases for name in (c['candidate_filename'], c['candidate_filename'] + '.json')}
    check({p.name for p in run_dir.iterdir()} <= allowed, 'Unexpected run contents')
    for path in run_dir.iterdir():
        check(not path.is_symlink(), 'Run symlinks are forbidden')
        if path.name != '.pilot.lock':
            check(path.is_file(), 'Unexpected run directory')
            pins[str(path)] = sha256(path)
    for case in cases:
        image_path = run_dir / case['candidate_filename']
        metadata = json.loads((run_dir / (image_path.name + '.json')).read_text())
        check(metadata['acceptance_contract'] == case['acceptance_contract']
              and metadata['required_disclosure'] == case['acceptance_contract']['required_disclosure']
              and metadata['required_disclosure']
              and metadata['settings'] == SETTINGS
              and metadata['seed'] == case['proposed_seed']
              and metadata['runtime_prompt'] == case['runtime_prompt']
              and metadata['image_sha256'] == sha256(image_path)
              and metadata['visual_acceptance'] == 'pending', 'Candidate metadata or original approval state changed')
        with Image.open(image_path) as image:
            check(image.size == (768, 768) and image.format == 'WEBP', 'Invalid pilot image format or size')
            image.verify()
        reference = case['original_reference_evidence']
        pins[reference['path']] = reference['sha256']
    verify_pins(pins)
    return cases, pins


def render(rows, counts):
    h = lambda value: escape(str(value), quote=True)
    labels = {'pass': 'Pass: initial visual screen', 'fail': 'Fail: do not use', 'uncertain': 'Uncertain: hold'}
    token_range = str(min(r['token_count'] for r in rows)) + ' to ' + str(max(r['token_count'] for r in rows))
    cards = []
    for row in rows:
        c = row['contract']
        parts = '; '.join(str(p['quantity']) + ' × ' + p['label'] for p in c['components']) or c['sale_unit']
        checklist = ''.join('<li><span class="' + status + '">' + h(status.upper()) + '</span> ' +
                            h(key.replace('_', ' ')) + '</li>' for key, status in row['checks'].items())
        figures = ''.join('<figure><figcaption>' + label + '</figcaption><a href="' + h(Path(path).as_uri()) +
                          '"><img src="' + h(Path(path).as_uri()) + '" alt="' + h(label + ': ' + c['product_name']) +
                          '" width="768" height="768"></a></figure>' for label, path in (
                              ('Original evidence, unchanged', row['original_reference']['path']),
                              ('New local pilot candidate', row['candidate_path'])))
        cards.append('<article id="' + h(row['root_sku']) + '"><p class="eyebrow">' + h(row['root_sku']) +
                     ' · ' + h(row['challenge']) + '</p><h2>' + h(c['product_name']) +
                     '</h2><p class="badge ' + row['verdict'] + '">' + labels[row['verdict']] +
                     '</p><p><strong>Selected:</strong> ' + h(', '.join(c['selected_options'].values())) +
                     '<br><strong>Required:</strong> ' + h(parts) + '</p><div class="comparison">' + figures +
                     '</div><p class="finding">' + h(row['finding']) + '</p><p><strong>Next:</strong> ' +
                     h(row['next_direction']) + '</p><details><summary>Checks, actual prompt and fingerprints</summary><ul>' +
                     checklist + '</ul><p>' + h(c['required_disclosure']) + '</p><pre>' + h(row['runtime_prompt']) +
                     '</pre><p>' + str(row['token_count']) + ' / 512 prompt tokens</p><dl>' +
                     ''.join('<dt>' + h(key) + '</dt><dd><code>' + h(row[key]) + '</code></dd>' for key in BINDINGS) +
                     '</dl></details></article>')
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Corrected catalog: local pilot review</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f0f2ef;color:#17231e;font:17px/1.55 system-ui,sans-serif}
main{max-width:1300px;margin:auto;padding:48px 32px}h1{font-size:clamp(2rem,4vw,3.2rem);line-height:1.12;max-width:950px}
h2{font-size:1.65rem;line-height:1.25;margin:8px 0}a{color:#154b8a}article{background:white;border:1px solid #d4ddd5;
border-radius:14px;margin:30px 0;padding:30px;scroll-margin-top:20px}.eyebrow{font-size:13px;text-transform:uppercase;letter-spacing:.06em}
.stats{display:flex;gap:12px;flex-wrap:wrap}.stats div{background:white;padding:12px 20px;border-radius:10px}
.stats strong{display:block;font-size:2rem}.badge{display:inline-block;border-radius:8px;padding:5px 10px;margin:8px 0}
.pass{color:#14572d;background:#e1f4e5}.fail{color:#8a201d;background:#fee6e2}.uncertain{color:#6b4700;background:#fff0c8}
.comparison{display:grid;grid-template-columns:1fr 1fr;gap:20px}figure{margin:0;min-width:0}figcaption{font-size:14px;color:#42554a;margin-bottom:7px}
img{display:block;width:100%;height:auto;aspect-ratio:1;object-fit:contain;background:#f3f3f3;border-radius:8px}
.finding{font-size:1.1rem}summary{cursor:pointer;color:#154b8a}details{border-top:1px solid #ddd;padding-top:12px}
li span{padding:2px 5px;font-size:.8rem}li{margin:7px 0}pre,code{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}
pre{padding:18px;background:#f0f3f1}dd{margin-left:0}dt{font-size:13px;color:#45584b;margin-top:8px}
.notice{border-left:4px solid #ac7120;padding:5px 18px;background:#fff8e8}nav{display:flex;gap:8px 18px;flex-wrap:wrap;margin:24px 0}
@media(max-width:700px){main{padding:24px 14px}article{padding:18px}.comparison{grid-template-columns:1fr}h2{font-size:1.4rem}}
</style></head><body><main><p class="eyebrow">Synthetic lab catalog · direct image inspection</p>
<h1>Corrected definitions.<br>New images under review.</h1>
<p>Local FLUX.2 Klein 4B, 4-bit, 768 × 768, four steps, text-only. One attempt per product, zero retries.
Originals are evidence only, not conditioning images. No original media or storefront was changed.</p>
<div class="stats">""" + ''.join('<div><strong>' + str(counts[key]) + '</strong>' + label + '</div>' for key, label in (
        ('reviewed', 'images reviewed'), ('pass', 'initial passes'), ('uncertain', 'uncertain'), ('fail', 'failures'))) + """
</div><p class="notice">This is a deliberately selected stress test, not a catalog-wide quality estimate.
A pass is an initial synthetic-design visual screen, not proof of physical dimensions, materials, manufacturer equivalence
or safety. No candidate is approved here for publication, reference conditioning or bulk expansion.</p>
<p>The runner compacts visual facts and rejects prompts above the installed encoder's 512-token budget.
Actual prompts in this pilot: """ + token_range + """ tokens. Complete contracts and synthetic provenance remain in metadata.</p>
<nav aria-label="Jump to product">""" + ''.join('<a href="#' + h(r['root_sku']) + '">' + h(r['root_sku']) + '</a>' for r in rows) + """
</nav>""" + ''.join(cards) + '<footer>Review observations are bound to candidate bytes, corrected definitions and actual prompts. No automatic acceptance or further generation.</footer></main></body></html>\n'


def build(plan_dir, run_dir, observation_path, output):
    run_dir = run_dir.resolve()
    check(not output.is_symlink() and not output.exists(), 'Use a fresh review directory')
    output = output.resolve()
    cases, pins = verify_run(plan_dir, run_dir)
    raw = observation_path.read_bytes()
    observations = json.loads(raw)
    check(isinstance(observations, list), 'Observations must be an array')
    pins[str(observation_path.resolve())] = hashlib.sha256(raw).hexdigest()
    pins[str(Path(__file__).resolve())] = sha256(Path(__file__))
    check(not output.is_relative_to(run_dir) and not any(Path(p).is_relative_to(output) for p in pins),
          'Review cannot overlap the run or source inputs')
    rows = bind_observations(cases, observations, run_dir)
    totals = Counter(r['verdict'] for r in rows)
    counts = {'reviewed': len(rows), **{key: totals[key] for key in ('pass', 'fail', 'uncertain')},
              'publication_approved': 0, 'bulk_generation_approved': 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.' + output.name + '-') as folder:
        stage = Path(folder)
        write_jsonl(stage / 'reviews.jsonl', rows)
        (stage / 'review.html').write_text(render(rows, counts))
        verify_pins(pins)
        write_json(stage / 'manifest.json', {'version': 'wands-media-pilot-review-v1', 'run': str(run_dir),
                   'inputs': pins, 'outputs': {p.name: sha256(p) for p in sorted(stage.iterdir())}, 'counts': counts,
                   'publication_approved': False, 'bulk_generation_approved': False, 'deployment_ready': False})
        stage.rename(output)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--json', action='store_true', help='Opt in to a terminal summary')
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_name(args.output_dir.name + '.log'), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        result = build(args.plan, args.run_dir, args.observations, args.output_dir)
        logging.info('Completed local visual review: %s', json.dumps(result, sort_keys=True))
        if args.json:
            print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except Exception:
        logging.exception('Pilot review stopped; no images or approvals changed')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
