"""Maintain a separate current catalog export with hash-bound SKU exclusions."""
from collections import Counter
import csv
import fcntl
import hashlib
import json
from pathlib import Path
import re
import time


FRANCHISE = re.compile(r'star[\s_-]*wars|\bdarth\b|\byoda\b|storm[\s-]*trooper|\bchewbacca\b|\bmandalorian\b|\bgrogu\b|\br2[\s-]*d2\b|\bc[\s-]*3po\b|\bbb[\s-]*8\b|\bkylo\s+ren\b|\bboba\s+fett\b|\bskywalker\b|\bprincess\s+leia\b|\bhan\s+solo\b|\blightsaber\b|\bmillennium\s+falcon\b|\bobi[\s-]*wan\b|\bjedi\b|\bsith\b', re.I)
LIST_FIELDS = ('related_skus', 'crosssell_skus', 'upsell_skus')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temp.replace(path)


def discover(data):
    matches = {}
    for path in sorted(Path(data).glob('*.csv')):
        with path.open(newline='') as stream:
            for row in csv.DictReader(stream):
                if row.get('product_type') and any(FRANCHISE.search(v or '') for v in row.values()):
                    matches[row['sku']] = {'sku': row['sku'], 'name': row['name'], 'product_type': row['product_type']}
    return sorted(matches.values(), key=lambda x: x['sku'])


def prune_bundle(value, excluded):
    entries = [dict(field.split('=', 1) for field in part.split(',')) for part in value.split('|')]
    kept = [entry for entry in entries if entry['sku'] not in excluded]
    names = {entry['name'] for entry in entries}
    if names != {entry['name'] for entry in kept}:
        raise ValueError('Bundle option would have no retained products')
    for name in names:
        options = [entry for entry in kept if entry['name'] == name]
        if not any(entry.get('default') == '1' for entry in options):
            options[0]['default'] = '1'
    return '|'.join(','.join(k + '=' + v for k, v in entry.items()) for entry in kept), len(entries) - len(kept)


def rename_text(value, rules):
    for rule in rules:
        def replacement(match):
            old = match.group()
            return rule['to'].upper() if old.isupper() else rule['to'].lower() if old.islower() else rule['to']
        value = re.sub(re.escape(rule['from']), replacement, value, flags=re.I)
    return value


def refresh(job, audit, latest):
    job, audit = Path(job), Path(audit)
    config_path = job / 'catalog-exclusions.json'
    if not config_path.exists() or not latest:
        return None
    with (job / 'catalog-exclusions.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        config = json.loads(config_path.read_text())
        policy_path = Path(config['policy'])
        if sha(policy_path) != config['policy_sha256']:
            raise ValueError('Catalog exclusion approval changed')
        policy = json.loads(policy_path.read_text())
        text_sha = config.get('text_policy_sha256')
        rules = []
        if text_sha:
            if sha(config['text_policy']) != text_sha:
                raise ValueError('Catalog text replacement approval changed')
            rules = json.loads(Path(config['text_policy']).read_text())['replacements']
            if any(not r['from'] or not r['to'] for r in rules):
                raise ValueError('Empty text replacement')
        text_pattern = re.compile('|'.join(re.escape(r['from']) for r in rules), re.I) if rules else None
        excluded = {x['sku'] for x in policy['products']}
        if not excluded or len(excluded) != len(policy['products']):
            raise ValueError('Empty or duplicate exclusion scope')
        verification = Path(latest['verification'])
        if sha(verification) != latest['verification_sha256']:
            raise ValueError('Selected image export changed')
        current_path = job / 'local-catalog.json'
        current = json.loads(current_path.read_text()) if current_path.exists() else {}
        if (current.get('selection_verification_sha256') == latest['verification_sha256'] and
                current.get('exclusions_sha256') == config['policy_sha256'] and current.get('text_policy_sha256') == text_sha):
            for name, change in current['changes'].items():
                if sha(Path(current['data']) / name) != change['output_sha256']:
                    raise ValueError('Current catalog export changed: ' + name)
            return current
        source = Path(config['source_data'])
        for name, expected in config['source_hashes'].items():
            if sha(source / name) != expected:
                raise ValueError('Catalog baseline changed: ' + name)
        destination = verification.parent / ('catalog-data-' + text_sha[:12] if text_sha else 'catalog-data')
        destination.mkdir(exist_ok=True)
        expected_media = json.loads(verification.read_text())['media_csv_sha256']
        if sha(latest['media_csv']) != expected_media:
            raise ValueError('Selected media CSV changed')
        changes = {}; products = {}; kept_skus = set();removed_products = set();text_total = 0
        for path in sorted(source.glob('*.csv')):
            input_path = Path(latest['media_csv']) if path.name == '4-media.csv' else path
            removed = [];pruned = 0;rows = 0;before = sha(input_path);text_count = 0;renamed_rows = 0
            with input_path.open(newline='') as stream, (destination / path.name).open('w', newline='') as output:
                reader = csv.DictReader(stream);writer = csv.DictWriter(output, fieldnames=reader.fieldnames);writer.writeheader()
                for row in reader:
                    if row['sku'] in excluded:
                        removed.append(row)
                        if row.get('product_type'):
                            removed_products.add(row['sku'])
                        continue
                    for field in LIST_FIELDS:
                        if row.get(field):
                            prior = row[field].split(',')
                            row[field] = ','.join(s for s in prior if s.strip() not in excluded)
                            pruned += len(prior) - len(row[field].split(',')) if row[field] else len(prior)
                    if row.get('bundle_values') and set(re.findall(r'WANDS-[A-Z0-9-]+', row['bundle_values'])) & excluded:
                        row['bundle_values'], removed_options = prune_bundle(row['bundle_values'], excluded)
                        pruned += removed_options
                    combined = '\n'.join(v or '' for v in row.values())
                    if text_pattern and text_pattern.search(combined):
                        text_count += len(text_pattern.findall(combined));renamed_rows += 1
                        row = {k: rename_text(v or '', rules) for k, v in row.items()}
                    if any(set(re.findall(r'WANDS-[A-Z0-9-]+', value or '')) & excluded for value in row.values()):
                        raise ValueError('Unresolved catalog relationship: ' + row['sku'])
                    if any(FRANCHISE.search(value or '') for value in row.values()):
                        raise ValueError('Franchise reference remains: ' + row['sku'])
                    writer.writerow(row);rows += 1
                    if row.get('product_type'):
                        if row['sku'] in kept_skus:
                            raise ValueError('Duplicate catalog product')
                        kept_skus.add(row['sku']);products[row['sku']] = row['product_type']
            if sha(input_path) != before:
                raise ValueError('Input changed during catalog projection')
            backup = destination.parent / ('excluded-rows-' + path.stem + '.jsonl')
            backup.write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in removed))
            changes[path.name] = {'kept_rows': rows, 'removed_rows': len(removed), 'pruned_links': pruned,
                                  'source_sha256': before, 'output_sha256': sha(destination / path.name),
                                  'text_replacements': text_count, 'renamed_rows': renamed_rows}
            text_total += text_count
        if removed_products != excluded:
            raise ValueError('Exclusions do not match baseline product inventory')
        for path in source.glob('attribute-options.json'):
            content = path.read_text()
            if text_pattern:
                text_total += len(text_pattern.findall(content));content = rename_text(content, rules)
            (destination / path.name).write_text(content)
        # Re-read the actual output, checking product references and media files.
        media_assignments = media_roles = 0;urls = {}
        for path in destination.glob('*.csv'):
            with path.open(newline='') as stream:
                for row in csv.DictReader(stream):
                    assigned = False
                    if row['sku'] not in kept_skus:
                        raise ValueError('Orphan catalog assignment')
                    if text_pattern and text_pattern.search('\n'.join(v or '' for v in row.values())):
                        raise ValueError('Unreplaced catalog text')
                    if row.get('product_type') and row.get('url_key'):
                        key = (row.get('store_view_code', ''), row['url_key'])
                        if key in urls and urls[key] != row['sku']:
                            raise ValueError('Duplicate catalog URL after replacement')
                        urls[key] = row['sku']
                    for field in LIST_FIELDS:
                        if any(s.strip() not in kept_skus for s in row.get(field, '').split(',') if s.strip()):
                            raise ValueError('Orphan merchandising link')
                    for field in ('base_image', 'small_image', 'thumbnail', 'thumbnail_image'):
                        if row.get(field):
                            assigned = True;media_roles += 1
                            value = row[field].lstrip('/')
                            media_path = Path(latest['media']).parent / value
                            qa_path = Path(config['qa_media']) / value
                            if not media_path.is_file() and not qa_path.is_file():
                                raise ValueError('Missing catalog media: ' + value)
                    media_assignments += assigned
        counts = {'products': len(products), 'product_types': dict(Counter(products.values())),
                  'excluded_products': len(excluded), 'media_assignments': media_assignments,
                  'media_roles': media_roles, 'expanded_media_assignments': changes['4-media.csv']['kept_rows']}
        write(destination / 'counts.json', counts)
        current = {'state': 'verified', 'updated_at': time.time(), 'data': str(destination), 'counts': counts,
                   'media': latest['media'], 'qa_media': config['qa_media'], 'changes': changes,
                   'selection_verification_sha256': latest['verification_sha256'],
                   'text_policy_sha256': text_sha, 'text_replacements': text_total,
                   'exclusions_sha256': config['policy_sha256'], 'exclusions': str(policy_path),
                   'source_data_intact': True, 'original_images_intact': True, 'deployed': False,
                   'verification': str(destination.parent / 'catalog-exclusions-verification.json')}
        write(Path(current['verification']), current)
        write(current_path, current)
        return current
