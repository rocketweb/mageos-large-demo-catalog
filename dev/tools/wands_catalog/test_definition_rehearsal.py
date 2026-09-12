#!/usr/bin/env python3
"""Exercise the migration and inverse on disposable SQLite snapshot fixtures, not Mage-OS."""
import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from prepare_catalog import sha256
from prepare_definition_migration import PRIMARY
from build_realism_review import write_json
from verify_catalog_repairs import check


def fixture(plan,path):
    db=sqlite3.connect(path);grouped={}
    for g in plan['guards']:
        group=grouped.setdefault(g['table'],{'rows':[],'columns':set()})
        group['rows']+=g['rows']
        group['columns'].update(k for r in g['rows'] for k in r)
        group['columns'].update(k for clause in g['clauses'] for k in clause)
    for op in plan['operations']:
        group=grouped.setdefault(op['table'],{'rows':[],'columns':set()})
        group['columns'].update(op['selector']);group['columns'].update(op['after'] or {});group['columns'].update(op['before'] or {})
    for table,g in grouped.items():
        columns=sorted(g['columns']);pk=PRIMARY.get(table,'value_id')
        if pk not in columns:pk=None
        db.execute('CREATE TABLE "'+table+'" ('+','.join('"'+c+'" '+('INTEGER PRIMARY KEY AUTOINCREMENT' if c==pk else 'TEXT') for c in columns)+')')
        seen=set()
        for r in g['rows']:
            key=json.dumps(r,sort_keys=True)
            if key in seen:continue
            seen.add(key);db.execute('INSERT INTO "'+table+'" ('+','.join('"'+k+'"' for k in r)+') VALUES ('+','.join('?' for _ in r)+')',list(r.values()))
    db.commit();db.close()


def contents(path):
    db=sqlite3.connect(path)
    tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    data={t:sorted([list(r) for r in db.execute('SELECT * FROM "'+t+'"')],key=str) for t in tables};db.close();return data


def run(a):
    check(not a.output_dir.exists(),'Choose a fresh output');a.output_dir.mkdir(parents=True)
    plan=json.loads(a.plan.read_text());digest=sha256(a.plan);checks=[]
    def call(path,action,receipt,expected=0,extra=(),plan_path=None):
        plan_path=plan_path or a.plan
        command=[a.php,str(Path(__file__).with_name('rehearse_definition_migration.php')),'--plan='+str(plan_path.resolve()),'--plan-sha256='+sha256(plan_path),
                 '--sqlite='+str(path),'--action='+action,'--receipt='+str(receipt),*extra]
        r=subprocess.run(command,capture_output=True,text=True)
        check(r.returncode==expected,'Unexpected result for '+action+': '+(Path(str(receipt)+'.log').read_text() if Path(str(receipt)+'.log').exists() else r.stderr[:500]))
        check(not r.stdout and not r.stderr,'Routine output leaked into terminal')
    base=a.output_dir.resolve()
    path=base/'rehearsal.sqlite';fixture(plan,path);before=contents(path)
    call(path,'dry-run',base/'dry-run.json');check(contents(path)==before,'Dry-run wrote data');checks.append('dry_run_zero_writes')
    call(path,'apply',base/'interrupted.json',expected=1,extra=('--fail-after=40',));check(contents(path)==before,'Interruption leaked changes');checks.append('interrupted_transaction_rolled_back')
    receipt=base/'applied.json';call(path,'apply',receipt)
    check(contents(path)!=before,'Apply did not change data')
    applied=json.loads(receipt.read_text());check(len(applied['operations'])==105,'Wrong operation count');checks.append('all_105_operations_applied')
    after=contents(path);call(path,'apply',base/'duplicate.json',expected=1);check(contents(path)==after,'Duplicate application wrote');checks.append('duplicate_apply_blocked')
    original_receipt=receipt.read_bytes()
    changed=json.loads(original_receipt);changed['state']='accidental receipt edit';receipt.write_text(json.dumps(changed))
    call(path,'rollback',receipt,expected=1);check(contents(path)==after,'Corrupted receipt allowed rollback');checks.append('receipt_tampering_blocked')
    receipt.write_bytes(original_receipt)
    db=sqlite3.connect(path)
    option=applied['bindings']['new_option'];aid=plan['new_option_attribute_id']
    db.execute('INSERT INTO catalog_product_entity_int (entity_id,attribute_id,store_id,value) VALUES (?,?,?,?)',('999999',str(aid),'0',option));db.commit();db.close()
    drift=contents(path);call(path,'rollback',receipt,expected=1);check(contents(path)==drift,'External option consumer was changed');checks.append('external_consumer_blocks_inverse')
    db=sqlite3.connect(path);db.execute('DELETE FROM catalog_product_entity_int WHERE entity_id=?',('999999',));db.commit();db.close()
    call(path,'rollback',receipt);check(contents(path)==before,'Inverse did not restore complete table contents');checks.append('inverse_full_table_parity')
    call(path,'rollback',receipt,expected=1);check(contents(path)==before,'Repeated inverse wrote');checks.append('duplicate_inverse_blocked')
    historical=base/'historical.json';call(path,'apply',historical)
    # Simulate an otherwise valid old receipt. Rebinding fixture hashes models elapsed
    # time without giving the real runner a clock override or a freshness bypass.
    aged_plan={**plan,'snapshot_captured_at':'2020-01-01T00:00:00+00:00'}
    aged_path=base/'aged-plan.json';write_json(aged_path,aged_plan)
    aged_receipt=json.loads(historical.read_text());aged_receipt['plan_sha256']=sha256(aged_path);write_json(historical,aged_receipt)
    marker=Path(str(historical)+'.committed');data=json.loads(marker.read_text());data['receipt_sha256']=sha256(historical);write_json(marker,data)
    call(path,'rollback',historical,plan_path=aged_path);check(contents(path)==before,'Historical inverse failed');checks.append('rollback_does_not_expire')
    call(path,'apply',base/'stale-apply.json',expected=1,plan_path=aged_path);check(contents(path)==before,'Stale apply wrote');checks.append('stale_apply_blocked')
    result={'checks':checks,'count':len(checks),'plan_sha256':digest,'engine':'SQLite snapshot fixture',
            'runner_sha256':sha256(Path(__file__).with_name('rehearse_definition_migration.php')),'harness_sha256':sha256(Path(__file__)),
            'mariadb_tested':False,'magento_bootstrapped':False,'storefront_verified':False,'live_writes':False,
            'scope':'All loaded fixture rows restored; this is not a full schema, MySQL, plugin, trigger or indexer acceptance test.'}
    write_json(base/'result.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--php',required=True)
    a=p.parse_args()
    try:run(a)
    except Exception:
        import logging
        logging.basicConfig(filename=a.output_dir.with_suffix('.log'),level=logging.INFO);logging.exception('Rehearsal failed');raise SystemExit(1)
