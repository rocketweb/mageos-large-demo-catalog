"""Canonical category paths for fresh catalog release inputs."""
import csv
import json
from pathlib import Path
import re
import shutil

DEPARTMENTS = ('DIY', 'Furniture', 'Decor', 'Bed & Bath', 'Kitchen', 'Outdoor', 'Storage', 'Kids', 'Pets')
RENAMES = {'Kitchen & Tabletop': 'Kitchen', 'Décor & Pillows': 'Decor',
           'Storage & Organization': 'Storage', 'Baby & Kids': 'Kids', 'Pet': 'Pets',
           'Home Improvement': 'DIY'}
CHILD_DEPARTMENTS = {'Lighting': 'Decor', 'Rugs': 'Decor'}
SKU_FIELDS = {'sku', 'configurable_variations', 'associated_skus', 'related_skus', 'upsell_skus', 'crosssell_skus'}


def canonical_row(row):
    result = dict(row)
    if 'categories' in result:
        result['categories'] = canonical_categories(result['categories'])
    for name in SKU_FIELDS & result.keys():
        result[name] = re.sub(r'(WANDS-SYN-[SCP]-)HOME-IMPROVEMENT-', r'\1DIY-', result[name])
    if 'url_key' in result:
        result['url_key'] = re.sub(r'(wands-syn-[scp]-)home-improvement-', r'\1diy-', result['url_key'])
    return result


def canonical_value(value):
    if isinstance(value, dict):
        return {canonical_value(key): canonical_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonical_value(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r'(WANDS-SYN-[SCP]-)HOME-IMPROVEMENT-', r'\1DIY-', value)
        value = re.sub(r'(wands-syn-[scp]-)home-improvement-', r'\1diy-', value)
        if value.startswith('WANDS Catalog/'):
            value = canonical_categories(value)
        return 'DIY' if value == 'Home Improvement' else value
    return value


def canonical_json(source, destination):
    destination = Path(destination)
    if destination.exists() or Path(source).resolve() == destination.resolve():
        raise ValueError('Canonical catalog output must be a fresh file')
    destination.parent.mkdir(parents=True, exist_ok=True)
    value = canonical_value(json.loads(Path(source).read_bytes()))
    with destination.open('x') as output:
        json.dump(value, output, sort_keys=True, separators=(',', ':'))
        output.write('\n')


def canonical_categories(value):
    paths = re.split(r',(?=WANDS Catalog/)', value)
    result = []
    for path in paths:
        parts = path.split('/', 2)
        if len(parts) > 1 and parts[0].casefold() == 'wands catalog':
            name = parts[1]
            for old, new in RENAMES.items():
                if name.casefold() == old.casefold():
                    parts[1] = new
                    break
            for child, parent in CHILD_DEPARTMENTS.items():
                if name.casefold() == child.casefold():
                    parts[1] = parent + '/' + child
                    break
        result.append('/'.join(parts))
    return ','.join(result)


def canonical_csv(source, destination):
    """Normalize taxonomy, generated identities and their references; preserve source inputs."""
    source, destination = Path(source), Path(destination)
    if destination.exists() or source.resolve() == destination.resolve():
        raise ValueError('Canonical catalog output must be a fresh file')
    destination.parent.mkdir(parents=True, exist_ok=True)
    changed = 0
    with source.open(newline='') as stream:
        reader = csv.DictReader(stream)
        if not ({'categories', 'url_key'} | SKU_FIELDS) & set(reader.fieldnames or []):
            shutil.copyfile(source, destination)
            return 0
        with destination.open('x', newline='') as output:
            writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                canonical = canonical_row(row)
                changed += canonical != row
                writer.writerow(canonical)
    return changed
