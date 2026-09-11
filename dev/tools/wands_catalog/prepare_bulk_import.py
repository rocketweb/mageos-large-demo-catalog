#!/usr/bin/env python3
"""Translate the verified correction packet into native Magento import batches."""
import argparse
import csv
from html import escape
import json
import logging
from pathlib import Path

from build_realism_review import write_json, write_jsonl
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from verify_catalog_repairs import check


def dimension_copy(record):
    design = record.get('dimension_design', {})
    labels = {'lab_spec_width_cm': 'Width', 'lab_spec_length_cm': 'Length', 'lab_spec_height_cm': 'Height', 'lab_spec_depth_cm': 'Depth'}
    def values(specs):
        return ', '.join(labels[code]+': '+str(fact['value'])+' cm' for code, fact in specs.items() if code in labels)
    parts = design.get('components', [])
    if parts:
        rows = [str(part['quantity'])+' × '+escape(part['label'])+': '+escape(values(part['specifications'])) for part in parts]
    else:
        value = values(record.get('specifications', {}))
        rows = [escape(value)] if value else []
    if not rows:
        return ''
    return '<h3>Illustrative dimensions</h3><ul>'+''.join('<li>'+row+'</li>' for row in rows)+'</ul><p>Dimensions are synthetic test-catalog specifications, not manufacturer measurements.</p>'


def native_row(record, children):
    row = dict(record['catalog_fields'])
    row.update(product_type=record['kind'], product_online='1', **record['variant_options'])
    row['description'] = row.get('description', '')+dimension_copy(record)
    if record['sku'] == 'WANDS-000056':
        row.update(qty='47', price='74.99', special_price='63.74', weight='1.75')
    if record['kind'] == 'configurable':
        family = sorted((c for c in children if c['parent_sku'] == record['sku']), key=lambda c: c['sku'])
        check(bool(family), 'Empty configurable family')
        row['configurable_variations'] = '|'.join(','.join(['sku='+c['sku']]+[code+'='+str(value) for code,value in c['variant_options'].items()]) for c in family)
        row['configurable_variation_labels'] = ','.join(a['attribute']+'='+a['label'] for a in record['axes'])
    return row


def write_csv(path, rows):
    columns = ['sku', 'store_view_code']+sorted(set().union(*(set(row) for row in rows))-{'sku','store_view_code'})
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def build(args):
    check(not args.output_dir.exists(), 'Choose fresh import directory')
    manifest = json.loads((args.packet/'manifest.json').read_text())
    for name, digest in manifest['outputs'].items():
        check(Path(name).name == name and sha256(args.packet/name) == digest, 'Bulk packet changed')
    records = read_jsonl(args.packet/'products.jsonl')
    retired = read_jsonl(args.packet/'retirements.jsonl')
    check(len(records) == 603 and len(retired) == 64, 'Wrong bulk scope')
    children = [r for r in records if r.get('parent_sku')]
    simple = [native_row(r, children) for r in records if r['kind'] == 'simple']
    parents = [native_row(r, children) for r in records if r['kind'] == 'configurable']
    disable = [{'sku': r['sku'], 'store_view_code': '', 'product_online': '2'} for r in retired]
    by_sku = {r['sku']: r for r in records}
    conversions = sorted({r['before']['parent_sku'] for r in retired
                          if by_sku.get(r['before']['parent_sku'], {}).get('kind') == 'simple'})
    check(len(conversions) == 5, 'Wrong configurable-to-simple conversion count')
    options = {}
    for record in records:
        for code, value in record['variant_options'].items():
            check(not any(c in str(value) for c in ('|', ',')), 'Unsupported variant CSV delimiter')
            options.setdefault(code, set()).add(value)
    structure = {'conversions': conversions, 'retired_skus': sorted(r['sku'] for r in retired),
                 'attribute_options': {k: sorted(v) for k,v in options.items()},
                 'parent_axes': {r['sku']: r['axis_codes'] for r in records if r['kind'] == 'configurable'},
                 'product_skus': sorted(by_sku), 'all_skus': sorted(set(by_sku)|{r['sku'] for r in retired})}
    args.output_dir.mkdir(parents=True)
    write_csv(args.output_dir/'simple-updates.csv', simple)
    write_csv(args.output_dir/'parent-updates.csv', parents)
    write_csv(args.output_dir/'disable-children.csv', disable)
    write_json(args.output_dir/'structure.json', structure)
    request = {'version': 1, 'expected_host': 'relevance.comtom.lab', 'skus': structure['all_skus'], 'bundle_skus': [],
               'attributes': sorted(set(options)|{'image','small_image','thumbnail','name','description','status','price','special_price','lab_sale_unit'}),
               'packet_sha256': sha256(args.packet/'manifest.json')}
    write_json(args.output_dir/'snapshot-request.json', request)
    write_json(args.output_dir/'summary.json', {'simple_updates': len(simple), 'parent_updates': len(parents),
               'disabled_children': len(disable), 'conversions': conversions, 'affected_skus': len(structure['all_skus']),
               'scope': 'Existing WANDS test catalog only; no customer/order changes', 'images_in_git': False})
    write_json(args.output_dir/'manifest.json', {'version': 'wands-bulk-native-import-v1',
        'inputs': {str((args.packet/'manifest.json').resolve()): sha256(args.packet/'manifest.json'), str(Path(__file__).resolve()): sha256(Path(__file__))},
        'outputs': {p.name: sha256(p) for p in args.output_dir.iterdir() if p.is_file()}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('packet', 'output-dir'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'), level=logging.INFO)
    try:
        build(args)
        logging.info('Native bulk import files prepared')
    except Exception:
        logging.exception('Bulk import preparation failed')
        raise SystemExit(1)
