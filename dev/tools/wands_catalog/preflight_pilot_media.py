#!/usr/bin/env python3
"""Compare exact pilot media proposals with a fresh snapshot; prepare review-only rollback."""
import argparse
from collections import Counter
import json
import logging
from pathlib import Path
import tempfile
from build_nursery_assortment import pin_packet
from build_realism_review import write_json
from prepare_catalog import sha256
from snapshot_preflight import load_snapshot, ident, literal
from run_catalog_media_pilot import verify_pins
from verify_catalog_repairs import check

MEDIA={'image','small_image','thumbnail','image_label','small_image_label','thumbnail_label'}


def inspect(assignments,request,tables):
    entities={r['sku']:r for r in tables['catalog_product_entity']};attrs={r['attribute_code']:r for r in tables['eav_attribute']}
    byid={str(r['entity_id']):r['sku'] for r in entities.values()};values={};issues=[];diff=[]
    for kind in ('varchar','text','int'):
        for r in tables.get('catalog_product_entity_'+kind,[]):values[(str(r['entity_id']),str(r['attribute_id']),str(r['store_id']))]=r['value']
    if set(entities)!=set(request['skus']):issues.append({'code':'snapshot_scope_mismatch','missing':sorted(set(request['skus'])-set(entities))})
    for sku,expected in request['intended_types'].items():
        if sku in entities and entities[sku]['type_id']!=expected:issues.append({'code':'type_mismatch','sku':sku,'expected':expected,'actual':entities[sku]['type_id']})
    for parent,children in request['configurable_links'].items():
        if parent not in entities:continue
        links={byid.get(str(r['product_id']), 'outside:'+str(r['product_id'])) for r in tables['catalog_product_super_link'] if str(r['parent_id'])==str(entities[parent]['entity_id'])}
        if links!=set(children):issues.append({'code':'configurable_link_mismatch','sku':parent,'actual':sorted(links),'expected':sorted(children)})
    codes={str(r['attribute_id']):r['attribute_code'] for r in attrs.values()}
    for parent,expected in request.get('configurable_axes',{}).items():
        if parent not in entities:continue
        actual={codes.get(str(r['attribute_id']),'unknown:'+str(r['attribute_id'])) for r in tables.get('catalog_product_super_attribute',[]) if str(r['product_id'])==str(entities[parent]['entity_id'])}
        if actual!=set(expected):issues.append({'code':'configurable_axes_mismatch','sku':parent,'actual':sorted(actual),'expected':sorted(expected)})
    labels={str(r['option_id']):r['value'] for r in tables['eav_attribute_option_value'] if str(r['store_id'])=='0'}
    owners={str(r['option_id']):str(r['attribute_id']) for r in tables.get('eav_attribute_option',[])}
    target_ids=set()
    for a in assignments:
        sku=a['target_sku']
        if sku not in entities:issues.append({'code':'missing_target','sku':sku});continue
        eid=str(entities[sku]['entity_id']);target_ids.add(eid)
        for field,expected in a['expected_definition_fields'].items():
            attr=attrs.get(field);actual=values.get((eid,str(attr['attribute_id']),'0')) if attr else None
            if actual!=expected:issues.append({'code':'definition_mismatch','sku':sku,'field':field,'actual':actual,'expected':expected})
        for code,expected in a['selected_options'].items():
            attr=attrs.get(code);oid=values.get((eid,str(attr['attribute_id']),'0')) if attr else None
            if labels.get(str(oid))!=expected:issues.append({'code':'selected_option_mismatch','sku':sku,'attribute':code,'actual':labels.get(str(oid)),'expected':expected})
            if not attr or owners.get(str(oid))!=str(attr['attribute_id']):issues.append({'code':'selected_option_owner_mismatch','sku':sku,'attribute':code})
        for code in sorted(MEDIA):
            attr=attrs.get(code)
            if not attr:issues.append({'code':'missing_media_attribute','sku':sku,'attribute':code});continue
            source_field={'image':'base_image','image_label':'base_image_label'}.get(code,code)
            diff.append({'sku':sku,'attribute':code,'store_id':0,'before':values.get((eid,str(attr['attribute_id']),'0')),
                         'proposed_import_value':a['fields'].get(source_field),
                         'actual_after_db_value':'pending native importer rehearsal'})
            overrides=[r for r in tables['catalog_product_entity_varchar'] if str(r['entity_id'])==eid and str(r['attribute_id'])==str(attr['attribute_id']) and str(r['store_id'])!='0']
            if overrides:issues.append({'code':'store_override_requires_review','sku':sku,'attribute':code,'rows':len(overrides)})
    gallery=[r for r in tables['catalog_product_entity_media_gallery_value_to_entity'] if str(r['entity_id']) in target_ids]
    if gallery:issues.append({'code':'existing_gallery_requires_retirement_review','associations':len(gallery),'reason':'Add/update does not remove historical incorrect gallery images. No retirement authorized by this packet.'})
    websites=[r for r in tables['catalog_product_website'] if str(r['product_id']) in target_ids]
    return {'issues':issues,'field_diff':diff,'target_products_found':len(target_ids),'proposed_field_operations':len(diff),
            'existing_gallery_associations':len(gallery),'website_bindings':websites,
            'issue_counts':dict(Counter(r['code'] for r in issues))}


def upload_plan(assignments,exports):
    files=[];names=set()
    for row in assignments:
        image=row['image'];name=image['file']
        check(name==Path(name).name and name.endswith('.jpg') and name not in names,'Invalid or duplicate import filename')
        names.add(name);source=exports.resolve()/name
        check(source.is_file() and not source.is_symlink(),'Import file missing or symlinked')
        check(sha256(source)==image['sha256'] and source.stat().st_size==image['bytes'],'Import bytes changed')
        check(row['fields']['base_image']=='/wands/pilot-media-v1/'+name,'Import path changed')
        files.append({'sku':row['target_sku'],'source':str(source),'sha256':image['sha256'],'bytes':image['bytes'],
                      'destination':'/opt/comtom/stores/relevance/src/pub/media/import/wands/pilot-media-v1/'+name})
    return {'host':'37.27.126.105','ssh_alias':'comtom-public','container':'farm-relevance-php-1','files':files,
            'total_bytes':sum(r['bytes'] for r in files),'overwrite_existing':False,'delete_existing':False,'uploaded':False,
            'requires_exact_approval':True,'collision_policy':'Check every destination before transfer; abort on different bytes. Identical bytes may be retained.',
            'post_transfer_check':'All five destination SHA-256 values must match before importer use.'}


def inverse(tables,manifest,target_skus):
    ids={str(r['entity_id']) for r in tables['catalog_product_entity'] if r['sku'] in target_skus}
    attrs={str(r['attribute_id']) for r in tables['eav_attribute'] if r['attribute_code'] in MEDIA}
    check(ids,'No exact inverse targets');qualify=lambda t:ident(manifest['database'])+'.'+ident(manifest['prefix']+t)
    lines=['-- REVIEW ONLY. Freeze writes and rehearse on a clone before approved use.',
           '-- Restores only the five image targets, including labels and all prior store scopes.',
           '-- Shared gallery master rows and binary files are never deleted.','START TRANSACTION;']
    for table in ('catalog_product_entity_media_gallery_value','catalog_product_entity_media_gallery_value_to_entity','catalog_product_entity_varchar'):
        if table.endswith('_varchar') and not attrs:continue
        extra=' AND attribute_id IN ('+','.join(literal(a) for a in sorted(attrs))+')' if table.endswith('_varchar') else ''
        lines.append('DELETE FROM '+qualify(table)+' WHERE entity_id IN ('+','.join(literal(i) for i in sorted(ids))+')'+extra+';')
        for r in tables[table]:
            if str(r['entity_id']) in ids and (not table.endswith('_varchar') or str(r['attribute_id']) in attrs):
                lines.append('INSERT INTO '+qualify(table)+' ('+','.join(ident(k) for k in r)+') VALUES ('+','.join(literal(v) for v in r.values())+');')
    return '\n'.join(lines+['-- New unused gallery masters and files remain for separately approved cleanup.','ROLLBACK;'])+'\n'


def build(a):
    out=a.output_dir.resolve();check(not out.exists() and not out.is_symlink(),'Use a fresh preflight directory')
    pins={};pin_packet(a.assignment,pins,'wands-pilot-media-assignment-v1');pin_packet(a.exports,pins,'wands-storefront-exports-v1')
    request_path=a.assignment/'snapshot-request.json';m,request,tables=load_snapshot(a.snapshot,request_path,a.max_age_hours)
    check(request['packet_sha256']==sha256(a.assignment/'assignments.json'),'Assignment/snapshot mismatch')
    rows=json.loads((a.assignment/'assignments.json').read_text());result=inspect(rows,request,tables)
    result.update({'status':'blocked' if result['issues'] else 'rehearsal_required','publication_approved':False,
                   'snapshot_sha256':sha256(a.snapshot/'manifest.json'),'snapshot_host':m['host'],'snapshot_captured_at':m['captured_at'],
                   'native_importer_executed':False,'rollback_rehearsed':False,
                   'remaining_gates':['Resolve definition/type/option mismatches','Review existing galleries and store overrides','Binary media and database backup',
                                      'Native importer validation and rollback rehearsal in clone','Exact apply approval','Live product/variant/media verification']})
    targets={r['target_sku'] for r in rows};ids={str(r['entity_id']) for r in tables['catalog_product_entity'] if r['sku'] in targets}
    links=[r for r in tables['catalog_product_entity_media_gallery_value_to_entity'] if str(r['entity_id']) in ids]
    mids={str(r['value_id']) for r in links};files=[r for r in tables['catalog_product_entity_media_gallery'] if str(r['value_id']) in mids]
    pins[str((a.snapshot/'manifest.json').resolve())]=sha256(a.snapshot/'manifest.json')
    for table,info in m['tables'].items():pins[str((a.snapshot/(table+'.jsonl')).resolve())]=info['sha256']
    for path in (Path(__file__),Path(__file__).with_name('snapshot_preflight.py')):pins[str(path.resolve())]=sha256(path)
    check(not any(Path(p).is_relative_to(out) or out.is_relative_to(Path(p).parent) for p in pins if Path(p).name=='manifest.json'),'Output overlaps evidence')
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent,prefix='.'+out.name+'-') as folder:
        stage=Path(folder);write_json(stage/'preflight.json',result);write_json(stage/'binary-backup-required.json',{'existing_media_rows':files,'backup_completed':False})
        write_json(stage/'upload-plan.review.json',upload_plan(rows,a.exports))
        (stage/'rollback-media.review.sql').write_text(inverse(tables,m,targets))
        verify_pins(pins);write_json(stage/'manifest.json',{'version':'wands-pilot-media-preflight-v1','inputs':pins,
            'outputs':{p.name:sha256(p) for p in stage.iterdir()},'publication_approved':False});stage.rename(out)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for f in ('assignment','snapshot','exports','output-dir'):p.add_argument('--'+f,required=True,type=Path)
    p.add_argument('--max-age-hours',type=float,default=24);a=p.parse_args();a.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=a.output_dir.with_suffix('.log'),level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        r=build(a);logging.info('Media preflight: %s',json.dumps({k:v for k,v in r.items() if k not in ('issues','field_diff')},sort_keys=True));return int(bool(r['issues']))
    except Exception:logging.exception('Preflight stopped without publication');return 1


if __name__=='__main__':raise SystemExit(main())
