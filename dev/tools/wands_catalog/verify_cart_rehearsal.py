#!/usr/bin/env python3
"""Verify unsaved guest-cart behavior against actual indexed product prices."""
import argparse
from decimal import Decimal
import json
import logging
from pathlib import Path
from build_realism_review import write_json
from prepare_catalog import sha256
from verify_catalog_repairs import check
from verify_mageos_rehearsal import index, number, VERSIONS


def verify_positive(case, ids, price):
    check(case['accepted'] is True and case['exception'] is None and case['message'] is None,'Valid cart request failed')
    parent,child=case['sku'],case['selected_sku'];items=case['items']
    check(len(items)==(1 if parent==child else 2),'Wrong item count')
    roots=[i for i in items if i['parent_product_id'] is None]
    check(len(roots)==1,'Wrong visible item count');root=roots[0]
    check(str(root['product_id'])==str(ids[parent]),'Wrong parent product ID')
    check(root['product_type']==('simple' if parent==child else 'configurable'),'Wrong parent type')
    for item in items:
        check(item['item_sku']==child and not item['has_error'],'Wrong selected SKU/item error')
        number(item['qty'],case['qty'])
    number(root['unit_price'],price)
    number(root['row_total'],(Decimal(str(price))*Decimal(str(case['qty']))).quantize(Decimal('.01')))
    if parent!=child:
        leaf=next(i for i in items if i['parent_product_id'] is not None)
        check(str(leaf['product_id'])==str(ids[child]) and str(leaf['parent_product_id'])==str(ids[parent]) and leaf['product_type']=='simple','Wrong selected child identity/relationship')
        number(leaf['unit_price'],0);number(leaf['row_total'],0)


def verify(args):
    check(not args.output_dir.exists(),'Choose fresh output')
    paths={k:getattr(args,k).resolve() for k in ('evidence','pricing','candidates','plan')}
    data={k:json.loads(p.read_text()) for k,p in paths.items()}
    evidence=data['evidence'];pricing=data['pricing'];candidates=data['candidates'];plan=data['plan']
    for name in ('probe_mageos_cart.php','rehearsal_runtime.php','probe_mageos_pricing.php'):paths[name]=Path(__file__).with_name(name)
    check(evidence['versions']==pricing['versions']==VERSIONS and evidence['database']==pricing['database'] and evidence['database'].startswith('wands_rehearsal_'),'Wrong runtime')
    check(evidence['probe_sha256']==sha256(paths['probe_mageos_cart.php']) and evidence['runtime_sha256']==sha256(paths['rehearsal_runtime.php']),'Changed cart runtime')
    check(pricing['probe_sha256']==sha256(paths['probe_mageos_pricing.php']) and not any(p['errors'] for p in pricing['products']),'Invalid pricing evidence')
    check(pricing['reindexed'] is False,'Use a fresh read-only price probe after the indexing process exits')
    check(evidence['plan_sha256']==pricing['plan_sha256']==sha256(paths['plan']) and evidence['candidates_sha256']==sha256(paths['candidates']),'Changed scope')
    check(evidence['database_unchanged'] is True and evidence['before_table_hashes']==evidence['after_table_hashes']==pricing['after_table_hashes'],'Cart changed database or pricing evidence drifted')
    check(evidence['quotes_saved']==evidence['orders_created']==evidence['reservations_created']==0 and evidence['live_writes'] is False,'Cart mutation boundary failed')
    check(evidence['storefront_verified'] is False and evidence['checkout_verified'] is False,'Unsupported browser/checkout claim')
    products=index(pricing['products']);prices=index(pricing['price_index']);ids={sku:p['entity_id'] for sku,p in products.items()}
    check(set(ids)==set(plan['approved_products']) and len(ids)==17,'Wrong product scope')
    expected={}
    for c in candidates['active']:
        if c['kind']=='configurable':
            for prefix in ('missing-','invalid-'):expected[prefix+c['sku']]=(False,c['sku'],None,1)
        else:expected['valid-'+c['sku']]=(True,c.get('parent_sku') or c['sku'],c['sku'],1)
    for c in candidates['retired']:expected['retired-'+c['sku']]=(False,c['sku'],None,1)
    for qty in (47,48):expected['nursery-qty-'+str(qty)]=(qty==47,'WANDS-000056','WANDS-000056',qty)
    cases={c['id']:c for c in evidence['cases']}
    check(len(cases)==len(evidence['cases'])==len(expected)==21 and set(cases)==set(expected),'Wrong cart-case coverage')
    for key,(accepted,parent,selected,qty) in expected.items():
        case=cases[key]
        check(case['sku']==parent and case.get('selected_sku')==selected and case['qty']==qty and case['expected'] is accepted and case['accepted'] is accepted,'Cart scenario mismatch: '+key)
        if accepted:verify_positive(case,ids,prices[selected]['final_price'])
        else:
            message=('You need to choose options for your item.' if key.startswith(('missing-','invalid-')) else
                     'Product that you are trying to add is not available.' if key.startswith('retired-') else 'Not enough items for sale')
            check(case['message']==message and case['exception'] in (None,'Magento\\Framework\\Exception\\LocalizedException'),'Wrong rejection cause: '+key)
            check(case['items']==[],'Rejected case retained accepted items')
    paths['verifier']=Path(__file__).resolve();args.output_dir.mkdir(parents=True)
    write_json(args.output_dir/'result.json',{'versions':VERSIONS,'database':evidence['database'],'cases':21,'accepted':12,'rejected':9,
        'exact_child_identity_and_price_verified':True,'database_unchanged':True,'quotes_saved':0,'orders_created':0,'reservations_created':0,
        'configuration':evidence['configuration'],'storefront_verified':False,'checkout_verified':False,'live_writes':False,'publication_approved':False,
        'inputs':{str(path):sha256(path) for path in paths.values()}})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('evidence','pricing','candidates','plan','output-dir'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'),level=logging.INFO)
    try:verify(args);logging.info('All 21 unsaved guest-cart cases verified')
    except Exception:logging.exception('Cart verification failed');raise SystemExit(1)
