#!/usr/bin/env python3
"""Build a CPU-only media review packet from verified catalog definitions.

This is neither a generation queue nor a media import. No model, network service,
credential, original image write or automatic visual approval is involved.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import logging
import math
import tempfile
import warnings
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, __version__ as PILLOW_VERSION
from build_realism_review import unique_index, write_json, write_jsonl
from catalog_depth import ATTRIBUTES
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from repair_designs import DISCLOSURE
from synthetic_dimensions import LABEL
from verify_catalog_repairs import check, verify_packet

VERSION = 'wands-media-reconciliation-v2'
VIEWS = {'hero', 'angle', 'detail', 'room', 'dimensions'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def inspect_reference(reference):
    """Decode existing bytes only. A valid JPEG is not an accepted product photo."""
    result = {'status': 'missing_reference', 'visual_acceptance': False}
    if not reference:
        return result
    path = Path(reference['path'])
    if not path.is_file():
        return {**result, 'status': 'missing_file'}
    result.update(bytes=path.stat().st_size, sha256=sha256(path))
    if result['sha256'] != reference['sha256']:
        return {**result, 'status': 'hash_mismatch'}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
                result.update(width=image.width, height=image.height, format=image.format,
                              mode=image.mode, frames=getattr(image, 'n_frames', 1))
        if result['format'] not in {'JPEG', 'PNG', 'WEBP'} or result['frames'] != 1:
            return {**result, 'status': 'unsupported_image'}
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return {**result, 'status': 'decode_failed'}
    return {**result, 'status': 'valid_image_bytes',
            'resolution_warning': min(result['width'], result['height']) < 512}


def dimensions(specifications):
    result = {code: fact['value'] for code, fact in specifications.items()
              if ATTRIBUTES[code]['kind'] == 'length'}
    check(all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in result.values()),
          'Invalid media-contract dimension')
    return result


def make_contract(root, children, review):
    """Bind exact current option values, not historical tokens in retained SKUs."""
    indexed = unique_index([root, *children], 'sku')
    target = review['selected_sku']
    check(review['root_sku'] == root['sku'] and target == root['gallery_target']['sku'], 'Review target mismatch')
    check(target in indexed, 'Selected media target is absent')
    chosen = indexed[target]
    check(chosen.get('parent_sku', root['sku']) == root['sku'] and
          chosen['source_product_id'] == root['source_product_id'], 'Selected target belongs to another family')
    check(target != root['sku'] or root['kind'] == 'simple', 'Select a child, not a configurable parent range')
    check(review['selected_options'] == chosen['variant_options'] == root['gallery_target']['options'], 'Selected options changed')
    check(review['reference'] == chosen.get('reference'), 'Selected reference changed')
    check(review['sale_unit'] == chosen['catalog_fields']['lab_sale_unit'], 'Selected sale unit changed')
    check(review['design'] == chosen['dimension_design'], 'Selected design changed')
    check(review['executable'] is False, 'Executable reference review')
    design = chosen['dimension_design']
    check(design['status'] in {'synthetic_design_complete', 'synthetic_components_complete'}, 'Incomplete media design')
    components = []
    for part in design.get('components', []):
        check(type(part['quantity']) is int and part['quantity'] > 0, 'Invalid component quantity')
        measure = dimensions(part['specifications'])
        check(len(measure) >= 2, 'Incomplete component geometry')
        components.append({key: copy.deepcopy(part[key]) for key in
                           ('component_id', 'label', 'quantity', 'scope', 'counts_as_furniture')})
        components[-1].update(dimensions_cm=measure, specifications=copy.deepcopy(part['specifications']),
                              composition_synthetic=part['composition_synthetic'],
                              composition_evidence=copy.deepcopy(part['composition_evidence']))
    unique_index(components, 'component_id')
    if components:
        check(sum(c['quantity'] for c in components) == design['total_component_quantity'], 'Component quantity total differs')
        if design.get('furniture_piece_count') is not None:
            check(sum(c['quantity'] for c in components if c['counts_as_furniture']) == design['furniture_piece_count'],
                  'Furniture quantity differs from assortment')
    measure = dimensions(chosen['specifications'])
    check(bool(components) or len(measure) >= 2, 'Incomplete product geometry')
    constraints = [
        'Use the selected option fields, never infer options from historical SKU tokens.',
        'Show exactly the sale unit; do not add matching furniture, accessories or unlisted components.',
        'The reference is unapproved for this corrected definition. Reconcile identity, finish, shape and quantity before using it.',
        'Never infer exact dimensions from pixels. Review proportions against the explicit synthetic design; this does not prove physical size or fit.',
        'No people, logos, watermarks, marketing text, certification marks or invented performance features.',
        'No manufacturer, fit, installation, capacity or safety claims. Preserve synthetic provenance in media metadata.',
    ]
    if components:
        constraints += ['Show every listed component in a countable arrangement. Fitted upholstery is not an extra furniture piece.',
                        'Component dimensions describe individual items, never a combined arrangement width.']
    if 'nursery' in root['name'].casefold() or 'Crib Bedding' in root['source_class']:
        constraints.append('No infant, crib, mattress or in-use sleeping arrangement. Display nursery-decor components laid out separately.')
    return {'root_sku': root['sku'], 'selected_sku': target, 'product_name': root['name'],
            'selected_name': chosen['name'], 'source_product_id': root['source_product_id'],
            'selected_options': copy.deepcopy(chosen['variant_options']), 'sale_unit': review['sale_unit'],
            'dimension_scope': design['scope'], 'dimensions_cm': measure,
            'specifications': copy.deepcopy(chosen['specifications']), 'components': components,
            'total_component_quantity': design.get('total_component_quantity'),
            'furniture_piece_count': design.get('furniture_piece_count'),
            'required_disclosure': DISCLOSURE + ' ' + LABEL + '.', 'constraints': constraints,
            'resolution_basis': root['repair']['rationale']}


def draft_prompt(contract, finding):
    lines = ['DRAFT ONLY. Generation requires a separate reviewed plan and explicit authorization.',
             'After approval, prepare a realistic studio hero photograph for the following fictional lab product.',
             'Product: ' + contract['product_name'] + '.',
             'Selected options: ' + json.dumps(contract['selected_options'], sort_keys=True) + '.',
             'Exact sale unit: ' + contract['sale_unit'] + '.',
             'Accepted catalog facts and explicitly synthetic options: ' + json.dumps(
                 {k: {'value': v['value'], 'synthetic': v['synthetic']} for k, v in contract['specifications'].items()
                  if k not in contract['dimensions_cm']}, sort_keys=True) + '.',
             'Use a neutral background and clear separation of the included items; no decorative staging props.']
    if contract['components']:
        parts = [{k: c[k] for k in ('component_id', 'label', 'quantity', 'scope', 'dimensions_cm', 'counts_as_furniture')}
                 for c in contract['components']]
        lines.append('Exact component manifest: ' + json.dumps(parts, sort_keys=True) + '.')
        lines.append('Total listed items: ' + str(contract['total_component_quantity']) +
                     '; furniture count (if applicable): ' + str(contract['furniture_piece_count']) + '.')
    else:
        lines.append('Explicit design dimensions in cm: ' + json.dumps(contract['dimensions_cm'], sort_keys=True) +
                     '. Scope: ' + contract['dimension_scope'] + '.')
    if finding:
        if finding.get('verdict', 'fail') == 'uncertain':
            lines += ['Review uncertainty, not a confirmed defect: ' + finding['finding'],
                      'This is not an instruction to regenerate. First resolve the focused visual review.',
                      'Conditional review/repair direction: ' + finding['prompt']]
        else:
            lines += ['Confirmed reference defect: ' + finding['finding'], 'Existing reviewed repair direction: ' + finding['prompt']]
    lines += contract['constraints']
    lines += ['Do not print dimensions or disclosures onto this hero photograph; retain them in accompanying metadata.',
              contract['required_disclosure']]
    return '\n'.join(lines)


def prepare_reviews(roots, children, reviews, drafts, supplemental=()):
    changed = {r['sku']: r for r in roots if r.get('repair')}
    indexed = unique_index(reviews, 'root_sku'); findings = unique_index(drafts, 'root_sku')
    check(set(indexed) == set(changed), 'Reference review scope differs from corrected roots')
    check(set(findings) <= set(indexed), 'Visual finding lies outside review scope')
    extra = unique_index(supplemental, 'root_sku')
    check(set(extra) <= set(indexed) and not set(extra) & set(findings), 'Supplemental finding scope overlaps or is unknown')
    groups = defaultdict(list)
    for child in children:
        groups[child['parent_sku']].append(child)
    result = []
    for sku, root in sorted(changed.items()):
        review = indexed[sku]; finding = findings.get(sku)
        contract = make_contract(root, groups[sku], review)
        if sku in extra:
            note = extra[sku]
            check(note['verdict'] in {'fail', 'uncertain'}, 'Supplemental findings cannot grant visual approval')
            check(note['selected_sku'] == review['selected_sku'] and review['reference'] and
                  note['reference_sha256'] == review['reference']['sha256'] and
                  note['definition_sha256'] == digest(contract), 'Supplemental finding reference or definition changed')
            check(all(isinstance(note[k], str) and note[k].strip() for k in ('finding', 'repair_direction', 'observation')),
                  'Supplemental finding lacks evidence or repair direction')
            finding = {key: copy.deepcopy(review[key]) for key in ('root_sku', 'selected_sku', 'reference', 'design')}
            finding.update(finding=note['finding'], prompt=note['repair_direction'], observation=note['observation'],
                           definition_sha256=note['definition_sha256'], verdict=note['verdict'], executable=False)
        if finding:
            check(all(finding[key] == review[key] for key in ('reference', 'selected_sku', 'design')),
                  'Visual finding is stale for this reference or selected design')
            check(finding['executable'] is False, 'Executable visual finding')
        integrity = inspect_reference(review['reference'])
        failed = finding is not None and finding.get('verdict', 'fail') == 'fail'
        uncertain = finding is not None and finding.get('verdict') == 'uncertain'
        priority = 0 if failed or integrity['status'] != 'valid_image_bytes' else 1 if uncertain or root['repair'].get('source_resolution') else 2
        result.append({'brief_id': sku + ':corrected-hero-review', 'priority': priority,
                       'contract': contract, 'definition_sha256': digest(contract),
                       'reference': copy.deepcopy(review['reference']), 'integrity': integrity,
                       'visual_status': 'known_reference_defect' if failed else 'reviewed_uncertain' if uncertain else 'not_reviewed_for_corrected_definition',
                       'next_action': 'reference_repair_review' if failed else 'focused_visual_design_review' if uncertain else 'initial_visual_review',
                       'finding': copy.deepcopy(finding), 'draft_prompt': draft_prompt(contract, finding),
                       'status': 'requires_visual_reconciliation', 'executable': False,
                       'reference_use_approved': False, 'images_generated': 0, 'model_calls': 0})
    return sorted(result, key=lambda r: (r['priority'], r['contract']['root_sku']))


def triage_counts(reviews):
    states = Counter(r['visual_status'] for r in reviews)
    check(set(states) <= {'known_reference_defect', 'reviewed_uncertain', 'not_reviewed_for_corrected_definition'},
          'Unknown visual status; no implicit approval is allowed')
    return {'known_reference_defects': states['known_reference_defect'],
            'reviewed_uncertain_references': states['reviewed_uncertain'],
            'visually_reviewed_roots': states['known_reference_defect'] + states['reviewed_uncertain'],
            'not_visually_reviewed_roots': states['not_reviewed_for_corrected_definition']}


def blocked_views(briefs, reviews):
    roots = {r['contract']['source_product_id']: r for r in reviews}
    result = []; seen = defaultdict(set)
    for brief in briefs:
        review = roots.get(brief['source_product_id'])
        if not review:
            continue
        check(brief['sku'] == review['contract']['selected_sku'], 'Gallery brief targets a stale variant')
        check(brief['view'] in VIEWS and brief['view'] not in seen[brief['sku']], 'Unexpected or duplicate gallery view')
        check(brief['selected_options'] == review['contract']['selected_options'], 'Gallery options differ from media contract')
        check(brief['executable'] is False, 'Executable gallery brief')
        seen[brief['sku']].add(brief['view'])
        result.append({'job_id': brief['job_id'], 'view': brief['view'], 'root_sku': review['contract']['root_sku'],
                       'selected_sku': brief['sku'], 'requires_brief_id': review['brief_id'],
                       'definition_sha256': review['definition_sha256'], 'executable': False,
                       'status': 'blocked_until_corrected_hero_and_design_are_visually_accepted'})
    check(len(seen) == len(reviews) and all(views == VIEWS for views in seen.values()), 'Incomplete gallery dependency coverage')
    return sorted(result, key=lambda r: r['job_id'])


def render_review(reviews, counts):
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for row in reviews:
        c = row['contract']; ref = row['reference']
        options = ', '.join(f'{k}: {v}' for k, v in c['selected_options'].items()) or 'Single design; no options'
        image = ('<a href="' + esc(Path(ref['path']).as_uri()) + '"><img loading="lazy" src="' +
                 esc(Path(ref['path']).as_uri()) + '" alt="Unapproved reference for ' + esc(c['product_name']) + '"></a>') if ref else '<p>No reference</p>'
        parts = '<ul>' + ''.join('<li>' + esc(f"{p['quantity']} × {p['label']}") + '</li>' for p in c['components']) + '</ul>' if c['components'] else ''
        known = ''
        if row['finding']:
            uncertain = row['visual_status'] == 'reviewed_uncertain'
            known = '<p class="' + ('uncertain' if uncertain else 'alert') + '">' + ('Review uncertainty: ' if uncertain else 'Confirmed defect: ') + esc(row['finding']['finding']) + '</p>'
        cards.append('<article id="' + esc(c['root_sku']) + '"><p class="eyebrow">Priority ' + str(row['priority']) +
                     ' · ' + esc(c['root_sku']) + '</p><h2>' + esc(c['product_name']) + '</h2>' + image +
                     '<p class="badge">Not visually accepted</p><p class="options">' + esc(options) + '</p><p>' +
                     esc(c['sale_unit']) + '</p>' + parts + known + '<p class="technical">File check: ' + esc(row['integrity']['status']) +
                     '. This checks bytes, not product correctness.</p><details><summary>Design, evidence and repair brief</summary><p>' +
                     esc(c['required_disclosure']) + '</p><p>Selected SKU: ' + esc(c['selected_sku']) +
                     '</p><pre>' + esc(json.dumps(c, indent=2, ensure_ascii=False)) + '</pre><h3>Draft instruction</h3><pre>' +
                     esc(row['draft_prompt']) + '</pre><p>Definition fingerprint: ' + esc(row['definition_sha256']) + '</p></details></article>')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Corrected catalog media review</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f4f1;color:#202b29;font:16px/1.5 system-ui,sans-serif}
header,main,footer{max-width:1660px;margin:auto;padding:24px}header{padding-top:40px}h1{font-size:36px;line-height:1.15;margin:0 0 16px}
h2{font-size:20px;line-height:1.3;margin:8px 0 18px}h3{font-size:17px}header p{max-width:1000px}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px;align-items:start}article{padding:22px;background:white;border:1px solid #cdd5cf;border-radius:12px;min-width:0}
article img{width:100%;height:260px;object-fit:contain;background:#f8f8f7}p,li,summary{overflow-wrap:anywhere}.eyebrow{font-size:13px;color:#50625a;margin:0}.badge{display:inline-block;font-size:13px;color:#784305;background:#fff0ca;padding:4px 9px;border-radius:4px;margin:8px 0}
.options{font-weight:650}.alert{background:#fff0e7;border-left:3px solid #a54216;padding:12px}.uncertain{background:#f0f2fb;border-left:3px solid #596898;padding:12px}.technical{font-size:13px;color:#56625d}details{border-top:1px solid #dce1dc;padding-top:12px}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 ui-monospace,monospace;background:#f5f6f3;padding:12px}ul{padding-left:22px}
@media(max-width:1050px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.grid{grid-template-columns:1fr}header,main,footer{padding:16px}h1{font-size:28px}article{padding:18px}}
</style></head><body><header><h1>Corrected catalog media review</h1><p>''' + esc(counts['review_roots']) + ' corrected product roots · ' + esc(counts['known_reference_defects']) + ' confirmed defects · ' + esc(counts.get('reviewed_uncertain_references', 0)) + ' reviewed but uncertain · ' + esc(counts.get('not_visually_reviewed_roots', counts['review_roots'] - counts['known_reference_defects'])) + ' not visually reviewed.</p><p>' + esc(counts['technically_valid_references']) + ' decodable references · ' + esc(counts['blocked_gallery_views']) + ''' gallery views held for reconciliation.</p>
<p>Review-only, local and CPU-only. No images generated, copied, accepted or uploaded. Existing image approvals are not carried over to changed definitions. Priority 0 covers confirmed defects and invalid files; priority 1 covers uncertain reviews or newly resolved definitions still awaiting review. Uncertainty is not a failure, approval or automatic regeneration instruction.</p>
<p>Compare the image to the selected options and exact assortment below it. Never infer exact dimensions from pixels. Each card links to the existing reference; the image is not a depiction we have accepted for the corrected design.</p></header><main class="grid">''' + ''.join(cards) + '''</main><footer>Images remain outside Git. These are explicitly synthetic lab designs, not manufacturer-verified products. No Magento import or deployment is included.</footer></body></html>'''


def build(definitions, output, findings_paths=()):
    definitions = definitions.resolve(); output = output.resolve()
    check(not output.exists(), 'Use a fresh media review directory')
    verified = verify_packet(definitions)
    manifest_path = definitions / 'manifest.json'
    source = json.loads(manifest_path.read_text())
    roots = read_jsonl(definitions / 'candidate-products.jsonl')
    children = read_jsonl(definitions / 'candidate-children.jsonl')
    supplemental = []; supplemental_inputs = {}
    for path in findings_paths:
        raw = path.read_bytes()
        notes = json.loads(raw)
        check(isinstance(notes, list), 'Supplemental observations must be a JSON array')
        supplemental.extend(notes)
        supplemental_inputs[str(path.resolve())] = hashlib.sha256(raw).hexdigest()
    reviews = prepare_reviews(roots, children, read_jsonl(definitions / 'reference-review.jsonl'),
                              read_jsonl(definitions / 'image-repair-drafts.jsonl'),
                              supplemental)
    views = blocked_views(read_jsonl(definitions / 'gallery-briefs.jsonl'), reviews)
    duplicates = defaultdict(list)
    for row in reviews:
        if row['reference']:
            duplicates[row['reference']['sha256']].append(row['contract']['root_sku'])
    duplicate_groups = [sorted(skus) for _, skus in sorted(duplicates.items()) if len(skus) > 1]
    counts = {'review_roots': len(reviews), 'technically_valid_references': sum(r['integrity']['status'] == 'valid_image_bytes' for r in reviews),
              **triage_counts(reviews),
              'newly_resolved_definition_roots': sum(bool(r.get('repair', {}).get('source_resolution')) for r in roots),
              'component_assortment_roots': sum(bool(r['contract']['components']) for r in reviews),
              'blocked_gallery_views': len(views), 'duplicate_image_groups': len(duplicate_groups),
              'priority_counts': dict(sorted(Counter(str(r['priority']) for r in reviews).items())),
              'integrity_status_counts': dict(sorted(Counter(r['integrity']['status'] for r in reviews).items())),
              'visually_accepted_references': 0, 'model_calls': 0, 'images_generated': 0, 'live_writes': 0}
    inputs = {str(manifest_path): sha256(manifest_path),
              **{str(definitions / name): value for name, value in source['outputs'].items()},
              str(Path(__file__).resolve()): sha256(Path(__file__)),
              str(Path(__file__).with_name('verify_catalog_repairs.py').resolve()): sha256(Path(__file__).with_name('verify_catalog_repairs.py'))}
    # The source manifest also pins producer dependencies and every original reference.
    inputs.update(source['inputs'])
    inputs.update(supplemental_inputs)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.' + output.name + '-') as folder:
        stage = Path(folder)
        write_jsonl(stage / 'hero-review-drafts.jsonl', reviews)
        write_jsonl(stage / 'gallery-dependencies.jsonl', views)
        write_json(stage / 'image-integrity.json', {'counts': counts, 'exact_duplicate_root_groups': duplicate_groups,
                                                  'checks': [{'root_sku': r['contract']['root_sku'], 'reference': r['reference'],
                                                              **r['integrity']} for r in reviews]})
        write_json(stage / 'definition-verification.json', verified)
        (stage / 'review.html').write_text(render_review(reviews, counts))
        # Verify inputs again before publishing the immutable local artifact.
        for path, expected in inputs.items():
            check(sha256(Path(path)) == expected, 'Input changed during media reconciliation: ' + path)
        manifest = {'version': VERSION, 'definition_packet': str(definitions), 'inputs': inputs,
                    'outputs': {p.name: sha256(p) for p in sorted(stage.iterdir())}, 'counts': counts,
                    'pillow_version': PILLOW_VERSION, 'executable': False, 'deployment_ready': False,
                    'existing_visual_approvals_reused': False,
                    'next_gate': 'Review corrected hero identity/options/counts, then approve a separate bounded generation plan.'}
        write_json(stage / 'manifest.json', manifest)
        stage.rename(output)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--definitions', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--findings', type=Path, action='append', default=[],
                        help='JSON array of byte- and definition-bound failures or uncertainties; repeat for separate review batches, never approvals')
    parser.add_argument('--json', action='store_true', help='Opt in to terminal summary; default output is the sibling log')
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_name(args.output_dir.name + '.log'), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        counts = build(args.definitions, args.output_dir, args.findings)
        logging.info('Completed CPU-only media reconciliation: %s', json.dumps(counts, sort_keys=True))
        if args.json:
            print(json.dumps(counts, indent=2, sort_keys=True))
        return 0
    except Exception:
        logging.exception('Media reconciliation stopped; definitions and original images unchanged')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
