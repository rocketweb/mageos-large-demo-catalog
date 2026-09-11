#!/usr/bin/env python3
"""Verify a narrowly scoped remote theme capture against the prior catalog fixture."""
import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from build_realism_review import write_json
from prepare_catalog import sha256
from verify_catalog_repairs import check


def canonical(rows):
    return sorted(json.dumps({k:None if v is None else str(v) for k,v in row.items()},sort_keys=True) for row in rows)


def verify(args):
    check(not args.output_dir.exists(),'Choose fresh output')
    paths={name:getattr(args,name).resolve() for name in ('snapshot','baseline','plan')}
    snapshot,baseline,plan=[json.loads(paths[name].read_text()) for name in ('snapshot','baseline','plan')]
    collector=Path(__file__).with_name('snapshot_rehearsal_schema.php');paths['collector']=collector
    check(snapshot['collector_sha256']==sha256(collector),'Collector changed')
    check(snapshot['plan_sha256']==baseline['plan_sha256']==sha256(paths['plan']),'Different catalog scope')
    check(snapshot['consistent_read_only'] is True and snapshot['storefront_metadata'] is True and snapshot['host']=='relevance.comtom.lab','Wrong capture boundary')
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(snapshot['captured_at'])).total_seconds()
    check(-360<=age<=86400,'Capture is not fresh')
    metadata={'theme','theme_file','design_change','directory_currency_rate'}
    check(set(snapshot['rows'])==set(baseline['rows'])|metadata,'Unexpected captured tables')
    check(set(snapshot['ddl'])==set(snapshot['rows']),'Schema coverage differs')
    for table,rows in baseline['rows'].items():
        if table!='core_config_data':check(canonical(rows)==canonical(snapshot['rows'][table]),'Catalog fixture drift: '+table)
    check(not baseline['rows']['core_config_data'],'Baseline unexpectedly contains configuration')
    rows=snapshot['rows'];products=rows['catalog_product_entity']
    check(len(products)==17 and {p['sku'] for p in products}==set(plan['approved_products']),'Wrong product scope')
    check(rows['theme_file']==[],'Theme contents escaped scope')
    check(all(str(r['store_id']) in ('0','2') for r in rows['design_change']),'Unrelated design assignment')
    check(all(r['currency_from']==r['currency_to']=='USD' for r in rows['directory_currency_rate']),'Unrelated currency')
    assignments={}
    for row in rows['core_config_data']:
        key=f'{row["scope"]}:{row["scope_id"]}'
        check(row['path']=='design/theme/theme_id' and key in ('default:0','websites:2','stores:2') and str(row['value']).isdigit(),'Unrelated configuration')
        check(key not in assignments,'Duplicate theme assignment');assignments[key]=str(row['value'])
    selected=next((assignments[k] for k in ('stores:2','websites:2','default:0') if k in assignments),None)
    matches=[r for r in rows['theme'] if str(r['theme_id'])==selected]
    check(len(matches)==1 and matches[0]['theme_path']=='Hyva/default' and matches[0]['area']=='frontend','Store no longer resolves to expected Hyva theme')
    args.output_dir.mkdir(parents=True);paths['verifier']=Path(__file__).resolve()
    write_json(args.output_dir/'result.json',{'captured_at':snapshot['captured_at'],'host':snapshot['host'],
        'catalog_scope_unchanged':True,'products':17,'tables':len(rows),'rows':sum(map(len,rows.values())),
        'effective_theme_id':selected,'effective_theme_path':matches[0]['theme_path'],'synthetic_theme_metadata':False,
        'configuration_rows':len(rows['core_config_data']),'theme_file_content_rows':0,'remote_catalog_writes':0,
        'live_definitions_updated':False,'media_uploaded':False,'publication_approved':False,
        'inputs':{str(path):sha256(path) for path in paths.values()}})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot','baseline','plan','output-dir'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'),level=logging.INFO)
    try:verify(args);logging.info('Remote catalog scope unchanged; actual Hyva assignment verified')
    except Exception:logging.exception('Capture acceptance failed');raise SystemExit(1)
