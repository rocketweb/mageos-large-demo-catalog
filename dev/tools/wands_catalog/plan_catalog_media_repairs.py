#!/usr/bin/env python3
"""Prepare a bounded, non-executable local hero-repair proposal. No model calls."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from build_realism_review import unique_index, write_json, write_jsonl
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from reconcile_catalog_media import digest, draft_prompt, make_contract, triage_counts
from verify_catalog_repairs import check, verify_packet

VERSION = 'wands-media-repair-plan-v1'
REVIEW_OUTPUTS = {'hero-review-drafts.jsonl', 'gallery-dependencies.jsonl', 'image-integrity.json',
                  'definition-verification.json', 'review.html'}
# Retain the existing local generator's settings as a proposal, not a model-quality claim.
SETTINGS = {'model': 'flux2-klein-4b', 'quantize': 4, 'width': 768, 'height': 768, 'steps': 4,
            'mode': 'text_only', 'max_attempts_per_root': 1, 'automatic_retries': 0,
            'derivative_views': 0, 'remote_uploads': 0, 'overwrite_originals': False}
CHECKS = ['identity_and_shape', 'selected_options', 'exact_sale_unit_and_component_count',
          'no_excluded_items', 'coherent_geometry_and_anatomy', 'no_text_or_branding',
          'no_unsupported_claims_or_unsafe_staging', 'synthetic_provenance_in_metadata']


def verify_review_row(row, root, children, source_review):
    ref = source_review['reference']
    check(row['contract'] == make_contract(root, children, source_review),
          'Review contract differs from corrected definition: ' + root['sku'])
    check(row['definition_sha256'] == digest(row['contract']), 'Review definition fingerprint changed')
    check(ref and row['reference'] == ref and sha256(Path(ref['path'])) == ref['sha256'], 'Review reference changed')
    check(row['integrity']['status'] == 'valid_image_bytes', 'Invalid image requires technical repair first')
    check(row['executable'] is False and row['reference_use_approved'] is False, 'Unexpected image approval')
    finding = row['finding']
    check(finding and finding['executable'] is False and
          all(finding[k] == source_review[k] for k in ('reference', 'selected_sku', 'design')), 'Unbound visual finding')
    check(finding.get('verdict', 'fail') in {'fail', 'uncertain'}, 'Unexpected visual finding verdict')
    expected = 'reviewed_uncertain' if finding.get('verdict', 'fail') == 'uncertain' else 'known_reference_defect'
    check(row['visual_status'] == expected, 'Visual status differs from observation')


def verify_review_packet(packet):
    """Check current bytes and reconstruct contracts from independently verified definitions."""
    packet = packet.resolve()
    manifest_path = packet / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    check(set(manifest['outputs']) == REVIEW_OUTPUTS, 'Unexpected media review outputs')
    check({p.name for p in packet.iterdir()} == REVIEW_OUTPUTS | {'manifest.json'}, 'Unexpected review contents')
    pins = dict(manifest['inputs'])
    for name, value in manifest['outputs'].items():
        check(Path(name).name == name, 'Unsafe review output path')
        pins[str(packet / name)] = value
    pins[str(manifest_path)] = sha256(manifest_path)
    for path, expected in pins.items():
        check(sha256(Path(path)) == expected, 'Pinned review input or output changed: ' + path)
    check(manifest['executable'] is False and manifest['deployment_ready'] is False,
          'Expected a non-executable review packet')
    definitions = Path(manifest['definition_packet']).resolve()
    check(str(definitions / 'manifest.json') in pins, 'Definition manifest is not pinned')
    verify_packet(definitions)
    roots = {r['sku']: r for r in read_jsonl(definitions / 'candidate-products.jsonl') if r.get('repair')}
    children = defaultdict(list)
    for child in read_jsonl(definitions / 'candidate-children.jsonl'):
        children[child['parent_sku']].append(child)
    source_reviews = unique_index(read_jsonl(definitions / 'reference-review.jsonl'), 'root_sku')
    rows = read_jsonl(packet / 'hero-review-drafts.jsonl')
    indexed = unique_index([{'root_sku': r['contract']['root_sku'], 'row': r} for r in rows], 'root_sku')
    check(set(indexed) == set(roots) == set(source_reviews), 'Media review root scope changed')
    coverage = triage_counts(rows, require_complete=True)
    check(all(manifest['counts'][key] == value for key, value in coverage.items()), 'Review coverage counts changed')
    check(manifest['counts']['review_roots'] == len(rows), 'Review root count changed')
    for sku, item in indexed.items():
        verify_review_row(item['row'], roots[sku], children[sku], source_reviews[sku])
    return rows, pins


def make_plan(reviews, decisions, selection):
    triage_counts(reviews, require_complete=True)
    indexed = unique_index([{'root_sku': r['contract']['root_sku'], 'row': r} for r in reviews], 'root_sku')
    focused = unique_index(decisions, 'root_sku')
    uncertain = {sku for sku, item in indexed.items() if item['row']['visual_status'] == 'reviewed_uncertain'}
    check(set(focused) == uncertain, 'Focused decisions must cover exactly the uncertain roots')
    check(0 < len(selection) <= 12, 'Pilot must contain between one and twelve roots')
    pilot = unique_index(selection, 'root_sku')
    check(set(pilot) <= set(indexed), 'Unknown pilot root')
    for case in selection:
        check(all(isinstance(case.get(k), str) and case[k].strip() for k in ('challenge', 'framing')),
              'Pilot case lacks challenge or framing')
    plan = []
    for sku, item in sorted(indexed.items()):
        row = item['row']; contract = row['contract']; note = focused.get(sku)
        action = 'repair_confirmed_defect'
        if note:
            check(note['disposition'] in {'retain_candidate', 'clarify_hero'}, 'Unsupported focused disposition; no approval allowed')
            check(note['selected_sku'] == contract['selected_sku'] and
                  note['definition_sha256'] == row['definition_sha256'] and
                  note['reference_sha256'] == row['reference']['sha256'], 'Stale focused decision')
            check(all(isinstance(note.get(k), str) and note[k].strip() for k in ('evidence', 'direction', 'observation')),
                  'Focused decision lacks evidence or direction')
            action = note['disposition']
        case = pilot.get(sku)
        check(not case or action != 'retain_candidate', 'A retained candidate cannot enter the repair pilot')
        instruction = None; filename = None; seed = None
        if action != 'retain_candidate':
            instruction = draft_prompt(contract, row['finding'] if not note else None)
            instruction += '\nDo not condition generation on the existing reference; it is evidence only, not approved conditioning.'
            if note:
                instruction += '\nClarity proposal, not a newly confirmed defect: ' + note['direction']
            if case:
                instruction += '\nPilot composition: ' + case['framing']
            token = digest({'definition': row['definition_sha256'], 'instruction': instruction, 'settings': SETTINGS})
            seed = int(token[:8], 16) & 0x7fffffff
            check(re.fullmatch(r'WANDS-\d{6}', sku) is not None, 'Unsafe product identifier')
            filename = sku + '-hero-' + token[:16] + '.webp'
        plan.append({'root_sku': sku, 'selected_sku': contract['selected_sku'], 'product_name': contract['product_name'],
                     'definition_sha256': row['definition_sha256'], 'original_reference_evidence': copy.deepcopy(row['reference']),
                     'original_visual_status': row['visual_status'], 'proposed_action': action,
                     'focused_decision': copy.deepcopy(note), 'pilot_case': copy.deepcopy(case),
                     'draft_instruction': instruction, 'proposed_image_basename': filename, 'proposed_seed': seed,
                     'acceptance_contract': copy.deepcopy(contract), 'required_checks': list(CHECKS),
                     'status': 'awaiting_approval', 'reference_use_approved': False, 'executable': False})
    states = Counter(p['proposed_action'] for p in plan)
    repairs = len(plan) - states['retain_candidate']
    counts = {'review_roots': len(plan), 'focused_decisions': len(focused),
              'confirmed_repairs': states['repair_confirmed_defect'], 'clarity_repairs': states['clarify_hero'],
              'retained_candidates': states['retain_candidate'], 'proposed_repair_images': repairs,
              'pilot_images_proposed': len(pilot), 'deferred_repair_images': repairs - len(pilot),
              'images_generated': 0, 'model_calls': 0, 'live_writes': 0, 'images_accepted': 0}
    return plan, counts


def render_plan(plan, counts):
    def md(value):
        return re.sub(r'([\\`*_{}\[\]()<>#+!|])', r'\\\1', str(value))

    lines = ['# Corrected catalog hero-repair pilot', '', 'Status: Awaiting approval. No images have been generated.', '',
             f"{counts['review_roots']} reviewed roots: {counts['confirmed_repairs']} confirmed repairs, "
             f"{counts['clarity_repairs']} clarity improvements and {counts['retained_candidates']} retained candidates.", '',
             f"Proposed pilot: {counts['pilot_images_proposed']} new hero images, one attempt each. "
             f"The other {counts['deferred_repair_images']} repair candidates are deferred, not authorized.", '',
             '## Proposed run boundary', '',
             '- Local Mac only; existing FLUX.2 Klein 4B settings, 4-bit quantization, 768 by 768, four steps.',
             '- Text-only generation from corrected contracts. Existing references are evidence only and must not condition generation.',
             '- Use a new versioned media directory and fingerprinted basenames. Never overwrite an original or a previous candidate.',
             '- No retries, derivative views, imports, uploads, model-server changes or publication.',
             '- Stop after the listed pilot, then inspect every output against its own acceptance contract.',
             '- A pilot failure stops expansion for that challenge. No bulk run follows automatically.',
             '- This is a deliberately selected stress test, not a random sample or a catalog-wide quality estimate.', '',
             '## Pilot cases', '']
    for row in plan:
        if not row['pilot_case']:
            continue
        c = row['acceptance_contract']; case = row['pilot_case']
        lines += ['### ' + md(row['root_sku'] + ': ' + row['product_name']), '',
                  '**Challenge:** ' + md(case['challenge']), '', '**Selected options:** ' + md(json.dumps(c['selected_options'], sort_keys=True)),
                  '', '**Sale unit:** ' + md(c['sale_unit']), '', md(case['framing']), '']
        lines += ['- ' + md(str(p['quantity']) + ' x ' + p['label']) for p in c['components']]
        lines += ['', 'Reference evidence only: [existing local image](' + Path(row['original_reference_evidence']['path']).as_uri() + ').', '']
    lines += ['## Focused uncertainty dispositions', '',
              'These resolve the proposed next action, not image acceptance. The original triage evidence remains unchanged.', '']
    for row in plan:
        note = row['focused_decision']
        if note:
            lines += ['- **' + md(row['root_sku']) + ': ' + md(row['proposed_action']) + '.** ' + md(note['evidence']) + ' ' + md(note['direction'])]
    lines += ['', '## Acceptance before any expansion', '',
              'Every required check must be explicitly recorded against the actual candidate image SHA-256 and corrected-definition fingerprint. '
              'A generated or decodable file is not a pass. Pending, failed or uncertain checks block acceptance.', '']
    lines += ['- ' + key.replace('_', ' ').capitalize() + '.' for key in CHECKS]
    lines += ['', 'Compare apparent proportions with the synthetic design, but never claim exact size, fit, material certification or safety from pixels. '
              'Keep measurement and synthetic provenance disclosures in metadata, not printed into hero images.', '',
              'A separately approved run still needs a current model/runtime preflight and a bounded, hash-bound runner. '
              'These proposal files deliberately omit the legacy generator job fields and are not executable queues.', '']
    return '\n'.join(lines)


def build(review, decisions, selection, output):
    output = output.resolve()
    check(not output.exists(), 'Use a fresh repair-plan directory')
    rows, pins = verify_review_packet(review)
    payloads = []
    for path in (decisions, selection):
        raw = path.read_bytes(); data = json.loads(raw)
        check(isinstance(data, list), 'Decision and selection files must be arrays')
        pins[str(path.resolve())] = hashlib.sha256(raw).hexdigest()
        payloads.append(data)
    for path in (Path(__file__), Path(__file__).with_name('generate_images.py')):
        pins[str(path.resolve())] = sha256(path)
    plan, counts = make_plan(rows, *payloads)
    pilot = [row for row in plan if row['pilot_case']]
    acceptance = [{'root_sku': r['root_sku'], 'definition_sha256': r['definition_sha256'],
                   'proposed_image_basename': r['proposed_image_basename'], 'candidate_sha256': None,
                   'checks': {key: 'pending' for key in CHECKS}, 'verdict': 'pending',
                   'executable': False, 'publication_approved': False} for r in pilot]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.' + output.name + '-') as folder:
        stage = Path(folder)
        write_jsonl(stage / 'dispositions.proposed.jsonl', plan)
        write_jsonl(stage / 'pilot.proposed.jsonl', pilot)
        write_jsonl(stage / 'acceptance.pending.jsonl', acceptance)
        (stage / 'plan.md').write_text(render_plan(plan, counts))
        for path, expected in pins.items():
            check(sha256(Path(path)) == expected, 'Input changed during repair planning: ' + path)
        write_json(stage / 'manifest.json', {'version': VERSION, 'review_packet': str(review.resolve()), 'inputs': pins,
                   'outputs': {p.name: sha256(p) for p in sorted(stage.iterdir())}, 'counts': counts,
                   'proposed_settings': SETTINGS, 'executable': False, 'generation_authorized': False,
                   'deployment_ready': False, 'next_gate': 'Approve the exact bounded local pilot; no bulk expansion or publication implied.'})
        stage.rename(output)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', required=True, type=Path)
    parser.add_argument('--decisions', required=True, type=Path)
    parser.add_argument('--pilot-selection', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--json', action='store_true', help='Opt in to a terminal summary; otherwise use the sibling log')
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_name(args.output_dir.name + '.log'), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        counts = build(args.review, args.decisions, args.pilot_selection, args.output_dir)
        logging.info('Completed non-executable repair proposal: %s', json.dumps(counts, sort_keys=True))
        if args.json:
            print(json.dumps(counts, sort_keys=True, indent=2))
        return 0
    except Exception:
        logging.exception('Repair planning stopped; source packets and original images unchanged')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
