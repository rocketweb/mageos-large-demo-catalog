#!/usr/bin/env python3
"""Prepare immutable local catalog corrections. No imports, inference or uploads."""
from __future__ import annotations

import argparse
import copy
import html
import itertools
import json
import logging
import math
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from build_realism_review import read_csv, unique_index, write_json, write_jsonl
from catalog_depth import ATTRIBUTES, OPTION_FIELDS, gallery_briefs, render_review, normalize, extract_specs, rating_proposal
from definition_resolutions import remaining_rules, validate_resolved_definition, RESOLUTION_PROFILES, APPROVAL as RESOLUTION_APPROVAL
from prepare_catalog import sha256, parse_features, department
from repair_designs import rules, expansion_rule, VERSION, DISCLOSURE
from synthetic_dimensions import PROFILES, LABEL, ORIGIN, PREFIX, BED_ANCHORS, option_cm, summarize_family, validate_dimensions, add_dimensions, source_context

EXTRA_PROFILES = {
    'cafe_panel': {'scope':'one short curtain panel laid flat, not a whole window','dimensions':{'width':70,'length':76}},
    'valance': {'scope':'one valance laid flat, not an installed window width','dimensions':{'width':140,'length':30}},
    'pillowcase': {'scope':'one pillowcase laid flat; insert fit and thickness unspecified','dimensions':{'width':51,'length':100}},
    'nursery_cover': {'scope':'one decorative textile laid flat; no infant-sleep or fit claim','dimensions':{'width':85,'length':110}},
    'crib_sheet': {'scope':'one fictional crib-sheet surface and pocket; no fit or infant-sleep claim','dimensions':{'width':71,'length':133,'height':15}},
    'crib_skirt': {'scope':'one skirt platform and drop; no crib-fit or infant-sleep claim','dimensions':{'width':71,'length':133,'height':30}},
    'nursery_pillowcase': {'scope':'one decorative pillowcase laid flat; no infant-sleep claim','dimensions':{'width':30,'length':40}},
    'wall_decor': {'scope':'one decorative hanging exterior; mounting unspecified','dimensions':{'width':25,'height':30}},
    'plush': {'scope':'one decorative plush exterior; no age or safety rating','dimensions':{'width':20,'depth':15,'height':25}},
    'fabric_bag': {'scope':'one hanging fabric bag exterior; capacity and mounting unspecified','dimensions':{'width':30,'depth':18,'height':45}},
    'booties_pair': {'scope':'one pair displayed side by side; no age or fit claim','dimensions':{'width':14,'length':12,'height':8}},
    'fabric_cut': {'scope':'one separate precut fabric panel laid flat; not a continuous roll','dimensions':{'width':137.16,'length':91.44}},
}
INVENTORY = ('qty','is_in_stock','manage_stock','use_config_manage_stock','backorders','use_config_backorders','lab_stock_scenario')
PRICE_FIELDS = ('price','special_price','lab_price_method','lab_price_version','lab_price_synthetic')
REFERENCE_FINDINGS = {
    'WANDS-012133': {
        'reference_sha256':'8b81943bf96b07ee6f37d4c0c2e40f1aaf5f8767cdf4658d09806cc2ec54e4f7',
        'finding':'Reference depicts spoons of spices on a board, not a pair of curtains.',
        'instruction':'Create two short kitchen curtain panels with a printed spice-spoon motif on fabric. Show fabric folds and two separate panel hems. Do not depict loose spoons, spices, a cutting board or an artwork print as the product. Use the selected base color and panel drop; motifs may use contrasting print colors.',
    },
    'WANDS-014741': {
        'reference_sha256':'429daa69957e0bd4bd4aa411e8ac82abce1ef22e7e33aff11fc07e1945f67899',
        'finding':'Reference shows a gold-colored three-drawer cabinet, not the selected Oak finish.',
        'instruction':'Retain a single three-drawer bedside cabinet as the product identity. Replace the gold-colored cabinet finish with the selected wood finish and use the corrected cabinet width. Do not add a second cabinet or extra drawers.',
    },
    'WANDS-038422': {
        'reference_sha256':'316e1c7ede179f064fe51e7110f48d7dcf9d5efc6a5a93f5bfc885c4ae76c6b7',
        'finding':'Reference resembles a wrapped rectangular box; it does not show the twelve-item nursery textile assortment.',
        'instruction':'Replace the box-like reference with a flat-lay nursery-decor assortment. Show exactly one quilt, two valances, one crib skirt, one fitted sheet, one diaper stacker, one toy bag, two decorative pillows and three wall hangings. Separate each role so its quantity is countable. No box, crib, mattress, infant or in-use sleeping arrangement. Follow the selected color and component geometry.',
    },
}


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def image_repair_drafts(reviews):
    drafts=[]
    for review in reviews:
        finding=REFERENCE_FINDINGS.get(review['root_sku'])
        if not finding: continue
        ref=review.get('reference')
        if not ref or ref['sha256']!=finding['reference_sha256']:
            raise ValueError('Visual finding reference changed: '+review['root_sku'])
        drafts.append({'root_sku':review['root_sku'],'selected_sku':review['selected_sku'],
            'reference':ref,'finding':finding['finding'],'observation':'local visual inspection; not manufacturer validation',
            'prompt':finding['instruction']+' Selected options: '+json.dumps(review['selected_options'],sort_keys=True)+
                '. Exact sale unit: '+review['sale_unit']+'. '+DISCLOSURE,
            'design':review['design'],'status':'draft_requires_reference_repair_then_visual_acceptance',
            'executable':False,'model_calls':0})
    return drafts


def materialize_family(row, family, prepared, patch, media_dir):
    """Recover an out-of-pilot family's current definition from pinned inputs."""
    original=family['parent']; sku=original['sku']; pid=row['product_id']
    if family['source_product_id']!=pid or original['wands_product_id']!=pid or prepared['sku']!=sku:
        raise ValueError('Expansion family/source identity mismatch')
    axes=copy.deepcopy(family['axes']); codes={a['attribute'] for a in axes}
    current=patch[sku]; facts,withheld=extract_specs(row,codes)
    amount=current['special_price'] if current['special_price'] not in {'','__EMPTY__VALUE__'} else current['price']
    root={'sku':sku,'source_product_id':pid,'source_class':row['product_class'],'department':department(row),
        'name':current['name'],'kind':'configurable','price':float(amount),'salable':current['is_in_stock']=='1',
        'specifications':facts,'withheld':withheld,'variant_options':{},'axis_codes':sorted(codes),'axes':axes,
        'rating':rating_proposal(prepared,True),'design_context':source_context(row),
        'identity':{'sku':sku,'product_type':original['product_type'],'url_key':original['url_key']},
        'catalog_fields':copy.deepcopy(current),'reference':None,'scope':'full_catalog_expansion'}
    for suffix in ('.jpg','.png','.webp'):
        image=media_dir/(sku+suffix)
        if image.is_file():
            root['reference']={'path':str(image.resolve()),'sha256':sha256(image),'source_sku':sku}
            break
    children=[]
    for variant in family['variants']:
        child=copy.deepcopy(root); options=copy.deepcopy(variant['options']); fields=patch[variant['sku']]
        if set(options)!=codes or any(options[a['attribute']] not in a['values'] for a in axes):
            raise ValueError('Expansion child option schema mismatch')
        facts,withheld=extract_specs(row,codes,options)
        child.update(sku=variant['sku'],parent_sku=sku,kind='simple',name=fields['name'],price=float(fields['price']),
            salable=fields['is_in_stock']=='1',specifications=facts,withheld=withheld,variant_options=options,rating=None,
            identity={'sku':variant['sku'],'product_type':variant['product_type'],'url_key':variant['url_key']},
            catalog_fields=copy.deepcopy(fields))
        children.append(add_dimensions(child))
    if not children: raise ValueError('Expansion configurable has no children')
    root=summarize_family(root,children)
    chosen=min(children,key=lambda r:(not r['salable'],r['sku']))
    root['gallery_target']={'sku':chosen['sku'],'options':chosen['variant_options'],'reference_status':'unapproved'}
    root['child_summary']=[{'sku':c['sku'],'options':c['variant_options'],'specifications':c['specifications'],
        'dimension_design':c.get('dimension_design')} for c in children]
    return root,children


def clean_dimensions(record):
    result = copy.deepcopy(record)
    result['specifications'] = {k:v for k,v in result['specifications'].items() if not (k.endswith('_cm') and v.get('synthetic'))}
    result.pop('dimension_design', None)
    return result


def refine_facts(record):
    """Recover exact aliases only, never multi-valued, variable or unitless facts."""
    result=copy.deepcopy(record);remaining=[];recovered=[]
    synonyms={'lab_spec_style':{'country / farmhouse':'Farmhouse','farmhouse / country':'Farmhouse','boho':'Bohemian'},
              'lab_spec_material':{'100 % cotton':'Cotton','100% cotton':'Cotton'}}
    for entry in record['withheld']:
        code=entry['attribute']
        if entry['reason']!='outside controlled vocabulary' or code in record['specifications'] or ATTRIBUTES[code]['kind']!='select':
            remaining.append(entry);continue
        try:
            values=[]
            for evidence in entry['evidence']:
                raw=evidence['raw'].strip().casefold()
                if code=='lab_spec_bulb_base':
                    raw=re.sub(r'\(\s*','(',raw)
                    raw=re.sub(r'\s*\)',')',raw)
                raw=synonyms.get(code,{}).get(raw,raw)
                values.append(normalize(raw,ATTRIBUTES[code]))
            if len(set(values))!=1: raise ValueError('Conflicting aliases')
            result['specifications'][code]={'value':values[0],'synthetic':False,
                'origin':'WANDS product_features; exact alias normalization',
                'rule_version':VERSION,'evidence':copy.deepcopy(entry['evidence'])}
            recovered.append(code)
        except ValueError:
            remaining.append(entry)
    result['withheld']=remaining
    if recovered: result['facet_refinements']={'attributes':sorted(recovered),'version':VERSION,'source_evidence_preserved':True}
    return result


def make_design(record, descriptor):
    result = clean_dimensions(record)
    if 'components' in descriptor:
        components = []
        for definition in descriptor['components']:
            leaf = copy.deepcopy(result)
            leaf['specifications'] = {}
            leaf = make_design(leaf, definition)
            components.append({'component_id':definition['id'],'label':definition['label'],
                'quantity':definition['quantity'],'profile':definition['profile'],
                'scope':leaf['dimension_design']['scope'],'specifications':leaf['specifications'],
                'composition_synthetic':True,'composition_basis':DISCLOSURE,
                'counts_as_furniture':definition.get('counts_as_furniture',True),
                'composition_evidence':[{'key':'authored_repair_rule','raw':record.get('parent_sku',record['sku'])},
                                        {'key':'rule_version','raw':VERSION}]})
        result['dimension_design'] = {'status':'synthetic_components_complete','profile':None,
            'rule_version':VERSION,'display_label':LABEL,'source_verified':False,'issues':[],
            'scope':'Individual component envelopes; no installed span or combined set-wide measurement',
            'total_component_quantity':sum(c['quantity'] for c in components),
            'furniture_piece_count':sum(c['quantity'] for c in components if c['counts_as_furniture']),
            'components':components}
    else:
        key = descriptor['profile']
        profile = {**PROFILES, **EXTRA_PROFILES, **RESOLUTION_PROFILES}[key]
        values = {**profile['dimensions'], **descriptor.get('dimensions',{})}
        options = record['variant_options']
        for option, dimension in descriptor.get('bindings',{}).items():
            values[dimension] = option_cm(options[option])
        if descriptor.get('depth_matches_width'):
            values['depth'] = values['width']
        if 'rectangle_axis' in descriptor:
            parts = options[descriptor['rectangle_axis']].split(' x ')
            if len(parts)!=2: raise ValueError('Invalid rectangular option')
            values['width'],values['length'] = map(option_cm,parts)
        if 'bed_axis' in descriptor or 'fixed_bed_size' in descriptor:
            sizes = (options[descriptor['bed_axis']] if 'bed_axis' in descriptor else descriptor['fixed_bed_size']).split(' over ')
            anchors = {**BED_ANCHORS,'Twin XL':(99,203.2)}
            padding = 8 if key=='bed' else 16
            values['width'] = max(anchors[s][0] for s in sizes)+padding
            values['length'] = max(anchors[s][1] for s in sizes)+(12 if key=='bed' else padding)
        for dimension,value in values.items():
            if type(value) not in (int,float) or not math.isfinite(value) or not 0 < value <= 10000:
                raise ValueError('Invalid repair dimension')
            anchor = profile['dimensions'].get(dimension)
            if anchor is None or not anchor*.35 <= value <= anchor*3:
                raise ValueError('Repair dimension outside profile bounds: '+key+':'+dimension)
            code = PREFIX+dimension+'_cm'
            existing = result['specifications'].get(code)
            if existing and existing['value'] != round(value,4):
                raise ValueError('Conflicting source dimension: '+record['sku']+':'+code)
            if not existing:
                result['specifications'][code] = {'value':round(value,4),'synthetic':True,'origin':ORIGIN,
                    'rule_version':VERSION,'profile':key,'display_label':LABEL,'scope':profile['scope'],
                    'evidence':[{'key':'authored_repair_rule','raw':record.get('parent_sku',record['sku'])},
                                {'key':'synthetic_profile','raw':key},
                                {'key':'geometry_options','raw':json.dumps({k:v for k,v in options.items() if k.startswith('wands_') and k not in {'wands_finish','wands_material'}},sort_keys=True)}]}
        result['dimension_design'] = {'status':'synthetic_design_complete','profile':key,'rule_version':VERSION,
            'display_label':LABEL,'scope':profile['scope'],'source_verified':False,'issues':[]}
    validate_dimensions(result)
    return result


def describe(record, rule):
    esc = html.escape
    selected = ', '.join(record['variant_options'].values())
    record['name'] = rule['name'] + (' - '+selected if selected else '')
    fields = record['catalog_fields']
    parts = record.get('dimension_design',{}).get('components',[]) or rule.get('design',{}).get('components',[])
    contents = ''.join('<li>'+esc(str(c['quantity'])+' x '+c['label'])+'</li>' for c in parts)
    choices = '; '.join(a['label']+': '+', '.join(a['values']) for a in record['axes'])
    paragraph = 'Selected options: '+selected+'.' if selected else 'Available options: '+choices+'.' if choices else ''
    body = '<p>'+esc(rule['copy'])+'</p><p>'+esc(paragraph)+'</p><p>Sold as: '+esc(rule['sale_unit'])+'.</p>'
    if contents: body += '<h3>Included items</h3><ul>'+contents+'</ul>'
    elif rule.get('design_variants'):
        allowed=next(a['values'] for a in record['axes'] if a['attribute']==rule['design_axis'])
        body += '<h3>Assortments</h3><ul>'+''.join('<li>'+esc(value+': '+', '.join(str(c['quantity'])+' x '+c['label'] for c in rule['design_variants'][value]['components']))+'</li>' for value in allowed)+'</ul>'
    body += '<p>'+esc(DISCLOSURE)+'</p><p>'+esc(LABEL)+'. No manufacturer fit, safety or installation guarantee.</p>'
    fields.update(name=record['name'], description=body, short_description=rule['copy']+' Sold as: '+rule['sale_unit']+'.',
                  meta_title=record['name'][:255], meta_description=(rule['copy']+' '+rule['sale_unit'])[:255],
                  lab_sale_unit=rule['sale_unit'])
    record['repair'] = {'version':VERSION,'status':'local_candidate_requires_review','rationale':rule['rationale'],
                        'disclosure':DISCLOSURE,'executable':False,'source_verified':False}
    if rule.get('source_resolution'):
        record['repair']['source_resolution']=copy.deepcopy(rule['source_resolution'])
        record['repair']['resolution_kind']=rule['resolution_kind']
    return record


def design_for(record, rule):
    return rule['design_variants'][record['variant_options'][rule['design_axis']]] if 'design_variants' in rule else rule['design']


def repair_family(root, children, rule):
    root, children = copy.deepcopy(root), copy.deepcopy(children)
    if 'hold_reason' in rule: return root,children,[]
    axes = copy.deepcopy(root['axes'])
    changes=rule.get('axis_changes',[]) or ([rule['axis']] if rule.get('axis') else [])
    for change in changes:
        old_axis = next((a for a in axes if a['attribute']==change['from']),None)
        if old_axis is None or any(v not in change['map'] for v in old_axis['values']):
            raise ValueError('Unexpected family option schema: '+root['sku'])
        mapped = [change['map'][v] for v in old_axis['values']]
        if len(mapped)!=len(set(mapped)): raise ValueError('duplicate mapped option')
        old_axis.update(attribute=change['to'], label=change['label'], values=mapped)
        for child in children:
            old = child['variant_options'].pop(change['from'])
            if old not in change['map']: raise ValueError('Unexpected child option')
            child['variant_options'][change['to']] = change['map'][old]
        # An option assignment and its searchable facet must change together.
        # Clear is a valid proposed configurable value even when the separate
        # controlled specification schema still needs a new Clear enum option.
        codes={OPTION_FIELDS[k] for k in (change['from'],change['to']) if k in OPTION_FIELDS}
        for record in [root,*children]:
            for code in codes:
                fact=record['specifications'].get(code)
                if fact and not fact.get('synthetic'): raise ValueError('Option correction conflicts with source fact')
                if fact:
                    record.setdefault('superseded_specifications',{})[code]=record['specifications'].pop(code)
                record['withheld']=[w for w in record['withheld'] if not (w['attribute']==code and any(e['key'] in {change['from'],change['to']} for e in w['evidence']))]
                value=record['variant_options'].get(change['to'])
                if value is None or OPTION_FIELDS.get(change['to'])!=code: continue
                evidence=[{'key':change['to'],'raw':value}]
                try:
                    record['specifications'][code]={'value':normalize(value,ATTRIBUTES[code]),'synthetic':True,
                        'origin':'corrected synthetic variant option','evidence':evidence,'rule_version':VERSION}
                except ValueError as error:
                    record['withheld'].append({'attribute':code,'reason':str(error),'evidence':evidence})
    dropped = set(rule.get('drop_axes',[]))
    if dropped - {a['attribute'] for a in axes}: raise ValueError('Unknown collapsed axis')
    axes = [a for a in axes if a['attribute'] not in dropped]
    # Retirement snapshots use the untouched caller's records in build(); this
    # local choice only selects stable survivors in original axis-value order.
    order = {a['attribute']:{v:i for i,v in enumerate(a['values'])} for a in root['axes']}
    groups = defaultdict(list)
    for child in children:
        key = tuple(sorted((k,v) for k,v in child['variant_options'].items() if k not in dropped))
        groups[key].append(child)
    survivors, retired = [], []
    for group in groups.values():
        if len(group)>1 and not dropped: raise ValueError('duplicate option combination')
        group.sort(key=lambda c:(tuple(order[k][c['variant_options'][k]] for k in sorted(dropped)),c['sku']))
        survivor = group[0]
        survivors.append(survivor)
        for child in group[1:]:
            retired.append({'sku':child['sku'],'replacement_sku':survivor['sku'],
                            'reason':'duplicate after removing inappropriate option axis','executable':False})
    for record in [root,*survivors]:
        record['axes'],record['axis_codes'] = copy.deepcopy(axes), sorted(a['attribute'] for a in axes)
        record['variant_options'] = {k:v for k,v in record['variant_options'].items() if k not in dropped}
    if children and not axes:
        if len(survivors)!=1: raise ValueError('Expected one root-simple seed')
        seed=survivors[0]
        for key in (*INVENTORY,*PRICE_FIELDS):
            if key in seed['catalog_fields']: root['catalog_fields'][key]=seed['catalog_fields'][key]
        root.update(kind='simple',price=seed['price'],salable=seed['salable'])
        root['identity']['product_type']='simple'
        retired.append({'sku':seed['sku'],'replacement_sku':root['sku'],
                        'reason':'single design represented by existing root SKU','executable':False})
        for item in retired: item['replacement_sku']=root['sku']
        root['structural_review']={'previous_type':'configurable','candidate_type':'simple',
                                   'inventory_seed_sku':seed['sku'],'actual_inventory_transfer_approved':False}
        survivors=[]
    revised=[describe(make_design(c,design_for(c,rule)),rule) for c in survivors]
    if revised:
        root=summarize_family(clean_dimensions(root),revised)
        # Summarize the union of roles, including zero quantities in designs
        # where a component is absent. The smallest variant is not the schema.
        role_ids=sorted({p['component_id'] for c in revised for p in c['dimension_design'].get('components',[])})
        ranges=[]
        for identifier in role_ids:
            matches=[next((p for p in c['dimension_design'].get('components',[]) if p['component_id']==identifier),None) for c in revised]
            present=[p for p in matches if p is not None]
            codes=sorted({k for p in present for k in p['specifications']})
            ranges.append({'component_id':identifier,'label':present[0]['label'],
                'quantity_per_design':sorted({p['quantity'] if p else 0 for p in matches}),
                'present_children':len(present),'total_children':len(revised),
                'dimensions_cm':{code:{'min':min(p['specifications'][code]['value'] for p in present if code in p['specifications']),
                    'max':max(p['specifications'][code]['value'] for p in present if code in p['specifications']),
                    'covered_children':sum(code in p['specifications'] for p in present),'total_children':len(revised)} for code in codes}})
        root['dimension_design']['component_ranges']=ranges
        root['price']=min(c['price'] for c in revised)
        root['salable']=any(c['salable'] for c in revised)
    else:
        root=make_design(root,design_for(root,rule))
    root=describe(root,rule)
    selected=min(revised,key=lambda r:(not r['salable'],r['sku'])) if revised else root
    root['gallery_target']={'sku':selected['sku'],'options':copy.deepcopy(selected['variant_options']),'reference_status':'unapproved_after_catalog_correction'}
    root['child_summary']=[{'sku':c['sku'],'options':c['variant_options'],'specifications':c['specifications'],'dimension_design':c['dimension_design']} for c in revised]
    return root,revised,retired


def validate_candidate(before, after, retired):
    old=unique_index(before,'sku'); new=unique_index(after,'sku')
    gone=unique_index(retired,'sku')
    if set(old) != set(new)|set(gone) or set(new)&set(gone): raise ValueError('Identity partition mismatch')
    for item in retired:
        if item['replacement_sku'] not in new or item['executable'] is not False:
            raise ValueError('Invalid retirement proposal')
    families=defaultdict(list)
    for record in after:
        previous=old[record['sku']]
        if record['identity']['url_key']!=previous['identity']['url_key']:
            raise ValueError('Unexpected URL identity change')
        if not math.isfinite(record['price']) or record['price']<=0: raise ValueError('Invalid price')
        if 'structural_review' not in record:
            for field in (*INVENTORY,*PRICE_FIELDS):
                if record['catalog_fields'].get(field)!=previous['catalog_fields'].get(field):
                    raise ValueError('Unexpected price or inventory change')
        for code,fact in previous['specifications'].items():
            if not fact.get('synthetic') and record['specifications'].get(code)!=fact:
                raise ValueError('Source fact changed')
        validate_dimensions(record)
        parts=record.get('dimension_design',{}).get('components',[])
        if parts and 'wands_piece_count' in record['variant_options']:
            expected=int(record['variant_options']['wands_piece_count'].split()[0])
            if expected!=record['dimension_design']['furniture_piece_count']: raise ValueError('Piece count does not match components')
        if record.get('parent_sku'):
            if record['parent_sku'] not in new or new[record['parent_sku']]['kind']!='configurable': raise ValueError('Orphan child')
            families[record['parent_sku']].append(record)
    for root in (r for r in after if r['kind']=='configurable'):
        axes=root['axes']; children=families[root['sku']]
        expected=set(itertools.product(*(a['values'] for a in axes)))
        actual=[tuple(c['variant_options'][a['attribute']] for a in axes) for c in children]
        if len(actual)!=len(set(actual)) or set(actual)!=expected: raise ValueError('Incomplete or duplicate family matrix')
        for c in children:
            if set(c['variant_options'])!=set(root['axis_codes']): raise ValueError('Child axis mismatch')
        # Price ordering is checked within each identical finish/color combination.
        for index,a in enumerate(axes):
            if a['attribute'] in {'color','wands_finish','wands_material'}: continue
            price_groups=defaultdict(list)
            for c in children:
                key=tuple((k,v) for k,v in sorted(c['variant_options'].items()) if k!=a['attribute'])
                price_groups[key].append((a['values'].index(c['variant_options'][a['attribute']]),c['price']))
            if any([p for _,p in sorted(g)]!=sorted(p for _,p in g) for g in price_groups.values()):
                raise ValueError('Non-monotonic size/assortment price ladder')


def sparse_proposals(records):
    proposals=[]
    for record in records:
        values={k:f['value'] for k,f in record['specifications'].items()}
        synthetic=any(k.endswith('_cm') and f.get('synthetic') for k,f in record['specifications'].items())
        if synthetic: values['lab_spec_dimension_disclosure']=LABEL
        components=record.get('dimension_design',{}).get('components',[])
        proposals.append({'sku':record['sku'],'set':values,'clear':[],
                          'component_payload':components,'component_storage_required':bool(components),
                          'provenance':record['specifications'],'executable':False,
                          'disclosure_storage_and_renderer_required':synthetic or bool(components)})
    return proposals


def bundle_reference_impact(bundles, changed_skus, retired_skus):
    references=[{'bundle_sku':b['sku'],'option':o['name'],'selected_sku':s['sku']}
        for b in bundles for o in b['options'] for s in o['selections']]
    return {'bundles_checked':len(bundles),'selection_references_checked':len(references),
        'changed_selection_references':[r for r in references if r['selected_sku'] in changed_skus],
        'retired_selection_references':[r for r in references if r['selected_sku'] in retired_skus],
        'scope':'Pinned local bundle definitions, not live database references','live_verified':False,'executable':False}


def scan_families(families, source):
    findings=[]
    for family in families:
        row=source[family['source_product_id']]
        classes=row['product_class'].casefold(); name=row['product_name'].casefold()
        features=parse_features(row['product_features'])
        axes={a['attribute']:a['values'] for a in family['axes']}
        sizes=set(axes.get('wands_size',[])); reasons=[]
        if 'crib bedding' in classes and sizes: reasons.append('crib_set_has_bed_size_axis')
        if 'toddler' in name and sizes-{'Toddler'}: reasons.append('toddler_product_has_non_toddler_sizes')
        if 'trundle' in name and 'Toddler' in sizes: reasons.append('toddler_trundle_option')
        if 'triple' in name and sizes and any(v.count(' over ')!=2 for v in sizes): reasons.append('triple_bed_levels_undefined')
        if 'pillowcase' in name and sizes & {'Toddler','Twin','Full','Queen','King'}: reasons.append('pillowcase_uses_mattress_labels')
        if 'nightstand' in classes and any(option_cm(v)>66.04 for v in axes.get('wands_length',[])): reasons.append('oversized_nightstand_width')
        if 'valances & kitchen curtains' in classes and axes.get('wands_length'): reasons.append('kitchen_window_drop_requires_subtype_check')
        if set(features.get('productsincluded',[]))=={'liner'} and 'bath rugs' in classes and sizes: reasons.append('liner_has_mat_size_options')
        if 'wands_piece_count' in axes: reasons.append('piece_count_needs_explicit_component_manifest')
        if reasons:
            findings.append({'root_sku':family['parent']['sku'],'name':row['product_name'],
                'source_class':row['product_class'],'issues':reasons,'axes':family['axes'],
                'child_count':len(family['variants']),'status':'audit_candidate_not_confirmed_defect','executable':False})
    return sorted(findings,key=lambda r:r['root_sku'])


def render_corrections(roots, before, retired, holds, summary):
    esc=lambda v:html.escape(str(v),quote=True)
    reasons={r['root_sku']:r['reason'] for r in holds}
    root_ids=set(reasons)|{r['sku'] for r in roots if r.get('repair')}
    def options(record):
        return '; '.join(a['label']+': '+', '.join(a['values']) for a in record['axes']) or 'No configurable options'
    cards=[]
    for root in sorted((r for r in roots if r['sku'] in root_ids),key=lambda r:r['sku']):
        old=before[root['sku']];hold=reasons.get(root['sku']);ref=root.get('reference')
        image='<img loading="lazy" src="'+esc(Path(ref['path']).as_uri())+'" alt="Original product reference, not verified for the corrected design">' if ref else '<p>No reference file.</p>'
        removal=[r for r in retired if before[r['sku']].get('parent_sku')==root['sku']]
        content='<p class="held">Held: '+esc(hold)+'</p>' if hold else '<p class="candidate">Local correction candidate. '+esc(root['repair']['rationale'])+'</p>'
        if root['sku'] in REFERENCE_FINDINGS:
            content+='<p class="notice">Known reference issue: '+esc(REFERENCE_FINDINGS[root['sku']]['finding'])+' A non-executable repair draft is included in this packet.</p>'
        rows=[('Product name',old['name'],root['name']),('Product type',old['kind'],root['kind']),
              ('Options',options(old),options(root)),('Sale unit',old['catalog_fields'].get('lab_sale_unit',''),root['catalog_fields'].get('lab_sale_unit',''))]
        table='<table><caption>Current packet and proposed definition</caption><thead><tr><th>Field</th><th>Before</th><th>Candidate</th></tr></thead><tbody>'+''.join('<tr><th scope="row">'+esc(k)+'</th><td>'+esc(a)+'</td><td>'+esc(b)+'</td></tr>' for k,a,b in rows)+'</tbody></table>'
        copy_preview='' if hold else '<details><summary>Proposed product description</summary><div class="copy">'+root['catalog_fields']['description']+'</div></details>'
        inverse='<details><summary>'+str(len(removal))+' proposed child retirements</summary><ul>'+''.join('<li>'+esc(r['sku'])+' → '+esc(r['replacement_sku'])+'</li>' for r in removal)+'</ul><p>No stock transfer or record deletion has been executed.</p></details>' if removal else ''
        child_preview='<details><summary>Candidate dimensions and child options</summary><pre>'+esc(json.dumps({'dimensions':root.get('dimension_design'), 'children':root.get('child_summary',[])},indent=2))+'</pre></details>'
        cards.append('<article id="'+esc(root['sku'])+'"><h2>'+esc(root['name'])+'</h2><p class="sku">'+esc(root['sku'])+'</p>'+content+'<figure>'+image+'<figcaption>Existing reference only. Corrected options and geometry have not been visually accepted.</figcaption></figure>'+table+copy_preview+inverse+child_preview+'</article>')
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WANDS catalog correction review</title><style>body{font:16px system-ui;color:#18241e;background:#f3f4f0;margin:24px}main{max-width:1280px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,540px),1fr));gap:24px}article{background:#fff;padding:24px;border-radius:12px;min-width:0}h2{font-size:21px}figure{margin:16px 0}img{width:100%;height:250px;object-fit:contain}figcaption,.sku{font-size:13px;color:#526159}.held{background:#ffe5da;padding:12px}.candidate{background:#e7f2e8;padding:12px}table{border-collapse:collapse;width:100%;table-layout:fixed}caption{text-align:left;font-weight:600;margin-bottom:8px}th,td{padding:8px;text-align:left;vertical-align:top;border-bottom:1px solid #ddd;overflow-wrap:anywhere}th:first-child{width:22%}details{margin-top:16px}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}.notice{padding:18px;background:#fff2ca}a{color:#225b44}@media(max-width:600px){body{margin:12px}article{padding:16px}th,td{padding:5px;font-size:13px}}</style></head><body><main><h1>Catalog correction review</h1><p class="notice">'+esc(str(summary['candidate_repaired_roots'])+' corrected root candidates; '+str(summary['held_roots'])+' held definitions; '+str(summary['retirement_proposals'])+' proposed child retirements. All changes are local proposals. No imports, deletions, image generation or live writes.')+'</p><p>'+esc(DISCLOSURE)+' '+esc(LABEL)+'.</p><p><a href="pilot-review.html">View the complete 300-product pilot</a></p><section class="grid">'+''.join(cards)+'</section></main></body></html>'


def build(args):
    target=args.output_dir.resolve()
    if target.exists(): raise ValueError('Output exists; use a fresh versioned directory')
    resolving=getattr(args,'resolve_remaining_definitions',False)
    if resolving and not getattr(args,'expand_tested_rules',False):
        raise ValueError('Remaining-definition resolution requires --expand-tested-rules')
    base=args.depth_packet.resolve(); manifest=json.loads((base/'manifest.json').read_text())
    pinned={base/'manifest.json':sha256(base/'manifest.json')}
    for name,digest in manifest['outputs'].items():
        if Path(name).name!=name: raise ValueError('Unsafe packet path')
        pinned[base/name]=digest
    for item in manifest['inputs'].values(): pinned[Path(item['path'])]=item['sha256']
    for name,digest in manifest['references'].items(): pinned[Path(name)]=digest
    for module in ('catalog_repairs.py','repair_designs.py','definition_resolutions.py'):
        p=Path(__file__).with_name(module);pinned[p]=sha256(p)
    def verify():
        for path,digest in pinned.items():
            if not path.is_file() or sha256(path)!=digest: raise ValueError('Pinned input changed: '+str(path))
    verify()
    roots=read_jsonl(base/'products.jsonl'); children=read_jsonl(base/'children.jsonl')
    pilot_ids={r['sku'] for r in roots}
    patch=unique_index(read_csv(Path(manifest['inputs']['patch']['path'])),'sku')
    source=unique_index(read_csv(Path(manifest['inputs']['source']['path']),'\t'),'product_id')
    all_families=read_jsonl(Path(manifest['inputs']['families']['path']))
    queue=read_jsonl(base/'dimension-repair-proposals.jsonl'); definitions=rules()
    if set(definitions)!={r['root_sku'] for r in queue}: raise ValueError('Repair rules do not exactly match frozen queue')
    resolutions=remaining_rules() if resolving else {}
    definitions.update(resolutions)
    for sku,rule in resolutions.items():
        row=source[str(int(sku.removeprefix('WANDS-')))]
        rule['source_resolution'].update(source_product_id=row['product_id'],source_name=row['product_name'],source_class=row['product_class'])
    expansion_decisions=[]
    if getattr(args,'expand_tested_rules',False):
        if not args.media_dir or not args.media_dir.is_dir(): raise ValueError('Expansion requires an existing --media-dir')
        prepared=unique_index(read_csv(Path(manifest['inputs']['prepared']['path'])),'wands_product_id')
        for family in sorted(all_families,key=lambda r:r['parent']['sku']):
            if family['parent']['sku'] in pilot_ids: continue
            row=source[family['source_product_id']]; rule=resolutions.get(family['parent']['sku']) or expansion_rule(row,family)
            if rule is None: continue
            root,group=materialize_family(row,family,prepared[row['product_id']],patch,args.media_dir)
            roots.append(root); children.extend(group); definitions[root['sku']]=rule
            if root['reference']:
                pinned[Path(root['reference']['path'])]=root['reference']['sha256']
            expansion_decisions.append({'root_sku':root['sku'],'source_product_id':row['product_id'],
                'status':'held' if 'hold_reason' in rule else 'local_correction_candidate',
                'reason':rule.get('hold_reason',rule.get('rationale')),'executable':False})
    before=copy.deepcopy(roots+children)
    for r in before: r['catalog_fields']=copy.deepcopy(patch[r['sku']])
    old=unique_index(before,'sku'); families=defaultdict(list)
    for r in before:
        if r.get('parent_sku'): families[r['parent_sku']].append(r)
    out_roots=[];out_children=[];retired=[];holds=[]
    for root in roots:
        root=old[root['sku']]; group=families[root['sku']]; rule=definitions.get(root['sku'])
        if rule:
            if 'hold_reason' in rule: holds.append({'root_sku':root['sku'],'reason':rule['hold_reason'],'executable':False})
            root,group,removed=repair_family(root,group,rule)
            retired.extend(removed)
        out_roots.append(root);out_children.extend(group)
    out_roots=[refine_facts(r) for r in out_roots]
    out_children=[refine_facts(r) for r in out_children]
    child_index={r['sku']:r for r in out_children}
    for root in out_roots:
        # Keep the displayed child summary in sync with newly recovered facets.
        for child in root.get('child_summary',[]):
            child['specifications']=child_index[child['sku']]['specifications']
    after=out_roots+out_children
    validate_candidate(before,after,retired)
    indexed=unique_index(after,'sku')
    for item in retired: item['before']=old[item['sku']]
    changes=[];inverse=[]
    for sku,r in sorted(indexed.items()):
        fields={k:{'before':old[sku].get(k),'after':r.get(k)} for k in sorted(set(old[sku])|set(r)) if old[sku].get(k)!=r.get(k)}
        if fields:
            changes.append({'sku':sku,'fields':fields,'executable':False})
            inverse.append({'sku':sku,'restore':old[sku],'executable':False})
    inverse += [{'sku':r['sku'],'restore':r['before'],'executable':False} for r in retired]
    changed_roots={r['sku'] for r in out_roots if r.get('repair')}
    groups=defaultdict(list)
    for child in out_children: groups[child['parent_sku']].append(child)
    briefs=read_jsonl(base/'gallery-briefs.jsonl')
    previous_jobs={r['source_product_id']:[b for b in briefs if b['source_product_id']==r['source_product_id']] for r in roots}
    new_briefs=[];reference_review=[]
    for root in out_roots:
        if root['sku'] not in changed_roots:
            jobs=previous_jobs[root['source_product_id']]
            new_briefs.extend(jobs or gallery_briefs(indexed[root['gallery_target']['sku']]))
            continue
        chosen=indexed[root['gallery_target']['sku']]
        jobs=gallery_briefs(chosen)
        for job in jobs:
            job['executable']=False
            job['blockers']=sorted(set(job['blockers']+['corrected_product_design_requires_visual_reconciliation']))
            job['required_design_disclosure']=DISCLOSURE
            job['sale_unit']=chosen['catalog_fields']['lab_sale_unit']
            job['prompt']+=' Exact sale unit: '+job['sale_unit']+'. '+DISCLOSURE+' Any conflicting original reference must be repaired, not copied into the new design.'
        new_briefs.extend(jobs)
        reference_review.append({'root_sku':root['sku'],'selected_sku':chosen['sku'],'reference':chosen.get('reference'),
            'selected_options':chosen['variant_options'],'sale_unit':chosen['catalog_fields']['lab_sale_unit'],
            'design':chosen['dimension_design'],'required_checks':['Product identity','Selected color/finish','Corrected dimensions','All included components and quantities','No extra or omitted items'],
            'status':'not_visually_accepted','executable':False})
    global_audit=scan_families(all_families,source)
    after_audit=[]
    for finding in global_audit:
        finding['local_correction_candidate_prepared']=finding['root_sku'] in changed_roots
        finding['scope']='pilot' if finding['root_sku'] in pilot_ids else 'full_catalog_expansion'
        if finding['root_sku'] in changed_roots:
            after_audit.append(validate_resolved_definition(indexed[finding['root_sku']],groups[finding['root_sku']],finding['issues']))
        else:
            after_audit.append({'root_sku':finding['root_sku'],'original_issues':finding['issues'],
                'status':'unresolved','executable':False,'live_verified':False})
    if resolving:
        if any(r['status']!='resolved_in_local_candidate' for r in after_audit) or holds:
            raise ValueError('Remaining-definition batch left unresolved targets')
        for sku,rule in resolutions.items():
            if sku not in indexed: raise ValueError('Resolution target missing from packet: '+sku)
            if rule.get('expected_component_count'):
                for subject in groups[sku] or [indexed[sku]]:
                    if subject['dimension_design'].get('total_component_quantity')!=rule['expected_component_count']:
                        raise ValueError('Fixed assortment component count mismatch: '+sku)
    image_drafts=image_repair_drafts(reference_review)
    bundle_impact=None
    if resolving:
        release_manifest=Path(manifest['inputs']['packet_manifest']['path'])
        release=json.loads(release_manifest.read_text())
        bundle_path=release_manifest.parent/'bundles.jsonl'
        pinned[bundle_path]=release['outputs']['bundles.jsonl']
        verify()
        bundle_impact=bundle_reference_impact(read_jsonl(bundle_path),{r['sku'] for r in changes},{r['sku'] for r in retired})
    links=read_jsonl(base/'recommendations.jsonl')
    link_review=[]
    for link in links:
        for kind in ('alternatives','complements'):
            for candidate in link[kind]:
                link_review.append({'source_sku':link['sku'],'kind':kind,**candidate,'executable':False,
                    'changed_catalog_definition':bool({link['sku'],candidate['target_sku']}&changed_roots),
                    'status':'merchant_review_required'})
    storefront_cases=[{'root_sku':r['sku'],'expected_type':r['kind'],'expected_axes':r['axes'],
        'expected_children':[{'sku':c['sku'],'options':c['variant_options'],'price':c['catalog_fields']['price'],
                             'inventory':{k:c['catalog_fields'].get(k) for k in INVENTORY},
                             'media_accepted':False} for c in groups[r['sku']]],
        'expected_description':r['catalog_fields']['description'],
        'required_disclosures':[DISCLOSURE,LABEL],'required_checks':['Options and price update together','Unavailable options cannot be purchased','Displayed component quantities match selection','Images match selection','Disclosure accompanies synthetic dimensions'],
        'executed':False} for r in out_roots if r['sku'] in changed_roots]
    summary={'version':VERSION,'products':len(out_roots),'selected_children':len(out_children),
        'original_pilot_roots':len(pilot_ids),'expansion_roots':len(expansion_decisions),
        'expansion_corrected_roots':sum(r['status']=='local_correction_candidate' for r in expansion_decisions),
        'expansion_held_roots':sum(r['status']=='held' for r in expansion_decisions),
        'pilot_gallery_subjects_with_dimension_design':sum(indexed[r['gallery_target']['sku']].get('dimension_design',{}).get('status') in {'synthetic_design_complete','synthetic_components_complete'} for r in out_roots if r['sku'] in pilot_ids),
        'repair_queue_roots':len(queue),'candidate_repaired_roots':len(changed_roots),'held_roots':len(holds),
        'changed_active_records':len(changes),'retirement_proposals':len(retired),
        'total_affected_records':len(changes)+len(retired),'root_type_conversions':sum('structural_review' in r for r in out_roots),
        'regenerated_gallery_briefs':5*len(changed_roots),'gallery_briefs':len(new_briefs),
        'gallery_subjects_with_dimension_design':sum(indexed[r['gallery_target']['sku']].get('dimension_design',{}).get('status') in {'synthetic_design_complete','synthetic_components_complete'} for r in out_roots),
        'reference_reviews':len(reference_review),'recommendation_candidates':len(link_review),
        'confirmed_reference_issue_drafts':len(image_drafts),
        'source_facets_recovered':sum(len(r.get('facet_refinements',{}).get('attributes',[])) for r in after),
        'records_with_recovered_facets':sum(bool(r.get('facet_refinements')) for r in after),
        'facet_recovery_by_attribute':dict(Counter(code for r in after for code in r.get('facet_refinements',{}).get('attributes',[]))),
        'full_catalog_family_audit_findings':len(global_audit),'full_catalog_families_scanned':len(all_families),
        'remaining_definition_rules_applied':len(resolutions),
        'resolved_original_family_findings':sum(r['status']=='resolved_in_local_candidate' for r in after_audit),
        'unresolved_original_family_findings':sum(r['status']=='unresolved' for r in after_audit),
        'images_generated':0,'live_writes':0,'deployment_ready':False}
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.catalog-repairs-',dir=target.parent) as temporary:
        stage=Path(temporary)/'packet';stage.mkdir()
        for name,data in [
            ('candidate-products.jsonl',out_roots),('candidate-children.jsonl',out_children),
            ('changes.proposed.jsonl',changes),('inverse.proposed.jsonl',sorted(inverse,key=lambda r:r['sku'])),
            ('retirements.proposed.jsonl',retired),('held-definitions.jsonl',holds),
            ('specifications.sparse.proposed.jsonl',sparse_proposals(after)),
            ('gallery-briefs.jsonl',new_briefs),('reference-review.jsonl',reference_review),
            ('recommendations.review.jsonl',link_review),('full-catalog-option-audit.jsonl',global_audit),
            ('storefront-cases.jsonl',storefront_cases),
            ('expansion-decisions.jsonl',expansion_decisions),
            ('image-repair-drafts.jsonl',image_drafts),
            ('definition-audit.after.jsonl',after_audit),
            ('source-evidence.jsonl',[source[old[sku]['source_product_id']] for sku in sorted(definitions)]),
        ]: write_jsonl(stage/name,data)
        for name in ('benchmark-freeze.json','new-judgment-seeds.jsonl','collections.json'):
            (stage/name).write_bytes((base/name).read_bytes())
        write_json(stage/'rules.json',definitions)
        if bundle_impact is not None: write_json(stage/'bundle-reference-impact.json',bundle_impact)
        write_json(stage/'resolution-policy.json',{'version':VERSION,'enabled':resolving,
            'approval':RESOLUTION_APPROVAL if resolving else None,'source_evidence_preserved':True,
            'shared_eav_option_renames_permitted':False,
            'import_requirement':'Create/reuse new option values and assign them to the listed SKUs only; never rename an old shared option globally.',
            'manufacturer_verified':False,'import_approved':False})
        write_json(stage/'validation.json',{'identity_partition_valid':True,'family_matrices_complete':True,
            'price_ladders_monotonic':True,'unchanged_stock_and_prices_except_explicit_type_conversion_seed':True,
            'source_facts_preserved':True,'component_quantities_valid':True,'inverse_records_complete':True,
            'magento_import_validated':False,'visual_acceptance':False})
        write_json(stage/'schema-requirements.json',{'executable':False,'existing_specification_attributes':list(ATTRIBUTES),
            'additional_storage_needed':['lab_spec_dimension_disclosure','component-aware specification payload','synthetic design disclosure'],
            'renderer_required':'Render provenance beside measurements; never flatten component dimensions into product EAV fields',
            'clear_policy':'Empty source fields are not delete instructions; stale replaced synthetic fields require snapshot-aware clearing'})
        (stage/'pilot-review.html').write_text(render_review(out_roots,summary,links),encoding='utf-8')
        correction_html=render_corrections(out_roots,old,retired,holds,summary)
        correction_html=correction_html.replace('View the complete 300-product pilot',f'View the complete {len(out_roots)}-root candidate packet')
        (stage/'review.html').write_text(correction_html,encoding='utf-8')
        verify()
        write_json(stage/'manifest.json',{**summary,'baseline_packet':str(base),'inputs':{str(p):d for p,d in sorted(pinned.items())},
            'outputs':{p.name:sha256(p) for p in sorted(stage.iterdir())},
            'gates':['Review corrected definitions and proposed child retirement/type conversion','Reconcile selected-variant images','Implement disclosure-aware sparse storage and rendering','Fresh destination snapshot, exact diff, backup and approval before import']})
        stage.rename(target)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--depth-packet',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--expand-tested-rules',action='store_true',help='Also prepare explicitly reviewed out-of-pilot families')
    parser.add_argument('--resolve-remaining-definitions',action='store_true',help='Apply the approved synthetic resolutions for the exact remaining 44-product queue')
    parser.add_argument('--media-dir',type=Path,help='Existing parent reference directory; required for expansion')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    log=args.output_dir.with_name(args.output_dir.name+'.log');log.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=log,level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        summary=build(args);logging.info('Complete: %s',json.dumps(summary,sort_keys=True))
        if args.json: print(json.dumps(summary,indent=2))
        return 0
    except Exception:
        logging.exception('Catalog correction failed; source packet and live catalog unchanged')
        return 1


if __name__=='__main__': raise SystemExit(main())
