#!/usr/bin/env python3
"""Build an immutable catalog-depth pilot. No imports, model calls or benchmark mutation."""
from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import math
import re
import tempfile
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

from prepare_catalog import department, parse_features, sha256, stable_fraction
from build_realism_review import DEPARTMENTS, CLAIM_PATTERN, read_csv, unique_index, write_json, write_jsonl
from synthetic_dimensions import add_dimensions, summarize_family, validate_dimensions, source_context, repair_proposals, LABEL as DIMENSION_LABEL, VERSION as DIMENSION_VERSION

SCHEMA_PATH = Path(__file__).resolve().parents[3] / 'app/code/RocketWeb/LabCatalog/etc/depth_attributes.json'
SCHEMA = json.loads(SCHEMA_PATH.read_text())
VERSION = SCHEMA['version']
ATTRIBUTES = SCHEMA['attributes']
GEOMETRY_AXES = {'wands_size', 'wands_length', 'wands_seat_height', 'wands_seating_capacity', 'wands_piece_count', 'wands_light_count', 'wands_pack_size'}
OPTION_FIELDS = {'color': 'lab_spec_color', 'wands_material': 'lab_spec_material', 'wands_finish': 'lab_spec_finish'}
COMPLEMENTS = {
    'sofas': {'coffee & cocktail tables', 'end tables', 'table lamps', 'accent pillows'},
    'loveseats': {'end tables', 'table lamps', 'accent pillows'},
    'accent chairs': {'end tables', 'floor lamps', 'accent pillows'},
    'desks': {'table lamps', 'bookcases'},
    'beds': {'nightstands', 'table lamps'},
    'nightstands': {'table lamps'},
    'coffee & cocktail tables': {'table lamps', 'decorative objects'},
    'dining tables': {'dining linens', 'serving dishes & platters', 'candle holders'},
    'area rugs': {'accent pillows', 'curtains & drapes'},
    'patio sofas': {'patio tables', 'planters'},
    'patio lounge chairs': {'patio tables', 'planters'},
}


def length_cm(raw):
    value = raw.casefold().strip().replace('″', ' in').replace('′', ' ft').replace("''", ' in').replace('"', ' in').replace("'", ' ft')
    number = r'(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)'
    def numeric(v):
        return sum(float(Fraction(part)) for part in v.split())
    mixed = re.fullmatch(rf'({number})\s*(?:ft|feet)\s+({number})\s*(?:in|inches|inch)', value)
    if mixed:
        result = numeric(mixed[1]) * 30.48 + numeric(mixed[2]) * 2.54
    else:
        match = re.fullmatch(rf'({number})\s*(cm|mm|m|in|inch|inches|ft|feet)', value)
        if not match:
            raise ValueError('explicit unambiguous unit required')
        result = numeric(match[1]) * {'cm':1,'mm':.1,'m':100,'in':2.54,'inch':2.54,'inches':2.54,'ft':30.48,'feet':30.48}[match[2]]
    if not math.isfinite(result) or not 0 < result <= 10000:
        raise ValueError('measurement outside pilot bounds')
    return round(result, 4)


def normalize(raw, rule):
    value = ' '.join(raw.split())
    if not value or CLAIM_PATTERN.search(value) or re.search(r'[<>]', value):
        raise ValueError('empty, markup or restricted claim')
    if rule['kind'] == 'length':
        return length_cm(value)
    if rule['kind'] == 'select':
        options = {v.casefold(): v for v in rule['options']}
        value = rule.get('synonyms', {}).get(value.casefold(), value)
        if value.casefold() not in options:
            raise ValueError('outside controlled vocabulary')
        return options[value.casefold()]
    if len(value) > 1000 or value.casefold() in {'n/a', 'unknown', 'null'}:
        raise ValueError('invalid text')
    return value


def extract_specs(row, axes=frozenset(), options=None):
    features = parse_features(row.get('product_features', ''))
    facts, withheld = {}, []
    for code, rule in ATTRIBUTES.items():
        values = [{'key': key, 'raw': value} for key in rule['aliases'] for value in features.get(key, [])]
        title_axes = {'lab_spec_width_cm':'wide|width','lab_spec_depth_cm':'deep|depth',
                      'lab_spec_height_cm':'high|height|tall','lab_spec_length_cm':'long|length'}
        title_values = []
        if code in title_axes:
            pattern = r'(?<![\d./-])(\d+(?:\.\d+)?)\s*-?\s*(inches|inch|in\b|cm\b|mm\b|ft\b|feet|\x22|\x27\x27|″)\s*[- ]*(' + title_axes[code] + r')\b'
            for match in re.finditer(pattern,row.get('product_name',''),re.I):
                title_values.append({'key':'product_name','raw':match[1]+' '+match[2], 'matched_text':match[0]})
            values += title_values
        if not values:
            continue
        if set(rule['varied_by']) & set(axes) or (rule['kind'] == 'length' and set(axes) & GEOMETRY_AXES):
            withheld.append({'attribute': code, 'reason': 'varies_by_family_axis', 'evidence': values})
            continue
        try:
            normalized = []
            for value in values:
                try:
                    normalized.append(normalize(value['raw'], rule))
                except ValueError:
                    if rule['kind'] != 'length' or not re.fullmatch(r'\d+(?:\.\d+)?',value['raw']):
                        raise
                    matches = [v for v in title_values if float(v['raw'].split()[0]) == float(value['raw'])]
                    resolved = {normalize(v['raw'],rule) for v in matches}
                    if len(resolved) != 1:
                        raise ValueError('unitless value lacks unique matching title evidence')
                    normalized.append(next(iter(resolved)))
            if len(set(normalized)) != 1:
                raise ValueError('conflicting source values')
            facts[code] = {'value': normalized[0], 'synthetic': False, 'origin': 'WANDS product_features', 'evidence': values}
        except (ValueError, ZeroDivisionError) as error:
            withheld.append({'attribute': code, 'reason': str(error), 'evidence': values})
    for axis, value in (options or {}).items():
        code = OPTION_FIELDS.get(axis)
        if code and axis in axes:
            try:
                facts[code] = {'value': normalize(value, ATTRIBUTES[code]), 'synthetic': True,
                               'origin': 'existing generated variant option', 'evidence': [{'key': axis, 'raw': value}]}
            except ValueError as error:
                withheld.append({'attribute': code, 'reason': str(error), 'evidence': [{'key': axis, 'raw': value}]})
    return facts, withheld


def select_pilot(rows, families, count=300, departments=DEPARTMENTS):
    if count <= 0 or count % len(departments):
        raise ValueError('Pilot count must be a positive multiple of department count')
    quota = count // len(departments)
    selected = []
    for dept in departments:
        classes = defaultdict(list)
        for row in rows:
            if department(row) == dept and row.get('product_class', '').strip():
                classes[row['product_class']].append(row)
        if sum(map(len, classes.values())) < quota:
            raise ValueError('Insufficient candidates for department: ' + dept)
        # Prefer configurable roots inside each class, while retaining class diversity.
        for pool in classes.values():
            pool.sort(key=lambda r: (r['product_id'] not in families, stable_fraction(r['product_id'], VERSION + ':pilot')))
        order = sorted(classes, key=lambda c: stable_fraction(c, VERSION + ':class:' + dept))
        group = []
        # Fill from configurable families first, round-robin across their classes.
        while len(group) < quota:
            before = len(group)
            for cls in order:
                if classes[cls] and classes[cls][0]['product_id'] in families and len(group) < quota:
                    group.append(classes[cls].pop(0))
            if len(group) == before:
                break
        while len(group) < quota:
            for cls in order:
                if classes[cls] and len(group) < quota:
                    group.append(classes[cls].pop(0))
        selected.extend(group)
    return selected


def tokens(value):
    return {part.strip().casefold() for part in value.split('|') if part.strip()}


def shared_evidence(a, b):
    matches = []
    for code in ('lab_spec_style', 'lab_spec_color', 'lab_spec_finish', 'lab_spec_material'):
        x, y = a['specifications'].get(code), b['specifications'].get(code)
        if x and y and not x['synthetic'] and not y['synthetic'] and x['value'] == y['value']:
            matches.append({'attribute':code, 'value':x['value']})
    # Material alone is not evidence of a coordinated appearance.
    return matches if any(m['attribute'] != 'lab_spec_material' for m in matches) else []


def recommend(current, candidates):
    result = {'alternatives': [], 'complements': []}
    classes = tokens(current['source_class'])
    allowed = set().union(*(COMPLEMENTS.get(c, set()) for c in classes))
    for other in candidates:
        if other['sku'] == current['sku'] or other['source_product_id'] == current['source_product_id'] or not other['salable']:
            continue
        matches = shared_evidence(current, other)
        if not matches:
            continue
        other_classes = tokens(other['source_class'])
        current_kids = current['department'] == 'Baby & Kids' or bool(re.search(r'\bkids|\bcrib|\btoddler',current['source_class'],re.I))
        other_kids = other['department'] == 'Baby & Kids' or bool(re.search(r'\bkids|\bcrib|\btoddler',other['source_class'],re.I))
        if current_kids != other_kids:
            continue
        ratio = other['price'] / current['price']
        kind = None
        if classes == other_classes and current['department'] == other['department'] and .65 <= ratio <= 1.5:
            kind = 'alternatives'
        elif other_classes & allowed and other['price'] <= current['price'] * 1.5:
            kind = 'complements'
        if kind:
            result[kind].append({'target_sku':other['sku'], 'shared_evidence':matches, 'price':other['price'],
                                 'review_required':True, 'compatibility_claim':False,
                                 'reason':'Same product class and shared appearance' if kind=='alternatives' else 'Complementary product role and shared appearance'})
    for kind in result:
        result[kind].sort(key=lambda r: (-len(r['shared_evidence']), abs(r['price']-current['price']), r['target_sku']))
        result[kind] = result[kind][:3]
    return result


def gallery_briefs(record):
    specs = {code: fact['value'] for code, fact in record['specifications'].items()}
    dimensions = {code: value for code, value in specs.items() if ATTRIBUTES[code]['kind'] == 'length'}
    dimension_provenance = {code: record['specifications'][code] for code in dimensions}
    components = record.get('dimension_design',{}).get('components',[])
    component_dimensions = [{'component_id':c['component_id'],'label':c['label'],'quantity':c['quantity'],
                             'scope':c['scope'],'dimensions_cm':{k:f['value'] for k,f in c['specifications'].items()},
                             'provenance':c['specifications'],'composition_evidence':c['composition_evidence']} for c in components]
    has_dimensions = len(dimensions)>=2 or bool(components) and all(len(c['specifications'])>=2 for c in components)
    synthetic = bool(components) or any(fact['synthetic'] for fact in dimension_provenance.values())
    basis = 'synthetic_lab_component_design' if components else 'synthetic_lab_design' if synthetic else 'source_measurements' if dimensions else 'unknown'
    views = {'hero':'Audit the existing hero photograph; do not generate a replacement automatically.',
             'angle':'Create a three-quarter view of exactly this product. Do not invent hidden construction details.',
             'detail':'Create a close-up showing only construction or surface texture visible in the approved reference.',
             'room':'Place exactly this product in a plausible room. Context is not included in the purchase; do not add matching-set claims.',
             'dimensions':'Prepare a dimension diagram using only the supplied dimensions. Never estimate missing dimensions.'}
    jobs = []
    for view, instruction in views.items():
        blockers = ['reference_identity_and_options_unapproved']
        if not record.get('reference'):
            blockers.append('missing_reference')
        if view == 'dimensions' and not has_dimensions:
            blockers.append('missing_explicit_dimensions')
        if view == 'room' and not has_dimensions:
            blockers.append('scale_unverified')
        if set(record.get('axis_codes', [])) & GEOMETRY_AXES:
            blockers.append('selected_variant_geometry_requires_review')
        if record.get('dimension_design',{}).get('status') == 'needs_identity_or_component_review':
            blockers.append('dimension_identity_or_component_review_required')
        dimension_instruction = ''
        if view in {'dimensions','room'}:
            dimension_instruction = ' Dimensions in cm: ' + json.dumps(dimensions,sort_keys=True) + '. Dimension scopes: ' + json.dumps(sorted({f['scope'] for f in dimension_provenance.values() if f.get('scope')})) + '.'
            if components:
                dimension_instruction += ' Individual component dimensions, not an installed span or a single set-wide dimension: ' + json.dumps([{k:c[k] for k in ('component_id','label','quantity','scope','dimensions_cm')} for c in component_dimensions],sort_keys=True) + '. Show each component and its quantity separately. Never invent an arrangement width or change the assortment.'
            if synthetic:
                dimension_instruction += ' These are approved fictional lab-design assumptions, not source-verified scale or fit. '
                dimension_instruction += ('Include the visible label: ' if view=='dimensions' else 'Keep this disclosure in media metadata: ') + DIMENSION_LABEL + '.'
        jobs.append({'job_id':record['sku'] + ':' + view, 'sku':record['sku'], 'source_product_id':record['source_product_id'],
                     'view':view, 'executable':False, 'reference':record.get('reference'), 'blockers':blockers,
                     'selected_options':record['variant_options'], 'dimensions_cm':dimensions,
                     'dimension_basis':basis,'dimension_provenance':dimension_provenance,
                     'component_dimensions':component_dimensions,
                     'dimension_design':record.get('dimension_design'),
                     'required_disclosure':DIMENSION_LABEL if synthetic else None,
                     'output_file':record['sku'] + '-DEPTH-' + view + '.jpg',
                     'prompt':instruction + ' Product: ' + record['name'] + '. Selected options: ' + json.dumps(record['variant_options'], sort_keys=True) + '. Preserve shape, finish, pattern and exact piece count. No logos or extra products. Text only for dimension labels and the required synthetic disclosure in an approved diagram.' + dimension_instruction,
                     'acceptance':['Same product identity and option values across views','Reference geometry reconciled with source measurements or explicitly synthetic design','Exact sale-unit piece count','No unsupported features or certifications','Synthetic dimensions disclosed; no manufacturer fit or verified-scale claims']})
    return jobs


def rating_proposal(prepared, configurable):
    try:
        rating = float(prepared.get('wands_average_rating', ''))
        count = int(prepared.get('wands_review_count', ''))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(rating) or not 0 < rating <= 5 or count <= 0:
        return None
    return {'average':rating, 'count':count, 'provenance':'Historical WANDS source-product aggregate',
            'source_product_only':True, 'generated_variants_reviewed':False if configurable else None,
            'created_reviews':0, 'display_label':'Source-product rating; not reviews of generated lab variants', 'review_required':True}


def curated_collections(candidates):
    definitions = [
        ('coastal-bedroom', 'Coastal bedroom accents', {'nightstands','dressers & chests','table lamps','accent pillows'}, 'Coastal', None),
        ('modern-home-office', 'Modern home office', {'desks','office chairs','bookcases','table lamps'}, 'Modern', None),
        ('small-space-tables', 'Small-space tables', {'end tables','sofa & console tables','coffee & cocktail tables'}, None, 80),
        ('textiles-under-200', 'Textile accents under $200', {'accent pillows','curtains & drapes','area rugs'}, None, None),
    ]
    result = []
    for key,title,allowed,style,max_width in definitions:
        matches = []
        for record in candidates:
            if not record['salable'] or not tokens(record['source_class']) & allowed or record['department']=='Baby & Kids':
                continue
            facts = record['specifications']
            evidence = []
            if style:
                if facts.get('lab_spec_style',{}).get('value') != style:
                    continue
                evidence.append({'attribute':'lab_spec_style','value':style})
            if max_width:
                width = facts.get('lab_spec_width_cm',{}).get('value')
                if width is None or width > max_width:
                    continue
                evidence.append({'attribute':'lab_spec_width_cm','value':width})
            if key=='textiles-under-200' and record['price'] >= 200:
                continue
            matches.append({'sku':record['sku'],'name':record['name'],'price':record['price'],'evidence':evidence})
        matches.sort(key=lambda r: stable_fraction(r['sku'], VERSION+':collection:'+key))
        result.append({'id':key,'title':title,'candidates':matches[:24],'eligible_count':len(matches), 'status':'merchant_review_required',
                       'price_scope':'Individual synthetic USD item price, before tax and shipping; not a room-total budget',
                       'empty_policy':'Leave empty when evidence is insufficient; do not invent matching products'})
    return result


def validate_records(records, links, known_skus):
    skus = [r['sku'] for r in records]
    if len(skus) != len(set(skus)) or not set(skus) <= known_skus:
        raise ValueError('Duplicate or unknown product identity')
    for r in records:
        if not math.isfinite(r['price']) or r['price'] <= 0:
            raise ValueError('Invalid price')
        for code, fact in r['specifications'].items():
            if code not in ATTRIBUTES or not fact.get('evidence'):
                raise ValueError('Specification missing schema or provenance')
            if ATTRIBUTES[code]['kind'] == 'length' and not 0 < fact['value'] <= 10000:
                raise ValueError('Invalid measurement')
        validate_dimensions(r)
    for link in links:
        if link['sku'] not in set(skus):
            raise ValueError('Unknown recommendation source')
        targets = [p['target_sku'] for kind in ('alternatives','complements') for p in link[kind]]
        if len(targets) != len(set(targets)) or link['sku'] in targets or not set(targets) <= known_skus:
            raise ValueError('Orphan, duplicate or self recommendation')


def render_review(records, summary, links):
    esc = lambda value: html.escape(str(value), quote=True)
    by_sku = {r['sku']:r for r in links}
    cards = []
    for r in records:
        image = '<p>No pinned reference image.</p>'
        if r.get('reference'):
            image = '<img loading="lazy" alt="Unapproved existing reference" src="' + esc(Path(r['reference']['path']).as_uri()) + '">'
        specs = ''.join('<tr><th>' + esc(ATTRIBUTES[k]['label']) + '</th><td>' + esc(v['value']) + (' (synthetic dimension)' if v['synthetic'] and ATTRIBUTES[k]['kind']=='length' else ' (synthetic option)' if v['synthetic'] else '') + '</td></tr>' for k,v in r['specifications'].items())
        design = r.get('dimension_design',{})
        dimension_note = '<p class="synthetic">' + esc(DIMENSION_LABEL) + '</p><p>' + esc(design.get('status','')) + '</p>' if design else ''
        ranges = ''.join('<tr><th>' + esc(ATTRIBUTES[k]['label']) + '</th><td>' + esc(str(v['min'])+' to '+str(v['max'])) + ' (child range; ' + str(v['covered_children']) + '/' + str(v['total_children']) + ' covered)</td></tr>' for k,v in design.get('ranges_cm',{}).items() if v['min']!=v['max'])
        component_notes = ''.join('<p><strong>' + esc(c['label']) + ' × ' + str(c['quantity']) + '</strong>: ' + esc(', '.join(ATTRIBUTES[k]['label'] + ' ' + str(f['value']) for k,f in c['specifications'].items())) + '. Synthetic; ' + esc(c['scope']) + '</p>' for c in design.get('components',[]))
        if design.get('component_children'):
            component_notes += '<p>' + str(design['component_children']) + ' child designs have separate component dimensions, not a single set-wide size. Component ranges and evidence are in the details below.</p>'
        suggestions = by_sku.get(r['sku'], {})
        counts = ', '.join(f'{len(suggestions.get(k,[]))} {k}' for k in ('alternatives','complements'))
        cards.append('<article><h2>' + esc(r['name']) + '</h2><p>' + esc(r['sku']) + ' · ' + esc(r['department']) + '</p>' + image +
                     '<p>' + esc(r['kind']) + ' · ' + esc(counts) + '</p>' + dimension_note + '<table>' + specs + ranges + '</table>' + component_notes + '<details><summary>' + str(len(r['withheld'])) +
                     ' withheld facts and review details</summary><pre>' + esc(json.dumps({'withheld':r['withheld'],'axes':r['axes'],'options':r['variant_options'],
                     'dimension_design':design,'gallery_target':r.get('gallery_target'),'children':r.get('child_summary',[]),'recommendations':suggestions,'rating':r.get('rating')},indent=2)) + '</pre></details></article>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WANDS catalog depth pilot</title><style>body{font:16px system-ui;margin:2rem;background:#f3f4f0;color:#18241e}main{max-width:1400px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:20px}article{background:white;padding:20px;border-radius:10px;overflow:hidden}img{width:100%;height:230px;object-fit:contain}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:7px;border-bottom:1px solid #ddd;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}h2{font-size:19px}summary{cursor:pointer}.synthetic{background:#fff2ca;padding:10px}</style><main><h1>WANDS catalog depth pilot</h1><p>Local review only. References and generated variants are not visually approved. Explicitly synthetic dimensions are labeled design assumptions, not recovered source facts. Blank specifications remain unknown. No catalog changes have been deployed.</p><pre>' + esc(json.dumps(summary,indent=2)) + '</pre><section class="grid">' + ''.join(cards) + '</section></main></html>'


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build(args):
    target = args.output_dir.resolve()
    if target.exists():
        raise ValueError('Output exists; select a new packet directory')
    paths = {'source':args.source_products, 'prepared':args.prepared_products, 'families':args.merchandising_dir/'configurable-families.jsonl',
             'patch':args.realism_packet/'products.patch.csv', 'packet_manifest':args.realism_packet/'manifest.json',
             'schema':SCHEMA_PATH, 'implementation':Path(__file__), 'source_helpers':Path(__file__).with_name('prepare_catalog.py'),
             'review_helpers':Path(__file__).with_name('build_realism_review.py'),
             'synthetic_dimension_rules':Path(__file__).with_name('synthetic_dimensions.py'),
             'schema_patch':SCHEMA_PATH.parent.parent/'Setup/Patch/Data/AddDepthAttributes.php',
             'queries':args.benchmark_dir/'queries.all.jsonl', 'judgments':args.benchmark_dir/'qrels.all.trec'}
    provenance = {k:{'path':str(p.resolve()),'sha256':sha256(p)} for k,p in paths.items()}
    packet = json.loads(paths['packet_manifest'].read_text())
    if packet['outputs']['products.patch.csv'] != provenance['patch']['sha256']:
        raise ValueError('Realism packet hash mismatch')
    for key in ('source','prepared','families'):
        if packet['inputs'][key]['sha256'] != provenance[key]['sha256']:
            raise ValueError('Realism packet source lineage mismatch: '+key)
    source = unique_index(read_csv(paths['source'],'\t'),'product_id')
    prepared = unique_index(read_csv(paths['prepared']),'wands_product_id')
    families = unique_index(read_jsonl(paths['families']),'source_product_id')
    patches = unique_index(read_csv(paths['patch']),'sku')
    if set(source) != set(prepared) or not families.keys() <= source.keys():
        raise ValueError('Source, prepared and family identities disagree')
    selected = select_pilot(list(source.values()),families,args.count)
    logging.info('Selected %s roots; extracting source-backed candidate attributes',len(selected))
    candidate_records = []
    for pid,row in sorted(source.items(),key=lambda pair:int(pair[0])):
        family = families.get(pid)
        original = family['parent'] if family else prepared[pid]
        sku = original['sku']
        if original['wands_product_id'] != pid or sku != prepared[pid]['sku']:
            raise ValueError('Family/source identity mismatch: '+pid)
        if sku not in patches:
            raise ValueError('Missing current product patch: '+sku)
        axes = {a['attribute'] for a in family['axes']} if family else set()
        facts, withheld = extract_specs(row, axes)
        patch = patches[sku]
        amount = patch['special_price'] if patch['special_price'] not in {'','__EMPTY__VALUE__'} else patch['price']
        candidate_records.append({'sku':sku,'source_product_id':pid,'source_class':row['product_class'],'department':department(row),
                                  'name':patch['name'],'kind':'configurable' if family else 'simple','price':float(amount),
                                  'salable':patch['is_in_stock']=='1','specifications':facts,'withheld':withheld,'variant_options':{},
                                  'axis_codes':sorted(axes),'axes':family['axes'] if family else [],'rating':rating_proposal(prepared[pid],bool(family)),
                                  'identity':{'sku':sku,'product_type':original['product_type'],'url_key':original['url_key']}})
    by_pid = {r['source_product_id']:r for r in candidate_records}
    records, child_records, briefs, links, references = [], [], [], [], {}
    synthetic_enabled = getattr(args,'synthetic_dimensions',False)
    for row in selected:
        pid = row['product_id']; record = dict(by_pid[pid]); family = families.get(pid)
        if synthetic_enabled:
            record['design_context'] = source_context(row)
        record['reference'] = None
        for suffix in ('.jpg','.png','.webp'):
            image = args.media_dir/(record['sku']+suffix)
            if image.is_file():
                record['reference'] = {'path':str(image.resolve()),'sha256':sha256(image),'source_sku':record['sku']}
                references[str(image.resolve())] = record['reference']['sha256']
                break
        for child in family['variants'] if family else []:
            if child['sku'] not in patches:
                raise ValueError('Missing selected child patch')
            options = child['options']
            if set(options) != set(record['axis_codes']) or any(options[a['attribute']] not in a['values'] for a in family['axes']):
                raise ValueError('Child option/axis mismatch')
            facts, withheld = extract_specs(row,set(record['axis_codes']),options)
            child_record = {**record,'sku':child['sku'],'kind':'simple','parent_sku':record['sku'],'name':patches[child['sku']]['name'],
                                  'price':float(patches[child['sku']]['price']),'salable':patches[child['sku']]['is_in_stock']=='1',
                                  'specifications':facts,'withheld':withheld,'variant_options':options,'rating':None,
                                  'identity':{'sku':child['sku'],'product_type':child['product_type'],'url_key':child['url_key']}}
            child_records.append(add_dimensions(child_record) if synthetic_enabled else child_record)
        variants = sorted((r for r in child_records if r.get('parent_sku')==record['sku']),key=lambda r:(not r['salable'],r['sku']))
        if synthetic_enabled:
            record = summarize_family(record,variants) if family else add_dimensions(record)
        gallery_record = record
        if family:
            gallery_record = variants[0]
        record['gallery_target'] = {'sku':gallery_record['sku'],'options':gallery_record['variant_options'],'reference_status':'unapproved'}
        record['child_summary'] = [{'sku':r['sku'],'options':r['variant_options'],'specifications':r['specifications'],'dimension_design':r.get('dimension_design')} for r in variants]
        briefs.extend(gallery_briefs(gallery_record))
        links.append({'sku':record['sku'],**recommend(record,candidate_records)})
        records.append(record)
    all_records = records + child_records
    validate_records(all_records,links,set(patches))
    collections = curated_collections(candidate_records)
    synthetic_facts = [(r,code,fact) for r in all_records for code,fact in r['specifications'].items() if ATTRIBUTES[code]['kind']=='length' and fact['synthetic']]
    component_facts = [(r,c,code,fact) for r in all_records for c in r.get('dimension_design',{}).get('components',[]) for code,fact in c['specifications'].items()]
    repairs = repair_proposals(all_records)
    summary = {'version':VERSION,'products':len(records),'configurable_roots':sum(r['kind']=='configurable' for r in records),
               'selected_children':len(child_records),'specification_rows':len(all_records),'departments':dict(Counter(r['department'] for r in records)),
               'gallery_briefs':len(briefs),'images_generated':0,'recommendation_candidates':sum(len(r[k]) for r in links for k in ('alternatives','complements')),
               'roots_with_source_specs':sum(any(not f['synthetic'] for f in r['specifications'].values()) for r in records),
               'synthetic_dimensions_enabled':synthetic_enabled,'synthetic_dimension_rule_version':DIMENSION_VERSION if synthetic_enabled else None,
               'synthetic_dimension_facts':len(synthetic_facts),'rows_with_synthetic_dimensions':len({r['sku'] for r,_,_ in synthetic_facts}),
               'synthetic_component_dimension_facts':len(component_facts),'rows_with_component_dimensions':len({r['sku'] for r,_,_,_ in component_facts}),
               'repair_root_count':len(repairs),'repair_affected_record_count':sum(r['affected_record_count'] for r in repairs),
               'root_dimension_status':dict(Counter(r.get('dimension_design',{}).get('status','not_requested') for r in records)),
               'child_dimension_status':dict(Counter(r.get('dimension_design',{}).get('status','not_requested') for r in child_records)),
               'withheld_facts':sum(len(r['withheld']) for r in all_records),'historical_rating_proposals':sum(r['rating'] is not None for r in records),
               'live_writes':0,'deployment_ready':False}
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.depth-',dir=target.parent) as temporary:
        stage = Path(temporary)/'packet'; stage.mkdir()
        write_jsonl(stage/'products.jsonl',records)
        write_jsonl(stage/'children.jsonl',child_records)
        write_jsonl(stage/'gallery-briefs.jsonl',briefs)
        write_jsonl(stage/'recommendations.jsonl',links)
        write_json(stage/'collections.json',collections)
        write_json(stage/'coverage.json',{
            'root_denominator':len(records),'child_denominator':len(child_records),
            'root_attribute_counts':dict(Counter(code for r in records for code in r['specifications'])),
            'root_source_attribute_counts':dict(Counter(code for r in records for code,fact in r['specifications'].items() if not fact['synthetic'])),
            'synthetic_dimension_issues':dict(Counter(issue for r in all_records for issue in r.get('dimension_design',{}).get('issues',[]))),
            'root_withheld_reasons':dict(Counter(item['reason'] for r in records for item in r['withheld'])),
            'child_withheld_reasons':dict(Counter(item['reason'] for r in child_records for item in r['withheld'])),
            'gallery_blockers':dict(Counter(reason for brief in briefs for reason in brief['blockers']))})
        write_json(stage/'attribute-schema.json',SCHEMA)
        write_json(stage/'validation.json',{'identity_and_references_valid':True,'source_facts_have_provenance':True,'unknowns_withheld':True,
                                          'synthetic_dimensions_separately_labeled':True,'synthetic_geometry_constraints_valid':True,
                                          'visual_acceptance':False,'magento_import_validated':False})
        with (stage/'specifications.proposed.csv').open('w',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=['sku','store_view_code',*ATTRIBUTES])
            writer.writeheader()
            for r in all_records:
                writer.writerow({'sku':r['sku'],'store_view_code':'',**{code:fact['value'] for code,fact in r['specifications'].items() if not (ATTRIBUTES[code]['kind']=='length' and fact['synthetic'])}})
        with (stage/'synthetic-dimensions.proposed.csv').open('w',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=['sku','attribute_code','value','unit','synthetic','display_label','origin','rule_version','profile','scope','evidence_json'])
            writer.writeheader()
            for r,code,fact in synthetic_facts:
                writer.writerow({'sku':r['sku'],'attribute_code':code,'value':fact['value'],'unit':'cm','synthetic':'true',
                                 **{k:fact[k] for k in ('display_label','origin','rule_version','profile','scope')},'evidence_json':json.dumps(fact['evidence'],sort_keys=True)})
        write_jsonl(stage/'dimension-exceptions.jsonl',[{'sku':r['sku'],'parent_sku':r.get('parent_sku'),'name':r['name'],
            'source_class':r['source_class'],'options':r['variant_options'],'design':r['dimension_design']}
            for r in all_records if r.get('dimension_design',{}).get('issues')])
        write_jsonl(stage/'dimension-repair-proposals.jsonl',repairs)
        with (stage/'component-dimensions.proposed.csv').open('w',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=['sku','component_id','component_label','quantity','attribute_code','value','unit','display_label','rule_version','scope','evidence_json','composition_evidence_json'])
            writer.writeheader()
            for r,c,code,fact in component_facts:
                writer.writerow({'sku':r['sku'],'component_id':c['component_id'],'component_label':c['label'],'quantity':c['quantity'],
                    'attribute_code':code,'value':fact['value'],'unit':'cm','display_label':fact['display_label'],'rule_version':fact['rule_version'],
                    'scope':c['scope'],'evidence_json':json.dumps(fact['evidence'],sort_keys=True),'composition_evidence_json':json.dumps(c['composition_evidence'],sort_keys=True)})
        write_json(stage/'benchmark-freeze.json',{'upstream_queries':provenance['queries'],'upstream_judgments':provenance['judgments'],
                                                'prior_metrics_apply_to_new_catalog':False,'new_judgments_required':True,'policy':'Do not edit or reuse WANDS labels as judgments of generated variants, bundles, imagery or changed product facts.'})
        queue = [{'query_id':'depth-'+r['source_product_id'],'query':r['name'],'candidate_sku':r['sku'],'judgment':None,
                  'status':'unjudged','query_origin':'product-name seed; merchant must author realistic intent query before freezing holdout',
                  'human_review_required':True} for r in records]
        write_jsonl(stage/'new-judgment-seeds.jsonl',queue)
        (stage/'review.html').write_text(render_review(records,summary,links),encoding='utf-8')
        if any(sha256(paths[k])!=v['sha256'] for k,v in provenance.items()) or any(sha256(Path(p))!=h for p,h in references.items()):
            raise ValueError('Input changed during pilot build')
        manifest = {**summary,'inputs':provenance,'references':references,'outputs':{p.name:sha256(p) for p in sorted(stage.iterdir())},
                    'gates':['Review source conflicts and sparse coverage','Approve selected-variant reference identity before any generation','Review every recommendation, not just matching style','Validate attributes/import against isolated Magento','Fresh remote snapshot, exact diff, backup and deployment approval']}
        write_json(stage/'manifest.json',manifest)
        stage.rename(target)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-products','prepared-products','merchandising-dir','realism-packet','media-dir','benchmark-dir','output-dir'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--count',type=int,default=300)
    parser.add_argument('--synthetic-dimensions',action='store_true',help='Explicit opt-in to separately labeled fictional pilot dimensions; never source facts or import approval')
    parser.add_argument('--json',action='store_true',help='Opt in to terminal output; normally tail OUTPUT_DIR.log')
    args = parser.parse_args()
    log = args.output_dir.with_name(args.output_dir.name+'.log')
    log.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=log,level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        manifest = build(args)
        logging.info('Complete: %s',json.dumps({k:v for k,v in manifest.items() if k not in {'inputs','outputs','references'}}))
        if args.json: print(json.dumps(manifest,indent=2))
        return 0
    except Exception:
        logging.exception('Catalog depth build failed; no live changes made')
        return 1


if __name__=='__main__': raise SystemExit(main())
