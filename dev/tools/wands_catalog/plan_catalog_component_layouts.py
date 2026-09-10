#!/usr/bin/env python3
"""Build CPU-only, count-checked component schematics. No images, model calls or executable jobs."""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
import logging
import math
from pathlib import Path
import re
import tempfile

from build_realism_review import write_json, write_jsonl
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from review_catalog_media_pilot import classify
from run_catalog_media_pilot import verify_pins
from verify_catalog_repairs import check

PROFILES = {'flat_lay', 'footprint', 'place_settings', 'shared_floor'}
EPS = .002


def dimensions(part, profile):
    d = part['dimensions_cm']
    x = d.get('lab_spec_width_cm')
    y = d.get('lab_spec_height_cm') if profile == 'shared_floor' else d.get('lab_spec_length_cm', d.get('lab_spec_depth_cm'))
    check(all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in (x, y)),
          'Missing or invalid component dimension: ' + part['component_id'])
    return x, y


def expand(contract):
    parts = contract['components']
    check(parts and len({p['component_id'] for p in parts}) == len(parts), 'Missing or duplicate component roles')
    instances = []
    for p in parts:
        check(re.fullmatch(r'[a-z0-9-]+', p['component_id']) is not None, 'Unsafe component ID')
        check(type(p['quantity']) is int and 0 < p['quantity'] <= 64, 'Invalid component quantity')
        check(type(p['counts_as_furniture']) is bool, 'Invalid component counting classification')
        for ordinal in range(1, p['quantity'] + 1):
            instances.append({'instance_id': p['component_id'] + '-' + str(ordinal).zfill(2),
                              'component_id': p['component_id'], 'ordinal': ordinal,
                              'label': p['label'], 'counts_as_furniture': p['counts_as_furniture']})
    check(len(instances) == contract['total_component_quantity'] and len(instances) <= 64,
          'Component sum differs from sale-unit contract or exceeds bounded layout size')
    return instances


def group_instances(instances, parts, profile):
    if profile == 'place_settings':
        repeated = {p['component_id'] for p in parts if p['quantity'] == 8}
        servers = {p['component_id'] for p in parts if p['quantity'] == 1}
        check(len(repeated) == 5 and len(servers) == 5 and len(parts) == 10,
              'Place-settings profile requires eight five-piece settings plus five servers')
        return [('Place setting ' + str(n), [s for s in instances if s['component_id'] in repeated and s['ordinal'] == n])
                for n in range(1, 9)] + [('Five serving utensils', [s for s in instances if s['component_id'] in servers])]
    if profile == 'shared_floor':
        return [('Shared floor plane', instances)]
    return [(str(i + 1).zfill(2) + ' · ' + s['label'], [s]) for i, s in enumerate(instances)]


def make_layout(row, selection):
    c = row['contract']; profile = selection['profile']
    check(row['verdict'] == 'fail', 'Only failed assortment candidates enter component layout planning')
    check(selection['root_sku'] == row['root_sku'] == c['root_sku'] and
          selection['definition_sha256'] == row['definition_sha256'] == digest(c), 'Stale layout selection or definition')
    check(profile in PROFILES, 'Unknown layout profile')
    instances = expand(c); parts = {p['component_id']: p for p in c['components']}
    checks = selection['component_checks']
    check(set(checks) == set(parts) and all(isinstance(v, list) and v and
          all(isinstance(s, str) and s.strip() for s in v) for v in checks.values()), 'Incomplete component-specific checks')
    groups = group_instances(instances, c['components'], profile)
    columns = 1 if profile == 'shared_floor' else 3 if profile == 'place_settings' else min(4, math.ceil(math.sqrt(len(groups))))
    cell_w = 940 / columns
    cell_h = 610 if profile == 'shared_floor' else 250
    gap = 6 if profile == 'place_settings' else 15
    metrics = []
    for _, members in groups:
        sizes = [dimensions(parts[s['component_id']], profile) for s in members]
        metrics.append((sum(x for x, _ in sizes) + gap * (len(sizes)-1), max(y for _, y in sizes)))
    scale = min(min((cell_w-42)/w, (cell_h-80)/h) for w, h in metrics)
    positioned = []; regions = []
    for i, ((label, members), (width, _)) in enumerate(zip(groups, metrics)):
        x = 30 + (i % columns) * cell_w; y = 55 + (i // columns) * cell_h
        cursor = x + (cell_w - width * scale) / 2
        baseline = y + cell_h - 38
        regions.append({'label': label, 'x': x, 'y': y, 'width': cell_w, 'height': cell_h,
                        'instance_ids': [s['instance_id'] for s in members]})
        for member in members:
            w, h = dimensions(parts[member['component_id']], profile)
            positioned.append({**member, 'box': {'x': round(cursor, 6), 'y': round(baseline-h*scale, 6),
                                               'width': round(w*scale, 6), 'height': round(h*scale, 6)}})
            cursor += (w+gap)*scale
    result = {'root_sku': row['root_sku'], 'product_name': c['product_name'], 'definition_sha256': row['definition_sha256'],
              'failed_candidate_sha256': row['image_sha256'], 'profile': profile,
              'canvas': {'width': 1000, 'height': 70 + math.ceil(len(groups)/columns)*cell_h},
              'pixels_per_synthetic_cm': scale, 'groups': regions, 'instances': positioned,
              'layout_note': selection['layout_note'], 'sale_unit': c['sale_unit'],
              'required_disclosure': c['required_disclosure'], 'executable': False,
              'reference_use_approved': False, 'generation_approved': False, 'publication_approved': False}
    validate_layout(result, c)
    return result


def validate_layout(layout, contract):
    check(layout['profile'] in PROFILES and layout['definition_sha256'] == digest(contract), 'Layout definition changed')
    expected = {s['instance_id']: s for s in expand(contract)}
    actual = layout['instances']
    check(len(actual) == len(expected) and {s['instance_id'] for s in actual} == set(expected),
          'Missing or duplicate physical instances')
    parts = {p['component_id']: p for p in contract['components']}
    scale = layout['pixels_per_synthetic_cm']
    check(type(scale) in (int, float) and math.isfinite(scale) and scale > 0, 'Invalid diagram scale')
    canvas = layout['canvas']
    check(all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in canvas.values()), 'Invalid canvas')
    for s in actual:
        check(all(s[k] == v for k, v in expected[s['instance_id']].items()), 'Instance identity or quantity changed')
        b = s['box']
        check(set(b) == {'x', 'y', 'width', 'height'} and all(type(v) in (int, float) and math.isfinite(v) for v in b.values()),
              'Invalid component envelope')
        check(b['x'] >= 0 and b['y'] >= 0 and b['width'] > 0 and b['height'] > 0 and
              b['x'] + b['width'] <= canvas['width'] + EPS and b['y'] + b['height'] <= canvas['height'] + EPS,
              'Component envelope is outside canvas')
        width, height = dimensions(parts[s['component_id']], layout['profile'])
        check(abs(b['width'] - width*scale) < EPS and abs(b['height'] - height*scale) < EPS,
              'Component envelope breaks common synthetic scale')
    for i, a in enumerate(actual):
        for b in actual[i+1:]:
            x, y = a['box'], b['box']
            check(min(x['x']+x['width'], y['x']+y['width']) - max(x['x'], y['x']) <= EPS or
                  min(x['y']+x['height'], y['y']+y['height']) - max(x['y'], y['y']) <= EPS, 'Component envelopes overlap')
    expected_groups = group_instances(list(expected.values()), contract['components'], layout['profile'])
    check([(g['label'], g['instance_ids']) for g in layout['groups']] ==
          [(label, [s['instance_id'] for s in members]) for label, members in expected_groups], 'Component grouping changed')
    if layout['profile'] == 'shared_floor':
        bottoms = [s['box']['y'] + s['box']['height'] for s in actual]
        check(max(bottoms) - min(bottoms) < EPS, 'Lamps no longer share a floor plane')
    check(all(layout[k] is False for k in ('executable', 'reference_use_approved', 'generation_approved', 'publication_approved')),
          'Schematic is not generation or image-use approval')


def component_briefs(row, selection, layout):
    briefs = []
    for p in row['contract']['components']:
        briefs.append({'root_sku': row['root_sku'], 'component_id': p['component_id'],
                       'asset_requirement_id': row['root_sku'] + '-' + p['component_id'] + '-' +
                           digest({'definition': row['definition_sha256'], 'component': p, 'profile': selection['profile']})[:12],
                       'definition_sha256': row['definition_sha256'], 'layout_sha256': digest(layout),
                       'component': p, 'selected_options': row['contract']['selected_options'],
                       'parent_product_name': row['contract']['product_name'],
                       'parent_specifications': row['contract'].get('specifications', {}),
                       'parent_constraints': row['contract']['constraints'],
                       'required_instances': p['quantity'],
                       'instance_ids': [s['instance_id'] for s in layout['instances'] if s['component_id'] == p['component_id']],
                       'draft_description': 'Exactly one complete ' + p['label'] + '. Isolated full object, no extra products or text. '
                           'Match the corrected synthetic component design and selected options; repeated positions reuse the same accepted component.',
                       'view': 'front elevation' if selection['profile'] == 'shared_floor' else 'orthographic top view',
                       'construction_checks': selection['component_checks'][p['component_id']],
                       'required_asset_checks': ['exactly one complete component', 'identity and selected appearance',
                           'coherent construction', 'full silhouette and clean mask', 'no text, logos or excluded items',
                           'consistent viewpoint, lighting and materials across this set'],
                       'required_disclosure': row['contract']['required_disclosure'],
                       'acceptance': 'pending', 'executable': False, 'reference_use_approved': False})
    return briefs


def read_review(packet):
    packet = packet.resolve(); m = json.loads((packet/'manifest.json').read_text())
    check(set(m['outputs']) == {'review.html', 'reviews.jsonl'} and
          {p.name for p in packet.iterdir()} == {'review.html', 'reviews.jsonl', 'manifest.json'}, 'Unexpected review packet')
    check(m['deployment_ready'] is False and m['publication_approved'] is False and m['bulk_generation_approved'] is False,
          'Expected an unapproved local visual review')
    pins = {**m['inputs'], str(packet/'manifest.json'): sha256(packet/'manifest.json'),
            **{str(packet/k): v for k, v in m['outputs'].items()}}
    verify_pins(pins)
    rows = read_jsonl(packet/'reviews.jsonl')
    check(len(rows) == len({r['root_sku'] for r in rows}) == m['counts']['reviewed'], 'Review scope differs')
    for r in rows:
        check(r['verdict'] == classify(r) and r['definition_sha256'] == digest(r['contract']), 'Review verdict or definition changed')
        check(pins.get(r['candidate_path']) == r['image_sha256'] and sha256(Path(r['candidate_path'])) == r['image_sha256'],
              'Candidate image is not pinned to review')
        check(all(r[k] is False for k in ('publication_approved', 'reference_use_approved', 'bulk_generation_approved')),
              'Unexpected candidate approval')
    check(all(sum(r['verdict'] == k for r in rows) == m['counts'][k] for k in ('pass', 'fail', 'uncertain')),
          'Review verdict counts differ')
    return rows, pins


def render_svg(layout):
    h = lambda v: escape(str(v), quote=True)
    colors = ['#d4e8f5', '#f9dcbd', '#d7e9d1', '#ecddf3', '#f7d5d5', '#f5edbb', '#cce9e3', '#dce1f4', '#ebdfcf', '#d9e5e7']
    roles = list(dict.fromkeys(s['component_id'] for s in layout['instances']))
    elements = ['<title>' + h(layout['product_name']) + ': component planning schematic</title>',
                '<text x="30" y="28" font-size="15" font-weight="700">SCHEMATIC ONLY · RECTANGLES ARE COMPONENT ENVELOPES, NOT PRODUCT SHAPES</text>']
    for group in layout['groups']:
        elements.append('<text x="' + h(group['x']+10) + '" y="' + h(group['y']+20) +
                        '" font-size="13">' + h(group['label']) + '</text>')
    for i, s in enumerate(layout['instances']):
        b = s['box']; color = colors[roles.index(s['component_id']) % len(colors)]
        elements.append('<g><title>' + h(s['instance_id'] + ': ' + s['label']) + '</title><rect class="component-envelope" ' +
                        ' '.join(k+'="'+h(v)+'"' for k, v in b.items()) + ' fill="'+color+'" stroke="#334b5d" stroke-width="1.5"/>' +
                        '<text x="'+h(b['x']+b['width']/2)+'" y="'+h(b['y']+b['height']+18)+'" text-anchor="middle" font-size="12">' +
                        str(i+1).zfill(2) + '</text></g>')
    c = layout['canvas']
    return '<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="'+h(layout['product_name']+' component schematic') +            '" viewBox="0 0 '+str(c['width'])+' '+str(c['height'])+'" style="font-family:system-ui,sans-serif">' + ''.join(elements) + '</svg>'


def render_html(layouts, briefs, coverage, counts):
    h = lambda v: escape(str(v), quote=True)
    cards = []
    for layout in layouts:
        sku = layout['root_sku']; items = [b for b in briefs if b['root_sku'] == sku]
        legend = ''.join('<tr><th scope="row">'+h(b['component']['label'])+'</th><td>'+str(b['required_instances']) +
                         '</td><td>'+h('; '.join(b['construction_checks']))+'</td></tr>' for b in items)
        cards.append('<article id="'+h(sku)+'"><p class="tag">'+h(sku)+' · '+h(layout['profile'].replace('_',' '))+
                     '</p><h2>'+h(layout['product_name'])+'</h2><p>'+h(layout['sale_unit'])+'</p><p>'+h(layout['layout_note']) +
                     '</p><div class="diagram">'+render_svg(layout)+'</div><p>'+str(len(layout['instances']))+
                     ' physical positions; '+str(len(items))+' distinct component requirements. No component assets exist yet.</p>' +
                     '<table><thead><tr><th>Component</th><th>Qty</th><th>Must be recognizable</th></tr></thead><tbody>'+legend+
                     '</tbody></table><details><summary>Position IDs and synthetic provenance</summary><ul>'+
                     ''.join('<li>'+str(i+1).zfill(2)+': '+h(s['instance_id'])+'</li>' for i,s in enumerate(layout['instances']))+
                     '</ul><p>'+h(layout['required_disclosure'])+'</p></details></article>')
    action_labels = {'retain_local_candidate_pending_use_approval': 'Keep local; image use not approved',
                     'focused_visual_clarity_review': 'Clarity review needed',
                     'construction_specific_repair_required': 'Construction-specific repair needed'}
    deferred = ''.join('<li><strong>'+h(r['root_sku'])+'</strong>: '+h(action_labels[r['action']])+'. '+h(r['reason'])+'</li>'
                       for r in coverage if r['action'] != 'component_layout_prepared')
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Catalog component layout workbench</title><style>
*{box-sizing:border-box}body{margin:0;background:#edf1f3;color:#192e3b;font:16px/1.55 system-ui,sans-serif}
main{max-width:1160px;margin:auto;padding:36px 24px}h1{font-size:clamp(2rem,4vw,3.2rem);line-height:1.15;max-width:950px}
h2{font-size:1.65rem;line-height:1.25}.tag{font-size:13px;letter-spacing:.05em;text-transform:uppercase}
article{background:white;border:1px solid #cfd9df;padding:28px;border-radius:12px;margin:28px 0;scroll-margin-top:20px}
.notice{background:#fff2cf;border-left:4px solid #93691b;padding:14px 18px}.stats{display:flex;gap:12px;flex-wrap:wrap}
.stats div{background:white;border:1px solid #cfd9df;padding:12px 20px;border-radius:10px}.stats strong{display:block;font-size:2rem}
.diagram{background:#f7fafc;border:1px solid #d8e1e6;margin:22px 0;overflow:auto}.diagram svg{display:block;width:100%;min-width:600px}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #d6dee3;text-align:left;vertical-align:top;padding:10px 8px}
details{margin-top:20px}summary,a{color:#145a8d}summary{cursor:pointer}nav{display:flex;gap:10px 20px;flex-wrap:wrap;margin:24px 0}
@media(max-width:700px){main{padding:20px 14px}article{padding:16px}table{font-size:12px}td,th{padding:8px 4px}}
</style></head><body><main><p class="tag">CPU-only catalog development · no new generation</p><h1>Count the pieces.<br>Keep each component distinct.</h1>
<p>Deterministic layouts for the failed multi-piece pilot cases. Every position maps to one component in its corrected synthetic sale unit.</p>
<div class="stats">""" + ''.join('<div><strong>'+str(counts[k])+'</strong>'+label+'</div>' for k,label in (
        ('layouts','assortment layouts'),('component_types','component types'),('physical_instances','physical positions'),
        ('model_calls','model calls'))) + """</div><p class="notice">Planning diagrams, not catalog images or approved model references.
Rectangles represent component envelopes only. Labels belong to this tool, never product photos. Correct slot counts do not prove
that future images contain the right objects or construction. All assets and final composites still require visual acceptance.</p>
<p>Each diagram uses one common scale from synthetic dimensions. Viewpoints are top-view envelope plans except the lamps' shared-floor
front elevation. These diagrams do not establish measurements, fit, assembly, safety or a physically installed arrangement.
On small screens, scroll inside a diagram to inspect its labels.</p><nav aria-label="Assortment layouts">""" + ''.join(
        '<a href="#'+h(l['root_sku'])+'">'+h(l['root_sku'])+'</a>' for l in layouts) + '</nav>' + ''.join(cards) +         '<section><h2>Outside this layout batch</h2><ul>'+deferred+'</ul></section></main></body></html>\n'


def build(review, selection, output):
    check(not output.exists() and not output.is_symlink(), 'Use a fresh component-layout directory')
    output = output.resolve()
    rows, pins = read_review(review); indexed = {r['root_sku']: r for r in rows}
    raw = selection.read_bytes(); choices = json.loads(raw)
    check(isinstance(choices, list) and 0 < len(choices) <= 5 and
          len({s['root_sku'] for s in choices}) == len(choices), 'Invalid or duplicate layout selection')
    pins[str(selection.resolve())] = hashlib.sha256(raw).hexdigest()
    pins[str(Path(__file__).resolve())] = sha256(Path(__file__))
    check(not any(Path(p).is_relative_to(output) for p in pins) and not output.is_relative_to(review.resolve()) and
          not output.is_relative_to(Path(json.loads((review/'manifest.json').read_text())['run'])),
          'Output cannot overlap source packets or media')
    layouts = []; briefs = []
    for choice in choices:
        check(choice['root_sku'] in indexed, 'Unknown selected root')
        row = indexed[choice['root_sku']]
        layout = make_layout(row, choice)
        layouts.append(layout); briefs.extend(component_briefs(row, choice, layout))
    selected = {l['root_sku'] for l in layouts}
    coverage = []
    for row in rows:
        action = 'component_layout_prepared' if row['root_sku'] in selected else {
            'pass':'retain_local_candidate_pending_use_approval', 'uncertain':'focused_visual_clarity_review',
            'fail':'construction_specific_repair_required'}[row['verdict']]
        coverage.append({'root_sku': row['root_sku'], 'definition_sha256': row['definition_sha256'],
                         'candidate_sha256': row['image_sha256'], 'existing_verdict': row['verdict'],
                         'action': action, 'reason': row['next_direction'], 'executable': False})
    counts = {'reviewed_scope': len(rows), 'layouts': len(layouts), 'component_types': len(briefs),
              'physical_instances': sum(len(l['instances']) for l in layouts), 'model_calls': 0,
              'new_catalog_images': 0, 'approved_assets': 0, 'outside_layout_batch': len(rows)-len(layouts)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.'+output.name+'-') as folder:
        stage = Path(folder)
        write_jsonl(stage/'layouts.proposed.jsonl', layouts)
        write_jsonl(stage/'component-briefs.proposed.jsonl', briefs)
        write_jsonl(stage/'coverage.jsonl', coverage)
        (stage/'review.html').write_text(render_html(layouts, briefs, coverage, counts))
        verify_pins(pins)
        write_json(stage/'manifest.json', {'version':'wands-component-layouts-v1', 'source_review':str(review.resolve()),
                   'inputs':pins, 'outputs':{p.name:sha256(p) for p in sorted(stage.iterdir())}, 'counts':counts,
                   'executable':False, 'generation_approved':False, 'publication_approved':False,
                   'next_gate':'Review component geometry and approve an exact asset pilot before any additional generation.'})
        stage.rename(output)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', required=True, type=Path)
    parser.add_argument('--selection', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--json', action='store_true', help='Opt in to a terminal summary')
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_name(args.output_dir.name+'.log'), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        counts = build(args.review, args.selection, args.output_dir)
        logging.info('Completed component layout planning: %s', json.dumps(counts, sort_keys=True))
        if args.json:
            print(json.dumps(counts, indent=2, sort_keys=True))
        return 0
    except Exception:
        logging.exception('Component layout planning stopped; no images, model calls or approvals changed')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
