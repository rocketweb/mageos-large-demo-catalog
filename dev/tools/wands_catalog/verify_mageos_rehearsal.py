#!/usr/bin/env python3
"""Verify isolated Mage-OS model evidence, without claiming storefront acceptance."""
import argparse
from decimal import Decimal
import hashlib
import json
import logging
from pathlib import Path

from build_realism_review import write_json
from prepare_catalog import sha256
from verify_catalog_repairs import check

FIELDS = ('name', 'description', 'short_description', 'meta_title', 'meta_description', 'lab_sale_unit')
ROOTS = {'WANDS-000056', 'WANDS-003897', 'WANDS-017842', 'WANDS-030335', 'WANDS-035295'}
VERSIONS = {'mage-os/product-community-edition': '3.5.0', 'hyva-themes/magento2-default-theme': '1.5.2'}


def index(rows):
    result = {row['sku']: row for row in rows}
    check(len(result) == len(rows), 'Duplicate product evidence')
    return result


def number(value, expected):
    check(value is not None and Decimal(str(value)) == Decimal(str(expected)), 'Unexpected numeric value')


def check_nursery(data):
    nursery = index(data['products'])['WANDS-000056']
    check(nursery['type'] == 'simple' and nursery['children'] == [], 'Nursery is not a standalone simple product')
    for key, expected in {'price': '74.99', 'special_price': '63.74', 'nursery_final_price': '63.74', 'weight': '1.75'}.items():
        number(nursery[key], expected)
    check(len(data['nursery_stock']) == 1 and len(data['nursery_sources']) == 1, 'Unexpected stock coverage')
    stock = data['nursery_stock'][0]
    for key, expected in {'qty': 47, 'manage_stock': 1, 'use_config_manage_stock': 0, 'is_in_stock': 1}.items():
        number(stock[key], expected)
    source = data['nursery_sources'][0]
    check(source['source_code'] == 'default', 'Wrong source')
    number(source['quantity'], 47)
    number(source['status'], 1)


def verify_models(before, after, restored, candidates):
    for data in (before, after, restored):
        check(data['magento_models_loaded'] is True and data['live_writes'] is False, 'Wrong evidence boundary')
        check(data['storefront_verified'] is False and data['salability_verified'] is False, 'Unsupported acceptance claim')
        check(data['versions'] == VERSIONS, 'Wrong installed runtime')
        check(set(index(data['products'])) == ROOTS, 'Wrong root coverage')
        check(data['database'] == before['database'] and data['database'].startswith('wands_rehearsal_'), 'Database mismatch')
        check(data['probe_sha256'] == before['probe_sha256'], 'Mixed probe revisions')
    for key in ('products', 'retained_children', 'nursery_stock', 'nursery_sources'):
        check(restored[key] == before[key], 'Rollback model mismatch: ' + key)
    roots = index(after['products'])
    active = index(after['products'] + [c for root in after['products'] for c in root['children']])
    expected = index(candidates['active'])
    check(len(active) == 13 and set(active) == set(expected), 'Active SKU coverage mismatch')
    for sku, candidate in expected.items():
        actual = active[sku]
        check(actual['type'] == candidate['kind'], 'Product type mismatch: ' + sku)
        check(actual['catalog_fields'] == {k: candidate['catalog_fields'][k] for k in FIELDS}, 'Copy mismatch: ' + sku)
        check(actual['name'] == candidate['catalog_fields']['name'] and actual['sale_unit'] == candidate['catalog_fields']['lab_sale_unit'], 'Product accessor mismatch')
        if candidate.get('parent_sku'):
            check(sku in index(roots[candidate['parent_sku']]['children']), 'Wrong parent relationship')
            number(actual['status'], 1)
            for attribute, value in candidate['variant_options'].items():
                check(actual[{'wands_piece_count': 'piece_count', 'wands_finish': 'finish'}[attribute]] == value, 'Option mismatch: ' + sku)
        else:
            check(roots[sku]['option_labels'] == [axis['label'] for axis in candidate['axes']], 'Option caption mismatch')
    check_nursery(after)
    retired_before = index(before['retained_children'])
    retired_after = index(after['retained_children'])
    check(len(retired_before) == 4 and set(retired_before) == set(retired_after) == set(index(candidates['retired'])), 'Retirement scope mismatch')
    for sku, old in retired_before.items():
        check(old['entity_id'] == retired_after[sku]['entity_id'], 'Retired identity changed')
        number(old['status'], 1)
        number(retired_after[sku]['status'], 2)
    check(index(before['products'])['WANDS-000056']['type'] == 'configurable', 'Wrong nursery baseline')
    check(set(index(index(before['products'])['WANDS-000056']['children'])) == set(retired_before), 'Wrong original nursery children')
    return {'active_products': 13, 'copy_fields_verified': 78, 'retained_disabled_children': 4,
            'model_rollback_parity': True, 'nursery_price_and_stock_verified': True,
            'configurable_options_verified': True}


def build(args):
    check(not args.output_dir.exists(), 'Choose a fresh verification directory')
    paths = {key: getattr(args, key).resolve() for key in ('before', 'after', 'restored', 'candidates', 'receipt', 'plan', 'database_result')}
    data = {key: json.loads(path.read_text()) for key, path in paths.items()}
    checks = verify_models(data['before'], data['after'], data['restored'], data['candidates'])
    receipt = data['receipt']
    check(receipt['plan_sha256'] == sha256(paths['plan']) and len(receipt['operations']) == 105, 'Wrong migration receipt')
    db = data['after']['database']
    dsn = f'mysql:host=127.0.0.1;port=13380;dbname={db};charset=utf8mb4'
    check(receipt['dsn_sha256'] == hashlib.sha256(dsn.encode()).hexdigest(), 'Wrong receipt database')
    for suffix in ('.committed', '.rolled-back'):
        paths[suffix] = Path(str(paths['receipt']) + suffix)
    committed = json.loads(paths['.committed'].read_text())
    check(committed['receipt_sha256'] == sha256(paths['receipt']) and committed['operations'] == 105, 'Invalid commit marker')
    check(json.loads(paths['.rolled-back'].read_text())['verified_before_parity'] is True, 'Rollback not verified')
    db_result = data['database_result']
    check(db_result['database'] == db and db_result['count'] == 10 and db_result['live_writes'] is False, 'Database test mismatch')
    check(db_result['plan_sha256'] == sha256(paths['plan']) and db_result['before_table_hashes'] == db_result['restored_table_hashes'], 'Database rollback evidence mismatch')
    probe = Path(__file__).with_name('probe_mageos_definitions.php')
    check(data['after']['probe_sha256'] == sha256(probe), 'Probe code changed after evidence collection')
    paths['probe'] = probe
    paths['verifier'] = Path(__file__).resolve()
    args.output_dir.mkdir(parents=True)
    write_json(args.output_dir / 'result.json', {'checks': checks, 'versions': VERSIONS,
        'inputs': {str(path): sha256(path) for path in paths.values()},
        'database': db, 'operation_count': 105, 'storefront_verified': False,
        'salability_verified': False, 'live_writes': False, 'publication_approved': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before', 'after', 'restored', 'candidates', 'receipt', 'plan', 'database-result', 'output-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'), level=logging.INFO)
    try:
        build(args)
        logging.info('Isolated model evidence verified; storefront acceptance remains open')
    except Exception:
        logging.exception('Model verification failed')
        raise SystemExit(1)
