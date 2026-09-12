#!/usr/bin/env python3
"""Compare every scoped live product, option and relationship with the bulk packet."""
import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import subprocess


class ContainerPath:
    """Read a snapshot in place on its server, without copying product records."""
    def __init__(self, container, path):
        self.container, self.path = container, str(path)
    def __truediv__(self, name):
        return ContainerPath(self.container, self.path+'/'+name)
    def read_bytes(self):
        return subprocess.check_output(['docker','exec',self.container,'cat',self.path])
    def read_text(self):
        return self.read_bytes().decode()


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(snapshot, packet, imports, before=None):
    manifest = json.loads((snapshot/'manifest.json').read_text())
    assert not manifest['missing_skus']
    for table, meta in manifest['tables'].items():
        assert sha256(snapshot/(table+'.jsonl')) == meta['sha256']
    entities = {r['sku']: r for r in read_jsonl(snapshot/'catalog_product_entity.jsonl')}
    attrs = {r['attribute_code']: r for r in read_jsonl(snapshot/'eav_attribute.jsonl')}
    values = {}
    for kind in ('varchar','text','decimal','int','datetime'):
        values.update({(str(r['entity_id']),str(r['attribute_id']),str(r['store_id'])): r['value']
                       for r in read_jsonl(snapshot/('catalog_product_entity_'+kind+'.jsonl'))})
    option_labels = {str(r['option_id']): r['value'] for r in read_jsonl(snapshot/'eav_attribute_option_value.jsonl') if str(r['store_id']) == '0'}
    errors, checks, stock_updates = [], 0, {}
    for filename in ('simple-updates.csv','parent-content-only.csv','disable-children.csv'):
        for row in csv.DictReader((imports/filename).open()):
            entity = entities[row['sku']]
            stock_updates[row['sku']] = {k:v for k,v in row.items() if k in {'qty','is_in_stock','manage_stock'} and v!=''}
            for code, expected in row.items():
                if not expected or code in {'sku','store_view_code','configurable_variations','configurable_variation_labels'}:
                    continue
                if code == 'product_type':
                    actual = entity['type_id']
                else:
                    code = {'product_online':'status'}.get(code,code)
                    if code not in attrs:
                        continue
                    attr = attrs[code]
                    actual = values.get((str(entity['entity_id']),str(attr['attribute_id']),'0'))
                    if expected == '__EMPTY__VALUE__':
                        expected = None
                    elif attr['frontend_input'] == 'boolean':
                        expected = '1' if expected.lower() in {'yes','1'} else '0'
                        actual = str(actual)
                    elif code.startswith('wands_') and attr['frontend_input'] == 'select':
                        actual = option_labels.get(str(actual))
                    elif attr['backend_type'] in {'decimal','int'} and actual is not None:
                        try:
                            actual, expected = Decimal(str(actual)), Decimal(expected)
                        except InvalidOperation:
                            actual = option_labels.get(str(actual), actual)
                checks += 1
                if actual != expected:
                    errors.append({'sku':row['sku'],'field':code,'expected':str(expected),'actual':str(actual)})
    products = read_jsonl(packet/'products.jsonl')
    expected_links = {(str(entities[r['parent_sku']]['entity_id']),str(entities[r['sku']]['entity_id'])) for r in products if r.get('parent_sku')}
    actual_links = {(str(r['parent_id']),str(r['product_id'])) for r in read_jsonl(snapshot/'catalog_product_super_link.jsonl')}
    if actual_links != expected_links:
        errors.append({'relationship_difference':len(actual_links ^ expected_links)})
    expected_axes = {(str(entities[r['sku']]['entity_id']),str(attrs[code]['attribute_id'])) for r in products if r['kind']=='configurable' for code in r['axis_codes']}
    actual_axes = {(str(r['product_id']),str(r['attribute_id'])) for r in read_jsonl(snapshot/'catalog_product_super_attribute.jsonl')}
    if actual_axes != expected_axes:
        errors.append({'axis_difference':len(actual_axes ^ expected_axes)})
    inventory_checks = 0
    if before:
        for table, key, fields in [('cataloginventory_stock_item','product_id',['qty','is_in_stock','manage_stock']),
                                   ('inventory_source_item','sku',['quantity','status'])]:
            old = {str(r[key]):r for r in read_jsonl(before/(table+'.jsonl'))}
            for row in read_jsonl(snapshot/(table+'.jsonl')):
                identity = str(row[key])
                sku = identity if key=='sku' else next(k for k,v in entities.items() if str(v['entity_id'])==identity)
                for field in fields:
                    inventory_checks += 1
                    source_field = {'quantity':'qty','status':'is_in_stock'}.get(field,field)
                    expected = stock_updates.get(sku,{}).get(source_field,old[identity][field])
                    if str(expected).lower() in {'yes','no'}:
                        expected = '1' if str(expected).lower()=='yes' else '0'
                    if Decimal(str(expected)) != Decimal(str(row[field])):
                        errors.append({'sku':sku,'field':table+'.'+field,'expected':str(expected),'actual':str(row[field])})
    return {'captured_at':manifest['captured_at'],'products':len(entities),'field_checks':checks,
            'inventory_preservation_checks':inventory_checks,
            'configurable_links':len(actual_links),'configurable_axes':len(actual_axes),'errors':errors,'passed':not errors}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot','packet','imports','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--snapshot-container')
    parser.add_argument('--before',type=Path)
    args=parser.parse_args()
    snapshot = ContainerPath(args.snapshot_container,args.snapshot) if args.snapshot_container else args.snapshot
    before = ContainerPath(args.snapshot_container,args.before) if args.before and args.snapshot_container else args.before
    result=verify(snapshot,args.packet,args.imports,before)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    raise SystemExit(0 if result['passed'] else 1)
