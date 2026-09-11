#!/usr/bin/env python3
"""Verify guest price indexing, unchanged live prices and isolated rollback."""
import argparse
from decimal import Decimal
import hashlib
import json
import logging
from pathlib import Path
from build_realism_review import write_json
from prepare_catalog import sha256
from verify_catalog_repairs import check
from verify_mageos_rehearsal import index, number, VERSIONS


def check_price_rows(products, rows, children):
    products=index(products);prices=index(rows)
    check(set(products)==set(prices),'Active product/index coverage mismatch')
    for sku,product in products.items():
        row=prices[sku]
        number(row['price'],product['base_price'])
        if product['type']=='simple':
            for field in ('final_price','min_price','max_price'):
                number(row[field],product['checks']['pricing_final'])
            number(product['checks']['model_final'],row['final_price'])
        else:
            check(sku in children and children[sku],'Missing configurable family')
            finals=[Decimal(str(prices[c]['final_price'])) for c in children[sku]]
            number(row['min_price'],min(finals));number(row['max_price'],max(finals))
            number(product['checks']['pricing_final'],min(finals))
            number(product['checks']['model_final'],min(finals))
    for field,value in {'price':74.99,'final_price':63.74,'min_price':63.74,'max_price':63.74}.items():
        number(prices['WANDS-000056'][field],value)


def verify(args):
    check(not args.output_dir.exists(),'Choose fresh output')
    paths={k:getattr(args,k).resolve() for k in ('before','after','restored','candidates','receipt','plan')}
    data={k:json.loads(p.read_text()) for k,p in paths.items()}
    before,after,restored=(data[k] for k in ('before','after','restored'))
    plan=data['plan'];expected=set(plan['approved_products'])
    check(len(expected)==17 and len(plan['operations'])==105,'Wrong scope')
    for name in ('probe_mageos_pricing.php','rehearsal_runtime.php'):
        paths[name]=Path(__file__).with_name(name)
    for phase in (before,after,restored):
        check(phase['versions']==VERSIONS and phase['database']==before['database'] and phase['database'].startswith('wands_rehearsal_'),'Wrong runtime/database')
        check(phase['reindexed'] is True and phase['live_writes'] is False and phase['storefront_verified'] is False,'Wrong acceptance boundary')
        check(phase['probe_sha256']==sha256(paths['probe_mageos_pricing.php']) and phase['runtime_sha256']==sha256(paths['rehearsal_runtime.php']) and phase['plan_sha256']==sha256(paths['plan']),'Changed code/plan')
        check(set(index(phase['products']))==expected and not any(p['errors'] for p in phase['products']),'Missing product or pricing exception')
        check(all(int(r['customer_group_id'])==0 and int(r['website_id'])==2 for r in phase['price_index']),'Price index escaped guest WANDS scope')
    active=[p for p in after['products'] if p['status']==1]
    candidates=data['candidates']['active']
    check(len(active)==13 and set(index(active))==set(index(candidates)),'Wrong active set')
    children={p['sku']:[c['sku'] for c in candidates if c.get('parent_sku')==p['sku']] for p in candidates if p['kind']=='configurable'}
    check_price_rows(active,after['price_index'],children)
    old=index(before['products'])
    for product in after['products']:
        if product['sku']!='WANDS-000056':
            for field in ('base_price','special_price'):
                check(product[field]==old[product['sku']][field],'Unapproved repricing: '+product['sku'])
    check(before['products']==restored['products'] and before['price_index']==restored['price_index'],'Price runtime/index rollback mismatch')
    check(before['after_table_hashes']==restored['after_table_hashes'],'Indexed baseline table-row parity failed')
    receipt=data['receipt'];dsn=f"mysql:host=127.0.0.1;port=13380;dbname={before['database']};charset=utf8mb4"
    check(receipt['dsn_sha256']==hashlib.sha256(dsn.encode()).hexdigest() and receipt['plan_sha256']==sha256(paths['plan']) and len(receipt['operations'])==105,'Wrong receipt')
    for suffix in ('.committed','.rolled-back'):paths[suffix]=Path(str(paths['receipt'])+suffix)
    check(json.loads(paths['.committed'].read_text())['receipt_sha256']==sha256(paths['receipt']),'Receipt integrity failure')
    check(json.loads(paths['.rolled-back'].read_text())['verified_before_parity'] is True,'Missing rollback')
    paths['verifier']=Path(__file__).resolve();prices=index(after['price_index'])
    args.output_dir.mkdir(parents=True)
    write_json(args.output_dir/'result.json',{'versions':VERSIONS,'database':after['database'],'active_price_rows':13,
        'nursery':{k:prices['WANDS-000056'][k] for k in ('price','final_price')},
        'configurable_ranges':{sku:{k:prices[sku][k] for k in ('min_price','max_price')} for sku in children},
        'unapproved_repricing':False,'indexed_baseline_rollback_parity':True,'fixture_tables':len(restored['after_table_hashes']),
        'configuration':after['configuration'],'storefront_verified':False,'cart_verified':False,'live_writes':False,'publication_approved':False,
        'inputs':{str(path):sha256(path) for path in paths.values()}})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','after','restored','candidates','receipt','plan','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'),level=logging.INFO)
    try:verify(args);logging.info('Guest native price-index lifecycle and inverse verified')
    except Exception:logging.exception('Pricing verification failed');raise SystemExit(1)
