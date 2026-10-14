"""Exercise the real CLI on a pre-created disposable wands_installer_ database."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

DIST = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIST))
from catalog import Runtime, parser, digest, encoded, tree_inventory
from release import write_archive


def package(repository, output, tag, rows, module):
    output.mkdir()
    source = repository / 'var/catalog-qa-20261006/candidate-v5'
    files = {'module/' + path.relative_to(module).as_posix(): path for path in module.rglob('*') if path.is_file()}
    files.update({'media/' + path.relative_to(source / 'media/import').as_posix(): path
                  for path in (source / 'media/import').rglob('*') if path.is_file()})
    csv_file = output / 'qa.csv'
    with csv_file.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    files['data/6-qa.csv'] = csv_file
    for phase in ('1-simple', '2-configurable', '3-bundle', '4-media', '5-merchandising'):
        files['data/' + phase + '.csv'] = b'sku\n'
    files['data/counts.json'] = encoded({'products': len(rows), 'product_types': dict(Counter(row['product_type'] for row in rows))})
    artifact = write_archive(output / 'catalog.tar', files)
    (output / 'manifest.json').write_bytes(encoded({'schema': 1, 'release': tag, 'profile': 'full', 'artifacts': [artifact]}))
    csv_file.unlink()
    return digest(output / 'manifest.json')


def verify_inverse_recovery(root, runtime, restore):
    before = runtime.request('inspect')
    assert before['database'].startswith('wands_installer_'), 'A disposable installer database is required'
    backups = list((root / 'var/wands-installer').glob('20*/quarantine-*/backup.json'))
    inverse = max(backups, key=lambda path: path.stat().st_mtime).parent
    original = inverse.parent
    expected = json.loads((inverse / 'plan.json').read_bytes())['before_catalog_sha256']
    restore(inverse)
    assert runtime.request('inspect')['catalog_sha256'] == expected, 'Inverse recovery must restore its saved database'
    restore(original)
    assert runtime.request('inspect')['catalog_sha256'] == before['catalog_sha256'], 'Reapplying recovery must restore the accepted state'
    return True


def main():
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument('--magento-root', type=Path, required=True)
    options.add_argument('--php-binary', required=True)
    options.add_argument('--db-container', required=True)
    options.add_argument('--output', type=Path, required=True)
    options.add_argument('--module-root', type=Path, help='Explicit module snapshot for reproducible fixture releases')
    options.add_argument('--base-url', default='http://127.0.0.1:18049/')
    args = options.parse_args()
    repository = DIST.parents[3]
    args.output.mkdir(exist_ok=False)
    module = args.output / 'module-source'
    shutil.copytree(args.module_root or repository / 'app/code/RocketWeb/LabCatalog', module)
    php = json.dumps([args.php_binary])
    common = ['--magento-root', str(args.magento_root.resolve()), '--php-command', php, '--work-dir', str(args.output / 'work'),
              '--base-url', args.base_url, '--db-container', args.db_container, '--json-plan']
    runtime = Runtime(parser().parse_args(['install', *common]))
    snapshot = runtime.request('inspect')
    assert snapshot['database'].startswith('wands_installer_') and snapshot['products'] == 0, 'An empty disposable fixture is required'
    fixture_program = (Path(__file__).parent / 'installer_fixture.php').read_text().removeprefix('<?php')
    def fixture(action, **values):
        result = subprocess.run([args.php_binary, '-d', 'memory_limit=4G', '-r', fixture_program],
            cwd=args.magento_root, input=encoded({'root': str(args.magento_root), 'action': action, **values}), capture_output=True)
        if result.returncode:
            raise RuntimeError('Fixture action failed: ' + result.stderr.decode(errors='replace')[-1500:])
        return json.loads(result.stdout)
    def run(operation, release=None, *extra, apply=False, expect=0, expect_apply=0):
        command = [sys.executable, str(DIST / 'catalog.py'), operation, *common]
        if release:
            tag, pin, path = release
            command += ['--tag', tag, '--manifest-sha256', pin, '--release-dir', str(path)]
        command += list(extra)
        preview = subprocess.run(command, capture_output=True, text=True)
        if preview.returncode != expect:
            raise RuntimeError(preview.stderr[-2500:] or preview.stdout[-2500:])
        (args.output / (operation + '-preview-' + str(len(list(args.output.glob('*preview*')))) + '.log')).write_text(preview.stdout + preview.stderr)
        if expect:
            return preview.stderr
        plan = json.loads(preview.stdout)
        if apply:
            result = subprocess.run([*command, '--apply', '--jobs-stopped', '--confirm', plan['confirmation']], capture_output=True, text=True)
            (args.output / (operation + '-apply-' + str(len(list(args.output.glob('*apply*')))) + '.log')).write_text(result.stdout + result.stderr)
            if result.returncode != expect_apply:
                raise RuntimeError(result.stderr[-2500:] or result.stdout[-2500:])
        return plan
    with (repository / 'var/catalog-qa-20261006/candidate-v5/data/products.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    v1dir = args.output / 'v1'
    v1 = ('fixture-v1', package(repository, v1dir, 'fixture-v1', rows, module), v1dir)
    fixture('seed-old')
    outside = runtime.request('preserved')
    install = run('install', v1, apply=True)
    assert install['changes']['preserved_existing_products'] == 1
    assert runtime.request('preserved') == outside, 'Default installation must preserve the existing catalog'
    original = runtime.request('inspect')
    assert original['products'] == 128 and original['catalog_products'] == 127
    shutil.move(args.magento_root / 'var/wands-installer/current', args.output / 'initial-receipt')
    assert 'No installer receipt' in run('update', v1, expect=1)
    run('adopt', v1, apply=True)
    assert runtime.request('inspect') == original, 'Adoption must not change the catalog'
    target = next(row for row in rows if row['product_type'] == 'simple' and row['name'] and row.get('price'))
    sku = target['sku']
    fixture('stock', sku=sku, qty=41)
    old_stock = fixture('observe')
    updated = [dict(row) for row in rows]
    selected = next(row for row in updated if row['sku'] == sku)
    selected.update(name=selected['name'] + ' Updated', price=str(float(selected['price']) + 2), qty='999')
    replacement = next(row['base_image'] for row in rows if row.get('base_image') and row['base_image'] != selected['base_image'])
    for field in ('base_image', 'small_image', 'thumbnail_image', 'additional_images'):
        selected[field] = replacement
    addition = next(dict(row) for row in rows if row['product_type'] == 'virtual')
    addition.update(sku='WANDS-NEW-VIRTUAL', name='New virtual test product', url_key='wands-new-virtual')
    updated.append(addition)
    v2dir = args.output / 'v2'
    v2 = ('fixture-v2', package(repository, v2dir, 'fixture-v2', updated, module), v2dir)
    delta = run('update', v2, apply=True)
    assert delta['changes']['added_products'] == 1 and delta['changes']['changed_products'] == 1
    assert delta['changes']['gallery_reset_products'] == 1
    after_stock = fixture('observe')
    assert runtime.request('preserved') == outside, 'Update must preserve products outside WANDS'
    for key in ('stock_rows', 'source_rows'):
        before = [row for row in old_stock[key] if row['sku'] == sku]
        after = [row for row in after_stock[key] if row['sku'] == sku]
        assert before == after, key + ' changed during update'
    before_noop = runtime.request('inspect')
    run('update', v2, apply=True)
    assert runtime.request('inspect') == before_noop, 'A same-release update must be a no-op'
    fixture('name', sku=sku, name='Local edit')
    assert 'Local edits' in run('update', v1, expect=1)
    fixture('name', sku=sku, name=selected['name'])
    baseline = json.loads((args.magento_root / 'var/wands-installer/current/receipt.json').read_bytes())
    assert runtime.request('inspect')['catalog_sha256'] == baseline['catalog_sha256'], 'Removing the temporary edit must restore the baseline'
    before_reset = runtime.request('inspect')
    assert before_reset['products'] == 129
    assert 'Existing WANDS products' in run('install', v1, expect=1)
    reset = run('install', v1, '--reset-existing-catalog', '--dedicated-test-installation', apply=True)
    assert reset['changes']['removed_products'] == 129
    assert reset['changes']['removed_reservations'] == 1
    assert runtime.request('inspect')['reservations'] == 0
    assert fixture('observe')['queued_reservation_cleanup'] == 0, 'Reset must not queue cleanup against reintroduced SKUs'
    receipts = [path for path in (args.magento_root / 'var/wands-installer').glob('20*') if (path / 'plan.json').exists()]
    receipt = next(path for path in receipts if json.loads((path / 'plan.json').read_bytes())['confirmation'] == reset['confirmation'])
    run('restore', None, '--receipt', str(receipt), apply=True)
    restored = runtime.request('inspect')
    assert restored['catalog_sha256'] == before_reset['catalog_sha256']
    verify_inverse_recovery(args.magento_root, runtime,
                            lambda path: run('restore', None, '--receipt', str(path), apply=True))
    wrapper = args.output / 'failing-indexer.py'
    wrapper.write_text('import os,sys\nif "indexer:reindex" in sys.argv: raise SystemExit(19)\nos.execv(' + repr(args.php_binary) + ', [' + repr(args.php_binary) + ']+sys.argv[1:])\n')
    run('install', v1, '--reset-existing-catalog', '--dedicated-test-installation', '--php-command',
        json.dumps([sys.executable, str(wrapper)]), apply=True, expect_apply=1)
    assert runtime.request('inspect')['maintenance'], 'A failed apply must retain maintenance mode'
    receipt = max([path for path in (args.magento_root / 'var/wands-installer').glob('20*') if (path / 'backup.json').is_file()], key=lambda path: path.name)
    assert json.loads((receipt / 'status.json').read_bytes())['state'] == 'failed'
    run('restore', None, '--receipt', str(receipt), apply=True)
    assert runtime.request('inspect')['catalog_sha256'] == before_reset['catalog_sha256']
    result = {'passed': True, 'edition': snapshot['edition'], 'version': snapshot['version'], 'php': snapshot['php'],
              'fixture_products': 127, 'after_update': 128, 'reset_products_deleted': 129,
              'total_products_after_default_install': 128, 'total_products_after_update': 129,
              'default_preserved_existing_catalog': True,
              'update_preserved_legacy_and_msi_stock': True, 'local_edits_refused': True,
              'gallery_replacement_verified': True, 'reset_cleared_reservations_synchronously': True,
              'adoption_verified_without_catalog_writes': True, 'failed_apply_restored': True,
              'inverse_recovery_verified': True,
              'restore_matched_original_catalog_fingerprint': True, 'original_empty_fingerprint': snapshot['catalog_sha256']}
    result['module_inventory_sha256'] = hashlib.sha256(encoded(tree_inventory(module))).hexdigest()
    (args.output / 'acceptance.json').write_bytes(encoded(result))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
