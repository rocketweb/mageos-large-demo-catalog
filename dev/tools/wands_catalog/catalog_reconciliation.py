"""Reconcile only the exact new-simple prefix applied by a failed native run."""
from pathlib import Path
import json
from build_expanded_catalog import csv_rows
from prepare_catalog import sha256
from verify_expansion_install import compare
from prepare_expansion_deployment import CANDIDATE_SHA256

def verify_partial(before,current,desired,required_new,allowed_new):
    old={s:r for s,r in before['products'].items() if r['wands']}
    actual={s:r for s,r in current['products'].items() if r['wands']}
    new=set(actual)-set(old)
    if not required_new<=new<=allowed_new or set(actual)-set(desired):raise ValueError('Partial population outside exact applied batches')
    expected={s:{'product_type':r['type']} for s,r in old.items()}
    expected.update({s:{'product_type':desired[s]['product_type']} for s in new})
    links={(r['parent'],r['child']) for r in before['configurable_links'] if r['parent'] in expected}
    result=compare(before,current,expected,links)
    if not result['passed']:raise ValueError('Partial import changed protected data, IDs, original types, links or stock')
    return sorted(new)

def prepare(before_path,current_path,plan_path,receipts,desired):
    before_path=Path(before_path).resolve();current_path=Path(current_path).resolve();plan_path=Path(plan_path).resolve();receipts=Path(receipts).resolve()
    before=json.loads(before_path.read_text());current=json.loads(current_path.read_text());plan=json.loads(plan_path.read_text());state=json.loads((receipts/'state.json').read_text())
    if (before['root']!='/Users/matt/code/mageos-latest' or before['wands_products']!=42994
            or plan['candidate_sha256']!=CANDIDATE_SHA256 or plan['snapshot_sha256']!=sha256(before_path)
            or state['plan_sha256']!=sha256(plan_path) or state['state']!='failed; reconcile partial state before retry'
            or state['index']%2!=1):raise ValueError('Reconciliation requires the exact failed original Studio plan')
    required=set();allowed=set();pins={str(p):sha256(p) for p in (before_path,current_path,plan_path,receipts/'state.json')}
    for index in range(state['index']//2+1):
        action=plan['actions'][index]
        if action['action']!='native-import' or not Path(action['file']).name.endswith('-new-simple.csv'):
            raise ValueError('Only the examined new-simple prefix may reconcile')
        source=plan_path.parent/action['file']
        if sha256(source)!=plan['files'][action['file']]:raise ValueError('Applied batch source changed')
        batch={r['sku'] for r in csv_rows(source)};allowed|=batch;pins[str(source)]=sha256(source)
        if index<state['index']//2:
            receipt=receipts/f'{index*2+1:04d}-completed.json'
            if not receipt.exists() or json.loads(receipt.read_text()).get('exit_code')!=0:raise ValueError('Missing applied batch receipt')
            pins[str(receipt)]=sha256(receipt);required|=batch
    new=verify_partial(before,current,desired,required,allowed)
    return {'schema':1,'candidate_sha256':CANDIDATE_SHA256,'target_root':before['root'],
            'original_before_wands_products':42994,'before_wands_products':current['wands_products'],
            'already_imported_skus':new,'required_applied_skus':sorted(required),'allowed_applied_skus':sorted(allowed),
            'original_snapshot':str(before_path),'current_snapshot':str(current_path),'source_pins':pins,
            'records_deleted':0,'original_stock_preserved':True,'protected_data_preserved':True}

def validate(receipt,live,desired):
    if (receipt.get('schema')!=1 or receipt.get('candidate_sha256')!=CANDIDATE_SHA256
            or receipt.get('target_root')!='/Users/matt/code/mageos-latest' or receipt.get('original_before_wands_products')!=42994):
        raise ValueError('Wrong reconciliation receipt')
    for path,pin in receipt['source_pins'].items():
        if sha256(Path(path))!=pin:raise ValueError('Reconciliation evidence changed')
    before=json.loads(Path(receipt['original_snapshot']).read_text());current=json.loads(Path(receipt['current_snapshot']).read_text())
    if live!=current:raise ValueError('Partial destination changed after reconciliation')
    new=verify_partial(before,live,desired,set(receipt['required_applied_skus']),set(receipt['allowed_applied_skus']))
    if new!=receipt['already_imported_skus'] or len(new)+42994!=live['wands_products']:raise ValueError('Reconciliation count changed')
    return receipt
