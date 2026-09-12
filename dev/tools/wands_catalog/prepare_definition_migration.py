#!/usr/bin/env python3
"""Build the approved pilot migration for isolated rehearsal, not live execution."""
import argparse
from decimal import Decimal
import json
import logging
from pathlib import Path
import tempfile
from build_nursery_assortment import pin_packet
from build_realism_review import write_json
from prepare_catalog import sha256
from run_catalog_media_pilot import verify_pins
from snapshot_preflight import load_snapshot
from verify_catalog_repairs import check

PRIMARY={'catalog_product_entity':'entity_id','catalog_product_super_link':'link_id',
         'catalog_product_super_attribute':'product_super_attribute_id','catalog_product_super_attribute_label':'value_id',
         'cataloginventory_stock_item':'item_id','inventory_source_item':'source_item_id',
         'eav_attribute_option':'option_id','eav_attribute_option_value':'value_id'}


def row_operation(table,before,updates=None,selector=None):
    if selector is None:
        key=PRIMARY.get(table,'value_id')
        selector={key:before[key]} if key in before else {k:before[k] for k in ('parent_id','child_id')}
    return {'table':table,'selector':selector,'before':before,'after':None if updates is None else {**(before or {}),**updates}}


def activation(tables,entities):
    nid=str(entities['WANDS-000056']['entity_id']);seed=str(entities['WANDS-000056-TODDLER-56FF']['entity_id'])
    attrs={r['attribute_code']:str(r['attribute_id']) for r in tables['eav_attribute']}
    stock=[r for r in tables['cataloginventory_stock_item'] if str(r['product_id'])==nid]
    seed_stock=[r for r in tables['cataloginventory_stock_item'] if str(r['product_id'])==seed]
    sources=[r for r in tables['inventory_source_item'] if r['sku']=='WANDS-000056']
    seed_sources=[r for r in tables['inventory_source_item'] if r['sku']=='WANDS-000056-TODDLER-56FF']
    check(len(stock)==len(seed_stock)==len(sources)==len(seed_sources)==1,'Ambiguous activation inventory')
    check(sources[0]['source_code']==seed_sources[0]['source_code']=='default','Unexpected source')
    check(Decimal(seed_stock[0]['qty'])==Decimal(seed_sources[0]['quantity'])==47,'Approved seed drifted')
    dates={attrs[c] for c in ('special_from_date','special_to_date')}
    check(not any(str(r['entity_id'])==nid and str(r['attribute_id']) in dates and r['value'] for r in tables['catalog_product_entity_datetime']), 'Promotion date override requires separate review')
    ops=[row_operation('cataloginventory_stock_item',stock[0],{'qty':'47.0000','manage_stock':1,'use_config_manage_stock':0}),
         row_operation('inventory_source_item',sources[0],{'quantity':'47.0000'})]
    for code,value in (('price','74.990000'),('special_price','63.740000'),('weight','1.750000')):
        existing=[r for r in tables['catalog_product_entity_decimal'] if str(r['entity_id'])==nid and str(r['attribute_id'])==attrs[code]]
        check(all(str(r['store_id'])=='0' for r in existing) and len(existing)<=1,'Price/weight store override requires review')
        before=existing[0] if existing else None
        selector={'entity_id':int(nid),'attribute_id':int(attrs[code]),'store_id':0}
        ops.append(row_operation('catalog_product_entity_decimal',before, {**selector,'value':value},selector))
    return ops


def build(a):
    out=a.output_dir.resolve();check(not out.exists() and not out.is_symlink(),'Choose a fresh output')
    pins={};pin_packet(a.scope,pins,'wands-pilot-definition-scope-v1')
    m,request,tables=load_snapshot(a.snapshot,a.scope/'snapshot-request.json')
    check(sha256(a.snapshot/'manifest.json') in pins.values(),'Snapshot is not the scoped evidence')
    summary=json.loads((a.scope/'summary.json').read_text())
    check(summary['planned_row_operations_before_activation_and_media']==100,'Approved scope count changed')
    check(all(g['reason']=='new_option_requires_creation' for g in summary['scope_gates']),'Unresolved definition gate')
    dep=json.loads((a.scope/'dependencies.review.json').read_text())
    check(not dep['reservation_totals'] and not dep['bundle_selections'] and not dep['product_links'],'New dependency review needed')
    entities={r['sku']:r for r in tables['catalog_product_entity']};ids=[r['entity_id'] for r in entities.values()]
    attrs={r['attribute_code']:r for r in tables['eav_attribute']};aid=attrs['wands_piece_count']['attribute_id']
    nursery=entities['WANDS-000056'];check(nursery['has_options']==nursery['required_options']==0,'Unexpected nursery option flags')
    ops=[{'table':'eav_attribute_option','selector':{'option_id':'@new_option'},'before':None,
          'after':{'attribute_id':aid,'sort_order':1006},'generate':'new_option'},
         {'table':'eav_attribute_option_value','selector':{'option_id':'@new_option','store_id':0},'before':None,
          'after':{'option_id':'@new_option','store_id':0,'value':'6 Pieces'}}]
    for r in json.loads((a.scope/'fields.proposed.json').read_text()):
        if r['table']=='catalog_product_entity':ops.append(row_operation(r['table'],entities[r['sku']],{'type_id':r['after']}));continue
        value='@new_option' if isinstance(r['after'],dict) else r['after']
        selector={'entity_id':int(r['entity_id']),'attribute_id':int(r['attribute_id']),'store_id':r['store_id']}
        ops.append(row_operation(r['table'],r['before_row'],{**selector,'value':value},selector))
    detach=json.loads((a.scope/'relationships.detach.proposed.json').read_text())
    for table in ('catalog_product_super_attribute_label','catalog_product_super_link','catalog_product_relation','catalog_product_super_attribute'):
        for row in detach[table]:
            before={k:v for k,v in row.items() if table!='catalog_product_super_attribute_label' or k not in ('product_id','attribute_id')}
            ops.append(row_operation(table,before))
    for r in json.loads((a.scope/'axis-labels.proposed.json').read_text()):
        before={k:v for k,v in r['before_row'].items() if k not in ('product_id','attribute_id')}
        ops.append(row_operation(r['table'],before,{'value':r['after']}))
    check(len(ops)==100,'Base operation count changed');ops+=activation(tables,entities)
    guards=[]
    for table,columns in [('catalog_product_entity',['entity_id']),('cataloginventory_stock_item',['product_id']),
                          ('inventory_source_item',['sku']),('catalog_product_super_link',['parent_id','product_id']),
                          ('catalog_product_relation',['parent_id','child_id']),('catalog_product_super_attribute',['product_id']),
                          ('catalog_product_website',['product_id']),('catalog_category_product',['product_id']),
                          ('catalog_product_entity_media_gallery_value_to_entity',['entity_id']),('catalog_product_entity_media_gallery_value',['entity_id'])]+[
                              ('catalog_product_entity_'+kind,['entity_id']) for kind in ('varchar','text','int','decimal','datetime')]:
        values=request['skus'] if columns==['sku'] else ids
        guards.append({'table':table,'clauses':[{c:values} for c in columns],'rows':tables[table]})
    option_attrs=sorted({r['attribute_id'] for r in tables['eav_attribute_option']})
    guards.append({'table':'eav_attribute_option','clauses':[{'attribute_id':option_attrs}],'rows':tables['eav_attribute_option']})
    guards.append({'table':'eav_attribute_option_value','clauses':[{'option_id':[r['option_id'] for r in tables['eav_attribute_option']]}],'rows':tables['eav_attribute_option_value']})
    labels=[{k:v for k,v in r.items() if k not in ('product_id','attribute_id')} for r in dep['axis_labels']]
    guards.append({'table':'catalog_product_super_attribute_label','clauses':[{'product_super_attribute_id':[r['product_super_attribute_id'] for r in tables['catalog_product_super_attribute']]}],'rows':labels})
    guards.append({'table':'eav_attribute','clauses':[{'attribute_id':[r['attribute_id'] for r in tables['eav_attribute']]}],'rows':tables['eav_attribute']})
    guard_only=[('catalog_product_bundle_selection','product_id','bundle_selections'),('catalog_product_link','linked_product_id','product_links')]
    for table,column,key in guard_only:guards.append({'table':table,'clauses':[{column:ids}],'rows':dep[key]})
    if dep['inventory_reservation_table_present']:guards.append({'table':'inventory_reservation','clauses':[{'sku':request['skus']}],'rows':[]})
    guards.append({'table':'url_rewrite','clauses':[{'entity_id':ids,'entity_type':['product']}],'rows':dep['url_rewrites']})
    for p in (Path(__file__),Path(__file__).with_name('rehearse_definition_migration.php')):pins[str(p.resolve())]=sha256(p)
    plan={'version':1,'environment':'isolated_rehearsal_only','approved_products':request['skus'],'expected_operations':105,
          'snapshot_captured_at':m['captured_at'],'scope_sha256':sha256(a.scope/'manifest.json'),
          'activation':{'approved':True,'quantity':47,'price':'74.99','special_price':'63.74','weight':'1.75'},
          'operations':ops,'guards':guards,'new_option_attribute_id':aid,'publication_approved':False,
          'limitations':['No Magento services, plugins, indexers or storefront acceptance in this database-only runner','Fresh atomic live preflight and approved production adapter required']}
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent,prefix='.'+out.name+'-') as tmp:
        stage=Path(tmp);write_json(stage/'migration.json',plan)
        verify_pins(pins);write_json(stage/'manifest.json',{'version':'wands-definition-migration-v1','inputs':pins,'outputs':{'migration.json':sha256(stage/'migration.json')},'publication_approved':False});stage.rename(out)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('scope','snapshot','output-dir'):p.add_argument('--'+field,type=Path,required=True)
    a=p.parse_args();a.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=a.output_dir.with_suffix('.log'),level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:build(a);logging.info('105-operation rehearsal packet prepared, live execution prohibited');return 0
    except Exception:logging.exception('Preparation stopped without catalog writes');return 1


if __name__=='__main__':raise SystemExit(main())
