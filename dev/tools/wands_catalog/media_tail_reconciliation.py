"""Resume only unapplied media after exact full-catalog database acceptance."""
from pathlib import Path
import json
from build_expanded_catalog import csv_rows,write_csv,variations,digest
from prepare_catalog import sha256
from bulk_expansion_images import atomic_json
from verify_expansion_install import compare
from native_metadata import media_label

CANDIDATE='921e5e1a0d8a386c93bf0f80dd6543c9d3561e5ad27e31df5b80b9d3e0d8502e'

def completed_media(plan,receipts,reconcile_import_deadlock=False):
    state=json.loads((receipts/'state.json').read_text())
    if state.get('state')!='failed; reconcile partial state before retry' or (state['index']%2 and not reconcile_import_deadlock) or state['plan_sha256']!=sha256(plan/'deployment.json'):
        raise ValueError('Media resume requires exact stopped validation evidence')
    record=json.loads((plan/'deployment.json').read_text());count=0;pins={};metadata_done=[]
    if state['index']%2:
        log=receipts/f'{state["index"]:04d}-import.log'
        evidence=log.read_text()
        if state.get('exit_code')!=1 or 'SQLSTATE[40001]' not in evidence or '1213 Deadlock found' not in evidence:
            raise ValueError('Explicit media import deadlock evidence required')
        pins[str(log)]=sha256(log)
    for index in range(state['index']):
        path=receipts/f'{index:04d}-completed.json';entry=json.loads(path.read_text())
        if entry['exit_code']!=0 or entry['plan_sha256']!=state['plan_sha256']:raise ValueError('Applied prefix receipt changed')
        pins[str(path)]=sha256(path)
        action=record['actions'][index//2]
        if entry['action']['kind']=='import':
            if Path(action['file']).name.endswith('-media.csv'):count+=action['rows']
            else:metadata_done.append(action)
    pending=record['actions'][state['index']//2]
    if not Path(pending['file']).name.endswith('-media.csv'):raise ValueError('Resume is not an unimported media batch')
    media_started=False
    for action in record['actions']:
        is_media=Path(action['file']).name.endswith('-media.csv')
        if media_started and not is_media:raise ValueError('Metadata is not complete before media tail')
        media_started=media_started or is_media
        src=plan/action['file']
        if sha256(src)!=record['files'][action['file']]:raise ValueError('Prior imported inputs changed')
        pins[str(src)]=sha256(src)
    pins[str(plan/'deployment.json')]=sha256(plan/'deployment.json');pins[str(receipts/'state.json')]=sha256(receipts/'state.json')
    return count,pins

def prepare_receipt(original,current,prior_plan,prior_receipts,package,reconcile_import_deadlock=False):
    original,current,prior_plan,prior_receipts,package=map(lambda p:Path(p).resolve(),(original,current,prior_plan,prior_receipts,package))
    before=json.loads(original.read_text());live=json.loads(current.read_text())
    rows={r['sku']:r for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv') for r in csv_rows(package/'data'/name)}
    links={(s,g['sku']) for s,r in rows.items() if r['product_type']=='configurable' for g in variations(r)}
    acceptance=compare(before,live,rows,links)
    if not acceptance['passed'] or acceptance['wands_products']!=107688:raise ValueError('Full product catalog is not verified before media resume')
    count,pins=completed_media(prior_plan,prior_receipts,reconcile_import_deadlock)
    pins[str(original)]=sha256(original);pins[str(current)]=sha256(current)
    return {'schema':1,'candidate_sha256':CANDIDATE,'original_snapshot':str(original),'current_snapshot':str(current),
        'prior_plan':str(prior_plan),'prior_receipts':str(prior_receipts),'source_pins':pins,
        'completed_media_rows':count,'database_acceptance':acceptance,'product_records_written':0,
        'reconcile_import_deadlock':reconcile_import_deadlock}

def prepare_tail(package,snapshot,output,receipt,batch_size=1000):
    for path,pin in receipt['source_pins'].items():
        if sha256(Path(path))!=pin:raise ValueError('Media resume source evidence changed')
    count,_=completed_media(Path(receipt['prior_plan']),Path(receipt['prior_receipts']),receipt.get('reconcile_import_deadlock',False))
    live=json.loads(snapshot.read_text());original=json.loads(Path(receipt['original_snapshot']).read_text())
    if live!=json.loads(Path(receipt['current_snapshot']).read_text()) or count!=receipt['completed_media_rows']:raise ValueError('Media destination changed since reconciliation')
    rows={r['sku']:r for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv') for r in csv_rows(package/'data'/name)}
    links={(s,g['sku']) for s,r in rows.items() if r['product_type']=='configurable' for g in variations(r)}
    if compare(original,live,rows,links)!=receipt['database_acceptance']:raise ValueError('Media resume acceptance changed')
    media=csv_rows(package/'data/4-media.csv')
    for row in media:
        if any(row[k]!=media_label(rows[row['sku']]['name']) for k in ('base_image_label','small_image_label','thumbnail_label')):raise ValueError('Native image label changed or too long')
    applied=[];prior=json.loads((Path(receipt['prior_plan'])/'deployment.json').read_text())
    for a in prior['actions']:
        if Path(a['file']).name.endswith('-media.csv'):applied.extend(csv_rows(Path(receipt['prior_plan'])/a['file']))
        if len(applied)>=count:break
    if applied[:count]!=media[:count]:raise ValueError('Already applied media prefix differs from accepted assignments')
    output.mkdir();batches=output/'batches';batches.mkdir();actions=[]
    for index,start in enumerate(range(count,len(media),batch_size)):
        part=media[start:start+batch_size];name=f'batches/{index+1:04d}-media.csv';write_csv(output/name,part)
        actions.append({'action':'native-import','file':name,'rows':len(part),'preserve_existing_stock':True,'validate_before_apply':True})
    old={s:r for s,r in original['products'].items() if r['wands']};now={s:r for s,r in live['products'].items() if r['wands']}
    rec={'schema':1,'candidate_sha256':CANDIDATE,'target_root':live['root'],'original_before_wands_products':original['wands_products'],
         'before_wands_products':107688,'already_imported_skus':sorted(set(now)-set(old)),'original_snapshot':receipt['original_snapshot'],'source_pins':receipt['source_pins'],'media_only':True}
    plan={'schema':1,'target_root':live['root'],'website_code':'wands','website_id':live['website_id'],'store_id':live['store_id'],
        'candidate_sha256':CANDIDATE,'export_manifest_sha256':sha256(package/'manifest.json'),'snapshot_sha256':sha256(snapshot),
        'reconciliation':rec,'media_tail_reconciliation':receipt,
        'delta':{'before_wands_products':107688,'after_wands_products':107688,'product_inserts':0,'products_deleted':0},
        'actions':actions,'media_assignments':len(media),'excluded_disabled_skus':json.loads((package/'manifest.json').read_text())['excluded_disabled_skus'],
        'files':{str(p.relative_to(output)):sha256(p) for p in output.rglob('*') if p.is_file()}}
    atomic_json(output/'deployment.json',plan);return rec
