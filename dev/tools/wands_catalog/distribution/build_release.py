"""Build private Mage-OS Lab distribution candidates from explicit local inputs."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import logging
import math
from pathlib import Path
import subprocess

from release import closure, dependencies, digest, safe_path, write_archive, verify_release

HERE = Path(__file__).resolve().parent
REVISION = '3b74dcf4ba29ab8ff3e6a50b5b09fc627cb882b5'
BASE_SHA256 = 'f5a2664c20745230207e139c003a596d35e0f5d5573f67a8ecb36e6f528b6d26'
STARTER = ['WANDS-000056', 'WANDS-003817', 'WANDS-030335', 'WANDS-035295', 'WANDS-BUNDLE-001']


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode()


def csv_bytes(rows):
    stream = io.StringIO(newline='')
    columns = ['sku'] + sorted(set().union(*(set(row) for row in rows)) - {'sku'})
    writer = csv.DictWriter(stream, columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def read_csv(path):
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    if len({row['sku'] for row in rows}) != len(rows):
        raise ValueError(f'Duplicate SKU in {path.name}')
    return rows


def assemble(base, families, realism, corrections):
    rows = {row['sku']: row for row in read_csv(base)}
    layers = [families / 'configurable-parents.csv', families / 'configurable-children.csv',
              realism / 'bundles.csv', realism / 'products.patch.csv',
              corrections / 'simple-updates.csv', corrections / 'parent-updates.csv',
              corrections / 'disable-children.csv']
    for index, path in enumerate(layers):
        for row in read_csv(path):
            if index >= 3 and row['sku'] not in rows:
                raise ValueError(f'Unknown correction SKU: {row["sku"]}')
            rows.setdefault(row['sku'], {}).update(row)
    for sku, row in rows.items():
        row.update({key: '' for key, value in row.items() if value == '__EMPTY__VALUE__'})
        if row['product_type'] != 'configurable':
            row.pop('configurable_variations', None)
            row.pop('configurable_variation_labels', None)
        if row['visibility'] == 'Not Visible Individually':
            row['wands_average_rating'] = ''
            row['wands_review_count'] = ''
        row['store_view_code'] = ''
        if not row.get('url_key') or row['product_type'] not in ('simple', 'configurable', 'bundle'):
            raise ValueError(f'Incomplete product: {sku}')
        price = float(row.get('price') or 0)
        special = float(row.get('special_price') or 0)
        if not math.isfinite(price) or price < 0 or (row['product_type'] == 'simple' and price == 0):
            raise ValueError(f'Invalid price: {sku}')
        if row.get('special_price') and (not math.isfinite(special) or not 0 < special < price):
            raise ValueError(f'Invalid special price: {sku}')
        if not math.isfinite(float(row.get('qty') or 0)):
            raise ValueError(f'Invalid inventory quantity: {sku}')
        if any(value in json.dumps(row) for value in ('/Users/', 'relevance.comtom.lab', 'gophersport-com/')):
            raise ValueError(f'Private environment reference: {sku}')
        for child in dependencies(row):
            if child not in rows or rows[child]['product_type'] != 'simple':
                raise ValueError(f'Invalid dependency: {sku} -> {child}')
        if row['product_type'] == 'configurable':
            for variation in row['configurable_variations'].split('|'):
                values = dict(field.split('=', 1) for field in variation.split(','))
                child = rows[values.pop('sku')]
                for code, value in values.items():
                    if child.get(code) != value:
                        raise ValueError(f'Variant option mismatch: {sku}, {code}, {value}')
    urls = [row['url_key'] for row in rows.values()]
    if len(urls) != len(set(urls)):
        raise ValueError('Duplicate product URL keys')
    return rows, [base] + layers


def image_sources(args, rows):
    assignments = {}
    for prompt_file, origin in [(args.base_prompts, 'legacy-generated-product'),
                                (args.families / 'image-prompts.jsonl', 'legacy-generated-variant-or-bundle')]:
        with prompt_file.open() as stream:
            for line in stream:
                job = json.loads(line)
                safe_path(job['output_file'])
                source = args.media / job['output_file']
                if not source.is_file():
                    continue
                for sku in job.get('skus', [job['sku']]):
                    if sku in rows:
                        assignments[sku] = (source, origin)
    parent_of = {child: sku for sku, row in rows.items() if row['product_type'] == 'configurable'
                 for child in dependencies(row)}
    for sku in sorted(rows):
        if sku not in assignments and sku in parent_of and parent_of[sku] in assignments:
            assignments[sku] = (assignments[parent_of[sku]][0], 'inherited-family-illustration')
    media_manifest = json.loads((args.corrected_media / 'manifest.json').read_text())
    for sku, image_sku in media_manifest['assignments'].items():
        item = media_manifest['images'][image_sku]
        safe_path(item['file'])
        source = args.corrected_media / 'media' / item['file']
        if digest(source) != item['sha256']:
            raise ValueError(f'Corrected image checksum mismatch: {sku}')
        if sku in rows:
            assignments[sku] = (source, 'bulk-corrected-synthetic-illustration')
    return assignments


def build(args):
    from PIL import Image

    if args.output.exists():
        raise ValueError('Output must be a new release directory')
    if digest(args.base) != BASE_SHA256:
        raise ValueError('Prepared base is not the pinned WANDS input for this recipe')
    rows, inputs = assemble(args.base, args.families, args.realism, args.corrections)
    logging.info('Assembled %d rows: %s', len(rows), dict(Counter(r['product_type'] for r in rows.values())))
    assignments = image_sources(args, rows)
    selected = closure(rows, STARTER if args.profile == 'starter' else rows)
    chosen = [dict(rows[sku]) for sku in sorted(selected)]
    images, image_info, media_rows, coverage, media_lineage, missing_skus = {}, {}, [], Counter(), {}, []
    for row in chosen:
        sku = row['sku']
        if sku not in assignments:
            coverage['missing'] += 1
            missing_skus.append(sku)
            if row.get('product_online') == '1':
                raise ValueError(f'Active product has no illustration: {sku}')
            continue
        source, origin = assignments[sku]
        name = 'media/wands-lab/' + source.name
        if name in images and images[name] != source:
            raise ValueError(f'Conflicting image name: {name}')
        if name not in images:
            images[name] = source
            with Image.open(source) as image:
                if image.format != 'JPEG' or min(image.size) < 64:
                    raise ValueError(f'Invalid catalog JPEG: {name}')
                width, height = image.size
                image.verify()
            image_info[name] = {'sha256': digest(source), 'bytes': source.stat().st_size,
                                'width': width, 'height': height,
                                'acceptance': 'synthetic lab illustration; exact geometry not certified',
                                'model_revision': 'not fully recorded', 'license': 'CC0-1.0',
                                'license_scope': 'rights held by Rocket Web; third-party rights not waived'}
        coverage[origin] += 1
        media_lineage[sku] = {'file': name, 'origin': origin, 'sha256': image_info[name]['sha256']}
        media_rows.append({'sku': sku, 'url_key': row['url_key'], 'store_view_code': '',
                           **{role: '/wands-lab/' + source.name for role in ('base_image', 'small_image', 'thumbnail')},
                           **{role + '_label': row['name'] + ' (synthetic illustration)' for role in ('base_image', 'small_image', 'thumbnail')}})
    options = {}
    for row in chosen:
        if row['product_type'] == 'configurable':
            for variation in row['configurable_variations'].split('|'):
                for field in variation.split(','):
                    code, value = field.split('=', 1)
                    if code != 'sku':
                        options.setdefault(code, set()).add(value)
    options = {code: sorted(values) for code, values in sorted(options.items())}
    stats = {'products': len(chosen), 'product_types': dict(Counter(row['product_type'] for row in chosen)),
             'disabled_products': sum(row['product_online'] == '2' for row in chosen),
             'configurable_links': sum(len(dependencies(row)) for row in chosen if row['product_type'] == 'configurable'),
             'bundle_selections': sum(len(row['bundle_values'].split('|')) for row in chosen if row['product_type'] == 'bundle'),
             'bundle_options': sum(len({dict(field.split('=', 1) for field in group.split(','))['name']
                                         for group in row['bundle_values'].split('|')})
                                   for row in chosen if row['product_type'] == 'bundle'),
             'image_files': len(images), 'media_assignments': len(media_rows), 'media_roles': 3 * len(media_rows),
             'media_coverage': dict(coverage)}
    args.output.mkdir(parents=True)
    data = {f'data/{index}-{kind}.csv': csv_bytes([row for row in chosen if row['product_type'] == kind])
            for index, kind in enumerate(('simple', 'configurable', 'bundle'), start=1)}
    data['data/4-media.csv'] = csv_bytes(media_rows)
    data['data/attribute-options.json'] = json_bytes(options)
    data['data/media-inventory.json'] = json_bytes(image_info)
    data['data/media-lineage.json'] = json_bytes({'assignments': media_lineage, 'missing_disabled_skus': missing_skus})
    data['data/counts.json'] = json_bytes(stats)
    for name in ['README.md', 'ACCEPTANCE.md', 'DOWNLOADS.md', 'DATA_CARD.md', 'WANDS-LICENSE.txt', 'CITATION.bib', 'TERMS.md', 'CC0-1.0.txt']:
        data['docs/' + name] = HERE / name
    data['docs/ROCKET-WEB-LICENSE.txt'] = HERE.parent / 'LICENSE.txt'
    module_files = {}
    module_root = args.repository / 'app/code/RocketWeb/LabCatalog'
    for path in sorted(module_root.rglob('*')):
        relative = path.relative_to(module_root)
        if path.is_file() and relative.parts[0] != 'Test' and path.suffix in ('.php', '.xml', '.json'):
            if any(value in path.read_text() for value in ('/Users/', 'relevance.comtom.lab', 'gophersport-com/')):
                raise ValueError(f'Private environment reference in module: {relative}')
            module_files['module/' + relative.as_posix()] = path
    module_files['tools/release.py'] = HERE / 'release.py'
    module_files['tools/download.py'] = HERE / 'download.py'
    module_files['tools/preflight.php'] = HERE / 'preflight.php'
    module_files['docs/module-terms.md'] = HERE / 'TERMS.md'
    module_files['module/LICENSE.txt'] = module_root / 'LICENSE.txt'
    artifacts = [write_archive(args.output / 'catalog.tar', data), write_archive(args.output / 'module.tar', module_files)]
    chunk, chunk_size, number = {}, 0, 1
    for name, source in sorted(images.items()):
        size = source.stat().st_size
        if chunk and chunk_size + size + 10240 > args.media_chunk_mib * 1024 ** 2:
            artifacts.append(write_archive(args.output / f'media-{number:03d}.tar', chunk))
            logging.info('Archived media chunk %d', number)
            chunk, chunk_size, number = {}, 0, number + 1
        chunk[name] = source
        chunk_size += 512 + ((size + 511) // 512) * 512
    if chunk:
        artifacts.append(write_archive(args.output / f'media-{number:03d}.tar', chunk))
    inputs += [args.base_prompts, args.families / 'image-prompts.jsonl', args.corrected_media / 'manifest.json']
    source_inventory = {str(p.relative_to(args.repository)): digest(p) for p in sorted(module_root.rglob('*')) if p.is_file() and 'Test' not in p.parts}
    source_inventory.update({str(p.relative_to(args.repository)): digest(p) for p in HERE.iterdir() if p.is_file()})
    manifest = {'schema': 1, 'release': args.release, 'profile': args.profile,
                'status': 'private candidate; see profile-pinned acceptance record in docs/ACCEPTANCE.md',
                'install_mode': 'fresh dedicated lab only; not a live-store update or resumable import',
                'upstream': {'name': 'WANDS', 'revision': REVISION, 'license': 'MIT',
                             'product_csv_sha256': 'd993926254572e6eba96c8fd87cc549a17fb91ad3748308036eee4cf92b10ac6'},
                'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.repository, text=True).strip(),
                'source_files': source_inventory, 'inputs': {f'{i:02d}-{p.name}': digest(p) for i,p in enumerate(inputs)},
                'counts': stats, 'artifacts': artifacts,
                'licensing': {'upstream': 'MIT', 'code': 'MIT', 'authored_data': 'MIT', 'generated_media': 'CC0-1.0',
                              'media_scope': 'rights held by Rocket Web; third-party rights not waived',
                              'approved': '2026-09-11'},
                'dependency_closure': True, 'contains_customers_orders_or_database_dump': False}
    encoded = json_bytes(manifest)
    (args.output / 'manifest.json').write_bytes(encoded)
    pin = hashlib.sha256(encoded).hexdigest()
    (args.output / 'manifest.sha256').write_text(pin + '  manifest.json\n')
    (args.output / 'release.py').write_bytes((HERE / 'release.py').read_bytes())
    result = verify_release(args.output, pin)
    logging.info('COMPLETE %s', json.dumps({'counts': stats, 'verification': result, 'manifest_sha256': pin}))
    (args.output / 'build-summary.json').write_bytes(json_bytes({'counts': stats, 'verification': result, 'manifest_sha256': pin}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['repository', 'base', 'families', 'realism', 'corrections', 'base-prompts', 'media', 'corrected-media', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--profile', choices=['starter', 'full'], required=True)
    parser.add_argument('--release', required=True)
    parser.add_argument('--media-chunk-mib', type=int, default=256)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output.with_suffix('.log'), level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        if args.media_chunk_mib < 1:
            raise ValueError('Media chunk size must be positive')
        build(args)
    except Exception:
        logging.exception('Release build failed')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
