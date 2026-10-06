"""Package the pinned accepted expansion and QA suite; never install or publish."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import logging
from pathlib import Path
import re
import subprocess
import sys

from release import dependencies, digest, safe_path, verify_release, write_archive
from download import MANIFEST_LIMIT
from build_candidate_assets import qualify_document_links

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[3]
sys.path.insert(0, str(HERE.parent))
from build_qa_catalog import verify_package

EXPANSION_PIN = '4c276a38a325a682c1537c5932c0c24c51dc2732a220cac19faec6646174c386'
QA_PIN = '7fac73094a043c9fa4b11eed9def21d56e59a7dacb83ae4e29af332295262836'
EXPECTED_TYPES = {'simple': 103720, 'configurable': 4001, 'bundle': 62,
                  'virtual': 14, 'downloadable': 12, 'grouped': 6}
DATA_FILES = ['1-simple.csv', '2-configurable.csv', '3-bundle.csv', '4-media.csv',
              '5-merchandising.csv', 'attribute-options.json', 'media-inventory.json',
              'media-lineage.json', 'counts.json']
NOTICES = ['TERMS.md', 'WANDS-LICENSE.txt', 'CC0-1.0.txt', 'CITATION.bib']
SCRIPTS = ['release.py', 'download.py', 'github_download.py', 'preflight.php']


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def pinned_manifest(root, pin):
    path = Path(root) / 'manifest.json'
    if path.is_symlink() or digest(path) != pin:
        raise ValueError('Input manifest differs from pinned accepted identity')
    return json.loads(path.read_bytes())


def verified_files(root, inventory, names):
    """Verify only explicitly selected public members, never copy an input tree."""
    root = Path(root).resolve()
    files = {}
    for name in sorted(names):
        safe_path(name)
        path = root / name
        item = inventory[name]
        if (path.is_symlink() or not path.resolve().is_relative_to(root)
                or not path.is_file() or path.stat().st_size != item['bytes']
                or digest(path) != item['sha256']):
            raise ValueError('Pinned member changed: ' + name)
        files[name] = path
    return files


def media_archives(output, files, chunk_mib=512):
    limit = chunk_mib * 1024 ** 2
    if not 1 <= chunk_mib <= 1024:
        raise ValueError('Use media chunks between 1 and 1024 MiB')
    result, chunk, size = [], {}, 0
    for name, path in sorted(files.items()):
        member_size = 512 + ((path.stat().st_size + 511) // 512) * 512
        if member_size + 10240 > limit:
            raise ValueError('Media member exceeds chunk size')
        if chunk and size + member_size + 10240 > limit:
            result.append(write_archive(output / f'media-{len(result) + 1:03d}.tar', chunk))
            logging.info('Archived media chunk %d', len(result))
            chunk, size = {}, 0
        chunk[name] = path
        size += member_size
    if chunk:
        result.append(write_archive(output / f'media-{len(result) + 1:03d}.tar', chunk))
    return result


def product_inventory(paths):
    skus, types, parents = set(), Counter(), []
    visible = disabled = links = 0
    for path in paths:
        with path.open(newline='') as stream:
            for row in csv.DictReader(stream):
                sku = row['sku']
                if not sku or sku in skus:
                    raise ValueError('Empty or duplicate product SKU: ' + sku)
                if '__EMPTY__VALUE__' in row.values():
                    raise ValueError('Fresh-install input contains update-only empty sentinel')
                skus.add(sku)
                types[row['product_type']] += 1
                disabled += row.get('product_online') in ('0', '2', 'Disabled')
                visible += row.get('product_online') == '1' and row.get('visibility') != 'Not Visible Individually'
                if row['product_type'] in ('configurable', 'bundle'):
                    refs = dependencies(row)
                    parents.append((sku, refs))
                    if row['product_type'] == 'configurable':
                        links += len(refs)
    for sku, refs in parents:
        if not refs <= skus:
            raise ValueError('Missing dependency for ' + sku)
    return {'products': len(skus), 'product_types': dict(types), 'disabled_products': disabled,
            'enabled_visible_products': visible, 'configurable_links': links}


def acceptance_summary(path, qa_pin):
    receipt = json.loads(path.read_bytes())
    if (receipt.get('passed') is not True or receipt.get('manifest_sha256') != qa_pin
            or receipt.get('wands_products_per_store') != 107815):
        raise ValueError('Installation acceptance does not qualify this QA identity')
    stores = {}
    for name in ('studio', 'comtom'):
        row = receipt[name]
        if not all(row[part].get('passed') is True for part in ('database', 'row_preservation', 'runtime', 'browser')):
            raise ValueError('Incomplete store acceptance: ' + name)
        stores[name] = {
            'products': row['database']['wands_products'],
            'product_types': row['database']['product_types'],
            'product_checks': row['runtime']['product_checks'],
            'cart_cases': row['runtime']['cart_cases'],
            'cart_compositions': row['runtime']['cart_compositions'],
            'visible_pages': row['browser']['products_checked'],
            'excluded_pages': row['browser']['excluded_products_checked'],
            'existing_product_rows_changed': row['row_preservation']['existing_product_rows_changed'],
            'existing_stock_rows_changed': row['row_preservation']['existing_stock_rows_changed'],
            'quotes_saved': row['runtime']['quotes_saved'],
            'orders_created': row['runtime']['orders_created'],
        }
    return {'schema': 1, 'qa_manifest_sha256': qa_pin,
            'scope': 'Native import and existing lab runtime acceptance; no third store created',
            'stores': stores, 'tooling_tests_before_packaging': receipt['tooling_tests'],
            'limits': ['No new empty-store end-to-end installation of these release archives',
                       'Comtom browser acceptance used private SSH ingress and private CA bypass',
                       'Checkout, payments and post-order download access are not qualified',
                       'Custom file option tests use existing-file metadata, not browser upload']}


def build(expansion, qa, acceptance, output, tag):
    if not re.fullmatch(r'catalog-\d{4}\.\d{2}\.\d{2}(?:-[a-z0-9-]+)?', tag):
        raise ValueError('Use a new dated catalog tag')
    if output.exists() or output.is_symlink():
        raise FileExistsError('Use a new output directory')
    base = pinned_manifest(expansion, EXPANSION_PIN)
    qm = pinned_manifest(qa, QA_PIN)
    verify_package(qa)
    summary = acceptance_summary(acceptance, QA_PIN)
    public = ['data/' + name for name in DATA_FILES]
    media = [name for name in base['files'] if re.fullmatch(r'media/wands-expanded/[0-9a-f]{64}\.jpg', name)]
    if len(media) != 95401:
        raise ValueError('Unexpected accepted image inventory')
    sources = verified_files(expansion, base['files'], public + media)
    qa_public = ['data/products.csv', 'fixtures.json', 'test-matrix.json', 'media-lineage.json']
    qa_public += [name for name in qm['files'] if name.startswith('media/import/wands-qa')]
    qa_sources = verified_files(qa, qm['files'], qa_public)
    counts = product_inventory([sources['data/' + n] for n in DATA_FILES[:3]] + [qa_sources['data/products.csv']])
    if counts['products'] != 107815 or counts['product_types'] != EXPECTED_TYPES:
        raise ValueError('Unexpected combined catalog counts')
    counts.update({'image_files': 95417, 'distinct_image_hashes': 95401, 'qa_products': 127,
                   'download_files': 3, 'new_expansion_categories': 32, 'qa_categories': 11,
                   'quarantined_products': 213})
    with qa_sources['data/products.csv'].open(newline='') as stream:
        qa_rows = list(csv.DictReader(stream))
    qa_assignments = sum(bool(row.get('base_image')) for row in qa_rows)
    counts['media_assignments'] = base['media_assignments'] + qa_assignments
    counts['media_roles'] = json.loads(sources['data/counts.json'].read_bytes())['media_roles'] + 3 * qa_assignments
    output.mkdir(parents=True)
    full, toolkit, assets = (output / name for name in ('full', 'toolkit', 'assets'))
    for path in (full, toolkit, assets):
        path.mkdir()
    data = {name: path for name, path in sources.items() if name.startswith('data/')}
    data['data/counts.json'] = encoded(counts)
    data['data/6-qa.csv'] = qa_sources['data/products.csv']
    for name in ('fixtures.json', 'test-matrix.json', 'media-lineage.json'):
        data['data/qa/' + name] = qa_sources[name]
    data['docs/INSTALLATION_ACCEPTANCE.json'] = encoded(summary)
    for name in NOTICES + ['PRODUCTION_RELEASE.md', 'DATA_CARD.md']:
        data['docs/' + name] = HERE / name
    data['docs/ROCKET-WEB-LICENSE.txt'] = HERE.parent / 'LICENSE.txt'
    for name, path in list(data.items()):
        if name.endswith('.md') and isinstance(path, Path):
            data[name] = qualify_document_links(path.read_bytes(), path, name, data, REPOSITORY)
    module_root = REPOSITORY / 'app/code/RocketWeb/LabCatalog'
    module = {'module/LICENSE.txt': module_root / 'LICENSE.txt'}
    for path in sorted(module_root.rglob('*')):
        relative = path.relative_to(module_root)
        if path.is_file() and relative.parts[0] != 'Test' and path.suffix in ('.php', '.xml', '.json'):
            if any(value in path.read_text() for value in ('/Users/', 'relevance.comtom.lab', 'gophersport-com/')):
                raise ValueError('Private environment reference in module: ' + str(relative))
            module['module/' + relative.as_posix()] = path
    images = {name: sources[name] for name in media}
    for name in qa_public:
        if name.startswith('media/import/'):
            images[name.replace('media/import/', 'media/', 1)] = qa_sources[name]
    artifacts = [write_archive(full / 'catalog.tar', data), write_archive(full / 'module.tar', module)]
    artifacts += media_archives(full, images)
    # Check source parity again after writing, including any file changed mid-build.
    for artifact in artifacts:
        if artifact['bytes'] >= 2 ** 31:
            raise ValueError('Asset exceeds GitHub size limit')
        for name, info in artifact['files'].items():
            original = base['files'].get(name)
            if name == 'data/6-qa.csv': original = qm['files']['data/products.csv']
            elif name.startswith('data/qa/'): original = qm['files'][name.removeprefix('data/qa/')]
            elif name.startswith('media/wands-qa'): original = qm['files']['media/import/' + name.removeprefix('media/')]
            if original and name != 'data/counts.json' and info['sha256'] != original['sha256']:
                raise ValueError('Source changed during archive write: ' + name)
    source_files = {str(path.relative_to(REPOSITORY)): digest(path) for path in module.values()}
    source_files.update({str((HERE / name).relative_to(REPOSITORY)): digest(HERE / name)
                         for name in SCRIPTS + ['build_expanded_release.py']})
    manifest = {'schema': 1, 'release': tag, 'profile': 'full', 'counts': counts,
                'install_mode': 'Fresh dedicated lab only; no resumable import or live-store update',
                'inputs': {'accepted_expansion_manifest': EXPANSION_PIN, 'qa_manifest': QA_PIN},
                'build_baseline_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPOSITORY, text=True).strip(),
                'source_files': source_files, 'artifacts': artifacts,
                'contains_customers_orders_or_database_dump': False,
                'runtime_scope': 'See docs/INSTALLATION_ACCEPTANCE.json for existing-store evidence and limits'}
    content = encoded(manifest)
    if len(content) > MANIFEST_LIMIT:
        raise ValueError('Manifest exceeds downloader size limit')
    (full / 'manifest.json').write_bytes(content)
    full_pin = digest(full / 'manifest.json')
    result = verify_release(full, full_pin)
    toolkit_files = {'tools/' + name: HERE / name for name in SCRIPTS}
    toolkit_files.update({'docs/' + name: HERE / name for name in NOTICES + ['PRODUCTION_RELEASE.md', 'DATA_CARD.md']})
    toolkit_files['README.md'] = HERE / 'PRODUCTION_RELEASE.md'
    toolkit_files['docs/ROCKET-WEB-LICENSE.txt'] = HERE.parent / 'LICENSE.txt'
    toolkit_files['docs/INSTALLATION_ACCEPTANCE.json'] = encoded(summary)
    for name, path in list(toolkit_files.items()):
        if name.endswith('.md') and isinstance(path, Path):
            toolkit_files[name] = qualify_document_links(path.read_bytes(), path, name, toolkit_files, REPOSITORY)
    tool_artifact = write_archive(toolkit / 'tools.tar', toolkit_files)
    (toolkit / 'manifest.json').write_bytes(encoded({'schema': 1, 'release': tag, 'profile': 'toolkit', 'artifacts': [tool_artifact]}))
    toolkit_pin = digest(toolkit / 'manifest.json')
    verify_release(toolkit, toolkit_pin)
    for profile, root in (('full', full), ('toolkit', toolkit)):
        for path in root.iterdir():
            (assets / (profile + '-' + path.name)).hardlink_to(path)
    for name in SCRIPTS[:3]:
        (assets / name).write_bytes((HERE / name).read_bytes())
    (assets / 'README.md').write_bytes((HERE / 'PRODUCTION_RELEASE.md').read_bytes())
    inventory = {'schema': 1, 'repository': 'rocketweb/mageos-large-demo-catalog', 'tag': tag,
                 'profile_pins': {'full': full_pin, 'toolkit': toolkit_pin}, 'counts': counts,
                 'offline_verification': result,
                 'assets': {p.name: {'bytes': p.stat().st_size, 'sha256': digest(p)} for p in sorted(assets.iterdir())}}
    (assets / 'release-inventory.json').write_bytes(encoded(inventory))
    (assets / 'SHA256SUMS').write_text(''.join(digest(p) + '  ' + p.name + '\n' for p in sorted(assets.iterdir())))
    logging.info('COMPLETE %s', json.dumps({'pins': inventory['profile_pins'], 'counts': counts, 'verification': result}))
    return inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('expansion', 'qa', 'acceptance', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output.with_suffix('.log'), level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        build(args.expansion, args.qa, args.acceptance, args.output, args.tag)
    except Exception:
        logging.exception('Expanded release build failed')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
