#!/usr/bin/env python3
"""Scope the five-family definition prerequisite locally. Never execute catalog writes."""
import argparse
from collections import Counter
import datetime as dt
import json
import logging
from pathlib import Path
import tempfile
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from build_realism_review import write_json
from run_catalog_media_pilot import verify_pins
from snapshot_preflight import load_snapshot
from verify_catalog_repairs import check

ROOTS={'WANDS-000056','WANDS-003897','WANDS-017842','WANDS-030335','WANDS-035295'}
COPY_FIELDS=('name','description','short_description','meta_title','meta_description','lab_sale_unit')


def select_candidates(definitions):
    products=read_jsonl(definitions/'candidate-products.jsonl')
    children=read_jsonl(definitions/'candidate-children.jsonl')
    active=[r for r in products if r['sku'] in ROOTS]+[r for r in children if r.get('parent_sku') in ROOTS]
    retired=[r for r in read_jsonl(definitions/'retirements.proposed.jsonl') if r['replacement_sku'] in ROOTS]
    check(len(active)==13 and len(retired)==4,'Pilot dependency scope changed')
    check(len({r['sku'] for r in active+retired})==17,'Duplicate pilot SKU')
    return active,retired


def option_matches(code,label,tables):
    attrs={r['attribute_code']:r for r in tables['eav_attribute']}
    owners={str(r['option_id']):str(r['attribute_id']) for r in tables['eav_attribute_option']}
    aid=str(attrs[code]['attribute_id'])
    return {str(r['option_id']) for r in tables['eav_attribute_option_value'] if str(r['store_id'])=='0' and r['value']==label and owners.get(str(r['option_id']))==aid}


def resolve_option(code,label,tables):
    matches=option_matches(code,label,tables)
    check(len(matches)==1,f'Missing or ambiguous existing option {code}: {label}; shared labels must not be renamed')
    return next(iter(matches))


def compare(active,retired,tables):
    entities={r['sku']:r for r in tables['catalog_product_entity']}
    attrs={r['attribute_code']:r for r in tables['eav_attribute']}
    values={}
    for backend in ('varchar','text','int','decimal','datetime'):
        for r in tables['catalog_product_entity_'+backend]:values[(str(r['entity_id']),str(r['attribute_id']),str(r['store_id']))]=r
    changes=[];gates=[]
    def field(sku,code,after):
        attr=attrs.get(code);check(attr is not None,'Missing attribute '+code)
        eid=str(entities[sku]['entity_id']);aid=str(attr['attribute_id']);old=values.get((eid,aid,'0'))
        if any(key[0]==eid and key[1]==aid and key[2]!='0' for key in values):gates.append({'sku':sku,'attribute':code,'reason':'store_override_requires_review'})
        before=old['value'] if old else None
        if str(before)!=str(after):changes.append({'sku':sku,'entity_id':eid,'table':'catalog_product_entity_'+attr['backend_type'],
             'attribute':code,'attribute_id':aid,'store_id':0,'before':before,'after':after,'before_row':old,'operation':'update' if old else 'insert'})
    for r in active:
        sku=r['sku'];check(sku in entities,'Missing product '+sku)
        for code in COPY_FIELDS:field(sku,code,r['catalog_fields'][code])
        for code,label in r.get('variant_options',{}).items():
            if option_matches(code,label,tables):field(sku,code,resolve_option(code,label,tables))
            else:
                field(sku,code,{'new_option_attribute':code,'label':label})
                gates.append({'sku':sku,'attribute':code,'label':label,'reason':'new_option_requires_creation'})
        if entities[sku]['type_id']!=r['kind']:
            changes.append({'sku':sku,'entity_id':str(entities[sku]['entity_id']),'table':'catalog_product_entity','attribute':'type_id',
                            'before':entities[sku]['type_id'],'after':r['kind'],'operation':'update'})
    for r in retired:
        check(r['sku'] in entities,'Missing retirement target');field(r['sku'],'status','2')
    return changes,gates


def build(a):
    out=a.output_dir.resolve();check(not out.exists() and not out.is_symlink(),'Choose a fresh output')
    manifest=json.loads((a.definitions/'manifest.json').read_text())
    check(manifest['version']=='wands-catalog-repairs-v3','Wrong definitions')
    pins={**manifest['inputs'],str((a.definitions/'manifest.json').resolve()):sha256(a.definitions/'manifest.json'),
          **{str((a.definitions/name).resolve()):digest for name,digest in manifest['outputs'].items()}}
    verify_pins(pins);active,retired=select_candidates(a.definitions)
    candidate={'active':active,'retired':retired,'policy':{'global_option_renames':False,'delete_products':False,'inventory_transfer':False,'price_changes':False}}
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent,prefix='.'+out.name+'-') as tmp:
        stage=Path(tmp);write_json(stage/'candidates.json',candidate)
        request={'version':1,'expected_host':'relevance.comtom.lab','packet_sha256':sha256(stage/'candidates.json'),
                 'skus':sorted(r['sku'] for r in active+retired),'bundle_skus':[],
                 'attributes':sorted(set(COPY_FIELDS)|{'wands_size','wands_piece_count','wands_finish','status','visibility','image','small_image','thumbnail'}),
                 'intended_types':{r['sku']:r['kind'] for r in active},'configurable_links':{},'variant_options':{},'configurable_axes':{}}
        write_json(stage/'snapshot-request.json',request)
        if a.snapshot:
            check(a.request is not None and a.dependencies is not None,'Request and dependency evidence required')
            check(sha256(a.request)==sha256(stage/'snapshot-request.json'),'Prepared request changed')
            m,_,tables=load_snapshot(a.snapshot,a.request)
            dep=json.loads(a.dependencies.read_text())
            check(dep['request_sha256']==sha256(a.request) and dep['consistent_read_only'] and dep['host']==m['host'],'Wrong dependency evidence')
            age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(dep['captured_at'])).total_seconds()
            check(-360<=age<=86400,'Stale dependency evidence')
            check({(r['sku'],str(r['entity_id']),r['type_id']) for r in dep['entities']}=={(r['sku'],str(r['entity_id']),r['type_id']) for r in tables['catalog_product_entity']},'Dependency entities drifted')
            changes,gates=compare(active,retired,tables)
            write_json(stage/'fields.proposed.json',changes)
            creations=[{'attribute':code,'label':label,'new_rows':{'eav_attribute_option':1,'eav_attribute_option_value':1},
                        'store_id':0,'option_id':'allocate at approved application; never predict'} for code,label in sorted({(r['after']['new_option_attribute'],r['after']['label']) for r in changes if isinstance(r['after'],dict)})]
            write_json(stage/'options.create.proposed.json',creations)
            nursery=next(r for r in tables['catalog_product_entity'] if r['sku']=='WANDS-000056');nid=str(nursery['entity_id'])
            detach={table:[r for r in tables[table] if str(r[column])==nid] for table,column in (
                ('catalog_product_super_link','parent_id'),('catalog_product_relation','parent_id'),('catalog_product_super_attribute','product_id'))}
            detach['catalog_product_super_attribute_label']=[r for r in dep['axis_labels'] if str(r['product_id'])==nid]
            retired_ids={str(r['entity_id']) for r in tables['catalog_product_entity'] if r['sku'] in {item['sku'] for item in retired}}
            check({str(r['product_id']) for r in detach['catalog_product_super_link']}==retired_ids,'Nursery child links differ from retirement scope')
            check({str(r['child_id']) for r in detach['catalog_product_relation']}==retired_ids,'Nursery relations differ from retirement scope')
            check(not dep['axis_prices'],'Axis pricing requires additional explicit scope')
            write_json(stage/'relationships.detach.proposed.json',detach)
            entity_skus={str(r['entity_id']):r['sku'] for r in tables['catalog_product_entity']}
            attrs={str(r['attribute_id']):r['attribute_code'] for r in tables['eav_attribute']}
            parents={r['sku']:r for r in active if r['sku'] in ROOTS and r['kind']=='configurable'}
            label_changes=[]
            for old in dep['axis_labels']:
                sku=entity_skus[str(old['product_id'])]
                if sku not in parents:continue
                expected=next(axis['label'] for axis in parents[sku]['axes'] if axis['attribute']==attrs[str(old['attribute_id'])])
                if old['value']!=expected:label_changes.append({'sku':sku,'table':'catalog_product_super_attribute_label','before_row':old,'after':expected})
            write_json(stage/'axis-labels.proposed.json',label_changes)
            write_json(stage/'inventory.before.json',{'stock':tables['cataloginventory_stock_item'],'sources':tables.get('inventory_source_item',[]),'reservations':dep['reservation_totals'],
                       'policy':'No stock movement or writes proposed. Nursery salability must be established on a clone; request a separate decision if activation needs inventory changes.'})
            write_json(stage/'dependencies.review.json',dep)
            write_json(stage/'summary.json',{'active_products':len(active),'retained_disabled_children':len(retired),
                'distinct_proposed_product_writes':len({r['sku'] for r in changes}),
                'field_operations':len(changes),'field_operations_by_attribute':dict(Counter(r['attribute'] for r in changes)),
                'new_option_rows':sum(sum(r['new_rows'].values()) for r in creations),'axis_label_updates':len(label_changes),
                'planned_row_operations_before_activation_and_media':len(changes)+sum(map(len,detach.values()))+sum(sum(r['new_rows'].values()) for r in creations)+len(label_changes),
                'relationship_row_deletions':{k:len(v) for k,v in detach.items()},'snapshot_captured_at':m['captured_at'],
                'scope_gates':gates,'inbound_bundle_selections':len(dep['bundle_selections']),'product_links_to_review':len(dep['product_links']),
                'global_option_renames':0,'product_deletions':0,'inventory_writes':0,'price_writes':0,
                'status':'review_only_not_apply_ready','publication_approved':False,'rollback_rehearsed':False})
            pins[str(a.dependencies.resolve())]=sha256(a.dependencies)
            pins[str(a.request.resolve())]=sha256(a.request)
            pins[str((a.snapshot/'manifest.json').resolve())]=sha256(a.snapshot/'manifest.json')
            pins.update({str((a.snapshot/(t+'.jsonl')).resolve()):v['sha256'] for t,v in m['tables'].items()})
        for script in (Path(__file__),Path(__file__).with_name('snapshot_catalog.php'),Path(__file__).with_name('snapshot_pilot_dependencies.php')):
            pins[str(script.resolve())]=sha256(script)
        verify_pins(pins);write_json(stage/'manifest.json',{'version':'wands-pilot-definition-scope-v1','inputs':pins,'outputs':{p.name:sha256(p) for p in stage.iterdir()},'publication_approved':False});stage.rename(out)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('definitions','output-dir'):p.add_argument('--'+field,type=Path,required=True)
    for field in ('snapshot','request','dependencies'):p.add_argument('--'+field,type=Path)
    a=p.parse_args();a.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=a.output_dir.with_suffix('.log'),level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:build(a);logging.info('Scoped proposal saved; no catalog writes');return 0
    except Exception:logging.exception('Scoping stopped without catalog writes');return 1


if __name__=='__main__':raise SystemExit(main())
