#!/usr/bin/env python3
"""Verify the isolated pilot stock-index lifecycle and quantity boundaries."""
import argparse
import hashlib
import json
import logging
from pathlib import Path

from build_realism_review import write_json
from prepare_catalog import sha256
from verify_catalog_repairs import check
from verify_mageos_rehearsal import index, number, VERSIONS


def check_nursery_inventory(product):
    check(product['sku'] == 'WANDS-000056' and product['type'] == 'simple' and product['status'] == 1, 'Wrong nursery identity/type/status')
    check(not product['errors'], 'Inventory service raised an error')
    checks = product['checks']
    check(checks['model_is_salable'] is True and checks['inventory_is_salable'] is True, 'Nursery is not salable')
    number(checks['salable_quantity'], 47)
    for qty in (1, 47, 48):
        response = checks['requested_' + str(qty)]
        check(response['salable'] is (qty <= 47), 'Requested quantity boundary failed')
        if qty <= 47:
            check(response['error_codes'] == [], 'Valid quantity has errors')
        else:
            check('is_salable_with_reservations-not_enough_qty' in response['error_codes'], 'Overorder rejected for wrong reason')


def verify(args):
    check(not args.output_dir.exists(), 'Choose a fresh output directory')
    paths = {k: getattr(args, k).resolve() for k in ('before', 'stale', 'indexed', 'restored', 'receipt', 'plan')}
    data = {k: json.loads(p.read_text()) for k, p in paths.items()}
    before, stale, indexed, restored = (data[k] for k in ('before', 'stale', 'indexed', 'restored'))
    plan = data['plan']; expected = set(plan['approved_products'])
    check(len(expected) == 17 and len(plan['operations']) == 105, 'Wrong plan scope')
    probe = Path(__file__).with_name('probe_mageos_inventory.php')
    for phase in (before, stale, indexed, restored):
        check(phase['database'] == before['database'] and phase['database'].startswith('wands_rehearsal_'), 'Wrong database')
        check(phase['versions'] == VERSIONS and phase['website'] == 'wands' and phase['stock_id'] == 1, 'Wrong runtime/channel')
        check(phase['live_writes'] is False and phase['cart_verified'] is False and phase['storefront_verified'] is False, 'Wrong acceptance boundary')
        check(phase['probe_sha256'] == sha256(probe) and phase['plan_sha256'] == sha256(paths['plan']), 'Changed probe/plan')
        check(set(index(phase['products'])) == expected, 'Wrong inventory probe scope')
        check(not any(p['errors'] for p in phase['products']), 'Inventory service raised an error')
        check(set(phase['changed_tables']) <= ({'cataloginventory_stock_status'} if phase['reindexed'] else set()), 'Unexpected changed tables')
    check(before['reindexed'] is False and stale['reindexed'] is False and indexed['reindexed'] is True and restored['reindexed'] is True, 'Wrong lifecycle phases')
    number(index(stale['products'])['WANDS-000056']['checks']['salable_quantity'], 0)
    check_nursery_inventory(index(indexed['products'])['WANDS-000056'])
    retired = [p for p in indexed['products'] if p['sku'].startswith('WANDS-000056-')]
    check(len(retired) == 4 and all(p['status'] == 2 and p['checks']['model_is_salable'] is False and p['checks']['inventory_is_salable'] is False for p in retired), 'Retired child salability mismatch')
    check(before['products'] == restored['products'], 'Inventory service rollback parity failed')
    check(before['before_table_hashes'] == restored['after_table_hashes'], 'Complete database rollback parity failed')
    check(before['index_before'] == restored['index_after'], 'Stock index rollback parity failed')
    receipt = data['receipt']
    dsn = f"mysql:host=127.0.0.1;port=13380;dbname={before['database']};charset=utf8mb4"
    check(receipt['dsn_sha256'] == hashlib.sha256(dsn.encode()).hexdigest() and receipt['plan_sha256'] == sha256(paths['plan']) and len(receipt['operations']) == 105, 'Wrong receipt')
    for suffix in ('.committed', '.rolled-back'):
        paths[suffix] = Path(str(paths['receipt']) + suffix)
    check(json.loads(paths['.committed'].read_text())['receipt_sha256'] == sha256(paths['receipt']), 'Receipt hash mismatch')
    check(json.loads(paths['.rolled-back'].read_text())['verified_before_parity'] is True, 'Missing verified inverse')
    paths['probe'] = probe; paths['verifier'] = Path(__file__).resolve()
    args.output_dir.mkdir(parents=True)
    write_json(args.output_dir / 'result.json', {
        'versions': VERSIONS, 'database': before['database'], 'products_checked': 17,
        'nursery_salable_quantity_before_reindex': 0, 'nursery_salable_quantity_after_reindex': 47,
        'requested_quantities': {'1': True, '47': True, '48': False},
        'retired_children_not_salable': 4, 'whole_database_rollback_parity': True,
        'inventory_service_rollback_parity': True, 'native_partial_stock_reindex_verified': True,
        'configuration': indexed['configuration'], 'cart_verified': False,
        'storefront_verified': False, 'live_writes': False, 'publication_approved': False,
        'inputs': {str(path): sha256(path) for path in paths.values()}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before', 'stale', 'indexed', 'restored', 'receipt', 'plan', 'output-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'), level=logging.INFO)
    try:
        verify(args)
        logging.info('Local native stock-index lifecycle and inverse verified')
    except Exception:
        logging.exception('Inventory lifecycle verification failed')
        raise SystemExit(1)
