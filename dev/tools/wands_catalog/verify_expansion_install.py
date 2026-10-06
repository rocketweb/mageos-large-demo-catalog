#!/usr/bin/env python3
"""Verify catalog identity, relationships and protected data from read-only snapshots.

This is database acceptance only; media hashes and storefront acceptance are separate.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from build_expanded_catalog import csv_rows, variations
from bulk_expansion_images import atomic_json
from prepare_catalog import sha256


def compare(before, after, desired, expected_links):
    if before['schema'] != 2 or after['schema'] != 2:
        raise ValueError('Current stock-aware snapshots are required')
    if any(before[k] != after[k] for k in ('root', 'website_id', 'store_id')):
        raise ValueError('Snapshots refer to different installations')
    old = before['products']
    actual = after['products']
    target = {sku: row for sku, row in actual.items() if row['wands']}
    unrelated_before = {sku: row for sku, row in old.items() if not row['wands']}
    unrelated_after = {sku: row for sku, row in actual.items() if not row['wands']}
    old_ids = {row['id'] for row in old.values() if row['wands']}
    old_skus = {sku for sku, row in old.items() if row['wands']}
    changed_stock = {}
    for table, key, owner in (
        ('cataloginventory_stock_item', 'item_id', 'product_id'),
        ('inventory_source_item', 'source_item_id', 'sku'),
    ):
        prior = {str(row[key]): row for row in before['existing_wands_stock'][table]}
        current = {str(row[key]): row for row in after['existing_wands_stock'][table]
                   if (row[owner] in old_skus if owner == 'sku' else int(row[owner]) in old_ids)}
        changed_stock[table] = sum(prior.get(k) != current.get(k) for k in prior.keys() | current.keys())
    protected = before['protected']
    changed_tables = sorted(k for k in protected.keys() | after['protected'].keys()
                            if protected.get(k) != after['protected'].get(k))
    links = [(row['parent'], row['child']) for row in after['configurable_links'] if row['parent'] in desired]
    other_links_before = sorted((r['parent'], r['child']) for r in before['configurable_links'] if r['parent'] not in desired)
    other_links_after = sorted((r['parent'], r['child']) for r in after['configurable_links'] if r['parent'] not in desired)
    errors = {
        'missing_products': len(desired.keys() - target.keys()),
        'unexpected_wands_products': len(target.keys() - desired.keys()),
        'incorrect_product_types': sum(target[sku]['type'] != desired[sku]['product_type'] for sku in target.keys() & desired.keys()),
        'incorrect_product_websites': sum(row['websites'] != [after['website_id']] for row in target.values()),
        'changed_existing_product_ids': sum(sku not in actual or actual[sku]['id'] != row['id'] for sku, row in old.items()),
        'unrelated_product_changes': sum(unrelated_before.get(k) != unrelated_after.get(k)
                                         for k in unrelated_before.keys() | unrelated_after.keys()),
        'shared_wands_products': len(after['shared_wands_skus']),
        'missing_links': len(expected_links - set(links)),
        'unexpected_links': len(set(links) - expected_links),
        'duplicate_links': len(links) - len(set(links)),
        'unrelated_links_changed': other_links_before != other_links_after,
        'changed_protected_tables': changed_tables,
        'changed_existing_stock_rows': changed_stock,
    }
    passed = not any(value for key, value in errors.items() if key != 'changed_existing_stock_rows') and not any(changed_stock.values())
    return {'passed': passed, 'scope': 'database identity, membership, types, relationships and protected data only',
            'wands_products': len(target), 'total_products': len(actual),
            'product_types': dict(Counter(row['type'] for row in target.values())), **errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'before', 'after', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.candidate / 'manifest.json').read_text())
    for name, pin in manifest['outputs'].items():
        if sha256(args.candidate / name) != pin:
            raise ValueError('Frozen candidate changed')
    desired = {row['sku']: row for name in ('1-simple.csv', '2-configurable.csv', '3-bundle.csv')
               for row in csv_rows(args.candidate / 'data' / name)}
    if len(desired) != 107688:
        raise ValueError('Unexpected candidate size')
    links = {(sku, group['sku']) for sku, row in desired.items() if row['product_type'] == 'configurable'
             for group in variations(row)}
    before, after = (json.loads(path.read_text()) for path in (args.before, args.after))
    if before['root'] not in {'/Users/matt/code/mageos-latest', '/var/www/html'}:
        raise ValueError('Unapproved installation')
    report = compare(before, after, desired, links)
    report.update(candidate_sha256=sha256(args.candidate / 'manifest.json'),
                  before_snapshot_sha256=sha256(args.before), after_snapshot_sha256=sha256(args.after))
    atomic_json(args.output, report)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
