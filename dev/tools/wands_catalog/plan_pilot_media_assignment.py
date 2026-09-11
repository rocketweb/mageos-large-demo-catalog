#!/usr/bin/env python3
"""Prepare media-only assignment proposals for exact reviewed options; never import."""
import argparse
import csv
import json
import logging
from pathlib import Path
import tempfile
from build_nursery_assortment import pin_packet
from build_realism_review import write_json
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from run_catalog_component_pilot import verify_layouts
from run_catalog_media_pilot import verify_pins
from verify_catalog_repairs import check


def snapshot_attributes(axes):
    return sorted({'image','image_label','small_image','small_image_label','thumbnail','thumbnail_label',
                   'name','description','lab_sale_unit'} | {code for codes in axes.values() for code in codes})


def choose_target(product,options):
    target=product['gallery_target']
    check(target['options']==options,'Selected image options differ from catalog')
    if product['kind']=='simple':
        check(not options and target['sku']==product['sku'],'Simple target changed')
    else:
        check(product['kind']=='configurable','Unsupported product type')
        matches=[c for c in product['child_summary'] if c['sku']==target['sku'] and c['options']==options]
        check(len(matches)==1,'Selected variant missing or ambiguous')
    return target['sku']


def build(a):
    out=a.output_dir.resolve();check(not out.exists() and not out.is_symlink(),'Use a fresh assignment directory')
    briefs,pins=verify_layouts(a.layouts);pin_packet(a.exports,pins,'wands-storefront-exports-v1')
    dm=json.loads((a.definitions/'manifest.json').read_text());check(dm['version']=='wands-catalog-repairs-v3','Wrong definitions')
    incoming={**dm['inputs'],str((a.definitions/'manifest.json').resolve()):sha256(a.definitions/'manifest.json'),
              **{str((a.definitions/k).resolve()):v for k,v in dm['outputs'].items()}}
    check(all(k not in pins or pins[k]==v for k,v in incoming.items()),'Conflicting definition pins');verify_pins(incoming);pins.update(incoming)
    products={r['sku']:r for r in read_jsonl(a.definitions/'candidate-products.jsonl')}
    children={r['sku']:r for r in read_jsonl(a.definitions/'candidate-children.jsonl')}
    exports=json.loads((a.exports/'exports.json').read_text());obs=json.loads(a.observations.read_text())
    check(obs['exports_sha256']==sha256(a.exports/'exports.json') and obs['publication_approved'] is False,'Export review changed')
    accepted={r['root_sku']:r for r in obs['families']};assignments=[];context={};links={};axes={};variants={};held=[]
    check(len(exports)==len(accepted)==5,'Pilot export scope changed')
    for e in exports:
        sku=e['root_sku'];product=products[sku];b=[x for x in briefs if x['root_sku']==sku]
        check(b and all(x['selected_options']==b[0]['selected_options'] for x in b),'Ambiguous image options')
        check(e['physical_instances']==sum(x['required_instances'] for x in b),'Image sale unit count differs')
        target=choose_target(product,b[0]['selected_options']);review=accepted[sku]
        check(review['verdict']=='initial_visual_pass' and review['files']==e['files'],'Unreviewed export')
        image=next(f for f in e['files'] if f['role']=='import');check(sha256(a.exports/image['file'])==image['sha256'],'Import image changed')
        p=products[target] if target in products else children[target]
        label=p['name']+' - synthetic lab assortment'
        path='/wands/pilot-media-v1/'+image['file']
        fields={'sku':target,'store_view_code':'','base_image':path,'base_image_label':label,
                'small_image':path,'small_image_label':label,'thumbnail':path,'thumbnail_label':label}
        assignments.append({'root_sku':sku,'target_sku':target,'expected_type':'simple','selected_options':b[0]['selected_options'],
                            'physical_instances':e['physical_instances'],'image':image,'fields':fields,
                            'expected_definition_fields':{k:p['catalog_fields'][k] for k in ('name','description','lab_sale_unit')},
                            'mode':'add_update_media_roles_only','existing_gallery_policy':'preserve; inspect conflicts before approval',
                            'publication_approved':False})
        context[sku]=product['kind']
        for c in product.get('child_summary',[]):
            context[c['sku']]='simple';variants[c['sku']]=c['options']
        if product['kind']=='configurable':
            links[sku]=[c['sku'] for c in product['child_summary']];axes[sku]=product['axis_codes']
            held.append({'sku':sku,'reason':'Parent and non-selected variants are not assigned a selected-option hero; retain separate review gate.'})
    check(len({r['target_sku'] for r in assignments})==5,'Duplicate target')
    for p in (Path(__file__),a.observations):pins[str(p.resolve())]=sha256(p)
    check(not any(Path(p).is_relative_to(out) or out.is_relative_to(Path(p).parent) for p in pins if Path(p).name=='manifest.json'),'Output overlaps evidence')
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent,prefix='.'+out.name+'-') as folder:
        stage=Path(folder);write_json(stage/'assignments.json',assignments)
        with (stage/'media.review.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(assignments[0]['fields']));writer.writeheader();writer.writerows(r['fields'] for r in assignments)
        request={'version':1,'expected_host':'relevance.comtom.lab','packet_sha256':sha256(stage/'assignments.json'),
                 'skus':sorted(context),'intended_types':context,'bundle_skus':[],'configurable_links':links,'configurable_axes':axes,'variant_options':variants,
                 'attributes':snapshot_attributes(axes)}
        write_json(stage/'snapshot-request.json',request)
        write_json(stage/'scope.json',{'target_products':5,'image_role_assignments':15,'label_assignments':15,'import_files':5,
                   'import_bytes':sum(r['image']['bytes'] for r in assignments),'snapshot_context_products':len(context),
                   'configurable_parent_assignments':0,'bundle_changes':0,'held_parents':held,
                   'store_scope':'Default scope proposed. Website/store blast radius must be checked in the fresh remote snapshot.',
                   'live_preflight':'pending','publication_approved':False})
        verify_pins(pins);write_json(stage/'manifest.json',{'version':'wands-pilot-media-assignment-v1','inputs':pins,
                   'outputs':{p.name:sha256(p) for p in stage.iterdir()},'publication_approved':False});stage.rename(out)
    return {'target_products':5,'context_products':len(context),'image_roles':15,'held_parents':len(held)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for f in ('exports','observations','definitions','layouts','output-dir'):p.add_argument('--'+f,required=True,type=Path)
    a=p.parse_args();a.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=a.output_dir.with_suffix('.log'),level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:logging.info('Assignment scope: %s',json.dumps(build(a),sort_keys=True));return 0
    except Exception:logging.exception('Assignment planning stopped without publication');return 1


if __name__=='__main__':raise SystemExit(main())
