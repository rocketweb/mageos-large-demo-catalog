import argparse
from collections import Counter
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tarfile
import unittest

DIST = Path(__file__).resolve().parents[1] / 'distribution'
sys.path.insert(0, str(DIST))
import catalog
from build_installer import build
from release import write_archive


def data(root, rows, extra=None):
    root.mkdir(parents=True, exist_ok=True)
    header = ['sku', 'product_type', 'attribute_set_code', 'name', 'price', 'special_price', 'qty', 'categories']
    with (root / '1-simple.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, header)
        writer.writeheader()
        for row in rows:
            writer.writerow({'sku': 'WANDS-A', 'product_type': 'simple', 'attribute_set_code': 'Default',
                             'name': 'Chair', 'price': '20', 'special_price': '', 'qty': '5',
                             'categories': 'WANDS Catalog/Chairs', **row})
    for phase in ('2-configurable', '3-bundle', '4-media', '5-merchandising'):
        (root / (phase + '.csv')).write_text('sku\n')
    if extra:
        for name, text in extra.items():
            (root / name).write_text(text)
    (root / 'counts.json').write_text(json.dumps({'products': len(rows), 'product_types': dict(Counter(row.get('product_type', 'simple') for row in rows))}))


class FakeRuntime:
    def __init__(self, root):
        self.root = root
        self.events = []
        self.commands = []
        self.snapshot = {'edition': 'mage-os', 'version': '3.5.0', 'php': '8.4.24', 'identity': 'fixture',
            'database': 'isolated_fixture', 'websites': ['admin', 'base'], 'catalog_sha256': 'empty',
            'products': 0, 'catalog_products': 0, 'categories': 2, 'deletable_categories': 0, 'retained_category_roots': [1, 2],
            'running_cron': 0, 'remote_storage': False, 'maintenance': False, 'mode': 'developer', 'wands_collision': False}
        self.fail_command = None

    def path(self, path):
        return str(path)

    def request(self, action, **kwargs):
        self.events.append(action)
        if action == 'inspect':
            return copy.deepcopy(self.snapshot)
        if action == 'backup':
            path = Path(kwargs['destination'])
            path.write_text('-- SQL fixture backup\n' * 20)
            return {'database_sha256': catalog.digest(path), 'database_bytes': path.stat().st_size}
        if action == 'reset':
            self.snapshot['products'] = 0
            self.snapshot['catalog_sha256'] = 'reset'
        if action == 'restore':
            self.snapshot['catalog_sha256'] = 'empty'
        return {'passed': True}

    def magento(self, receipt, *args):
        self.commands.append(args)
        self.events.append(args[0])
        if args[0] == 'maintenance:enable':
            self.snapshot['maintenance'] = True
        if args[0] == 'maintenance:disable':
            self.snapshot['maintenance'] = False
        if args[0] == self.fail_command:
            raise RuntimeError('Fixture command failed')


class CatalogInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = (Path(self.temp.name) / 'store').resolve()
        for name in ('app/etc', 'app/code', 'var/wands-installer', 'pub/media'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / 'app/etc/config.php').write_text('<?php return [];')
        self.stage = Path(self.temp.name) / 'stage'
        data(self.stage / 'data', [{}])
        (self.stage / 'module').mkdir()
        (self.stage / 'module/registration.php').write_text('<?php // fixture')
        (self.stage / 'media').mkdir()
        self.runtime = FakeRuntime(self.root)
        self.args = argparse.Namespace(magento_root=self.root, allow_unverified_platform=False,
            operation='install', reset_existing_catalog=False, dedicated_test_installation=False,
            keep_default_website=False,
            tag='fixture-1', profile='full', base_url='http://fixture.test/', locales=['en_US'],
            jobs_stopped=True, confirm=None, db_dump='mysqldump', db_client='mysql', db_container=None)
        self.args.apply = False
        self.delta = Path(self.temp.name) / 'delta'

    def plan(self):
        return catalog.build_plan(self.args, self.runtime, 'a' * 64, self.stage, self.delta)

    def test_default_preserves_existing_products_and_reset_is_explicit(self):
        self.runtime.snapshot['products'] = 8
        plan, _ = self.plan()
        self.assertEqual(plan['changes']['preserved_existing_products'], 8)
        self.assertEqual(plan['changes']['removed_products'], 0)
        self.runtime.snapshot['catalog_products'] = 1
        with self.assertRaisesRegex(ValueError, 'Existing WANDS products'):
            self.plan()
        self.args.reset_existing_catalog = True
        with self.assertRaisesRegex(ValueError, 'dedicated-test-installation'):
            self.plan()
        self.args.dedicated_test_installation = True
        self.runtime.snapshot['deletable_categories'] = 6
        plan, _ = self.plan()
        self.assertEqual(plan['changes']['removed_products'], 8)
        self.assertEqual(plan['changes']['removed_categories'], 6)
        self.assertTrue(plan['confirmation'].startswith('RESET:'))
        self.assertNotIn('reset', self.runtime.events)

    def test_plan_binds_target_release_url_counts_and_module(self):
        first, _ = self.plan()
        self.args.base_url = 'http://other.test/'
        second, _ = self.plan()
        self.assertNotEqual(first['confirmation'], second['confirmation'])
        self.assertEqual(second['module_sha256']['registration.php'], catalog.digest(self.stage / 'module/registration.php'))

    def test_platform_and_running_writer_guards(self):
        self.runtime.snapshot['version'] = '3.4.0'
        with self.assertRaisesRegex(ValueError, 'not qualified'):
            self.plan()
        self.runtime.snapshot.update(edition='magento', version='2.4.9')
        self.plan()
        self.runtime.snapshot['php'] = '8.3.0'
        with self.assertRaisesRegex(ValueError, 'not qualified'):
            self.plan()
        self.runtime.snapshot['php'] = '8.4.24'
        self.runtime.snapshot['running_cron'] = 1
        with self.assertRaisesRegex(ValueError, 'currently running'):
            self.plan()

    def test_wrong_confirmation_backs_up_but_never_resets(self):
        self.args.reset_existing_catalog = self.args.dedicated_test_installation = True
        plan, snapshot = self.plan()
        self.args.confirm = 'RESET:wrong'
        with self.assertRaisesRegex(ValueError, 'Confirmation'):
            catalog.apply(self.args, self.runtime, plan, snapshot, self.stage, self.delta)
        self.assertIn('backup', self.runtime.events)
        self.assertNotIn('reset', self.runtime.events)
        self.assertFalse(self.runtime.snapshot['maintenance'])
        self.assertFalse((self.root / 'app/code/RocketWeb/LabCatalog').exists())

    def test_stage_tampering_stops_before_catalog_mutation(self):
        plan, snapshot = self.plan()
        self.args.confirm = plan['confirmation']
        (self.stage / 'module/registration.php').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'stage changed'):
            catalog.apply(self.args, self.runtime, plan, snapshot, self.stage, self.delta)
        self.assertNotIn('module:enable', self.runtime.events)

    def test_reset_backed_up_before_deletion_and_failure_keeps_maintenance(self):
        self.args.reset_existing_catalog = self.args.dedicated_test_installation = True
        plan, snapshot = self.plan()
        self.args.confirm = plan['confirmation']
        self.runtime.fail_command = 'lab:wands:import'
        with self.assertRaisesRegex(RuntimeError, 'Fixture command failed'):
            catalog.apply(self.args, self.runtime, plan, snapshot, self.stage, self.delta)
        self.assertLess(self.runtime.events.index('backup'), self.runtime.events.index('reset'))
        self.assertTrue(self.runtime.snapshot['maintenance'])
        receipt = next((self.root / 'var/wands-installer').glob('20*'))
        self.assertTrue(json.loads((receipt / 'status.json').read_text())['restore_required'])

    def test_success_records_receipt_and_stock_preserving_update(self):
        plan, snapshot = self.plan()
        self.args.confirm = plan['confirmation']
        receipt = catalog.apply(self.args, self.runtime, plan, snapshot, self.stage, self.delta)
        self.assertEqual(json.loads((receipt / 'status.json').read_text())['state'], 'verified')
        self.assertFalse(self.runtime.snapshot['maintenance'])
        self.assertTrue((self.root / 'var/wands-installer/current/receipt.json').is_file())

    def test_empty_import_phases_are_skipped(self):
        plan, snapshot = self.plan()
        self.args.confirm = plan['confirmation']
        catalog.apply(self.args, self.runtime, plan, snapshot, self.stage, self.delta)
        imports = [args for args in self.runtime.commands if args[0] == 'lab:wands:import']
        self.assertEqual(len(imports), 1)

    def test_symlinked_destination_is_rejected(self):
        (self.root / 'pub/media').rmdir()
        (self.root / 'pub/media').symlink_to(self.stage)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            catalog.validate_destination(self.root)

    def test_restore_quarantines_changes_and_verifies_original_files(self):
        plan, snapshot = self.plan()
        self.args.confirm = plan['confirmation']
        receipt = catalog.apply(self.args, self.runtime, plan, snapshot, self.stage, self.delta)
        (self.root / 'pub/media/new.txt').write_text('post-import media')
        self.args.receipt = receipt
        self.args.apply = False
        from unittest.mock import patch
        with patch('builtins.print') as printed:
            catalog.restore(self.args, self.runtime)
        preview = json.loads(printed.call_args.args[0])
        self.args.confirm = preview['confirmation']
        self.args.apply = True
        catalog.restore(self.args, self.runtime)
        self.assertFalse((self.root / 'pub/media/new.txt').exists())
        self.assertTrue(next(receipt.glob('quarantine-*')).joinpath('pub/media/new.txt').exists())
        self.assertEqual((self.root / 'app/etc/config.php').read_text(), '<?php return [];')
        inverse = next(receipt.glob('quarantine-*'))
        inverse_info = json.loads((inverse / 'backup.json').read_bytes())
        self.assertEqual(inverse_info['database_sha256'], catalog.digest(inverse / 'database.sql'))
        self.args.receipt = inverse
        self.args.apply = False
        with patch('builtins.print') as printed:
            catalog.restore(self.args, self.runtime)
        self.args.confirm = json.loads(printed.call_args.args[0])['confirmation']
        self.args.apply = True
        catalog.restore(self.args, self.runtime)
        self.assertEqual((self.root / 'pub/media/new.txt').read_text(), 'post-import media')

    def test_restore_does_not_expand_the_backup_scope(self):
        env = self.root / 'app/etc/env.php'
        env.write_text('<?php // current environment')
        plan, snapshot = self.plan()
        self.args.confirm = plan['confirmation']
        receipt = catalog.apply(self.args, self.runtime, plan, snapshot, self.stage, self.delta)
        backup = json.loads((receipt / 'backup.json').read_bytes())
        backup['file_inventory'].pop('app/etc/env.php')
        backup['existing_paths'].remove('app/etc/env.php')
        original = receipt / 'files.tar'
        revised = receipt / 'legacy.tar'
        with tarfile.open(original) as source, tarfile.open(revised, 'w') as target:
            for member in source:
                if member.name != 'app/etc/env.php':
                    target.addfile(member, source.extractfile(member) if member.isfile() else None)
        revised.replace(original)
        backup['file_sha256'] = catalog.digest(original)
        catalog.write_json(receipt / 'backup.json', backup)
        self.args.receipt = receipt
        self.args.apply = False
        from unittest.mock import patch
        with patch('builtins.print') as printed:
            catalog.restore(self.args, self.runtime)
        self.args.confirm = json.loads(printed.call_args.args[0])['confirmation']
        self.args.apply = True
        catalog.restore(self.args, self.runtime)
        self.assertTrue(env.is_file(), 'Recovery must preserve files outside the recorded backup scope')

    def test_delta_only_changes_selected_fields_and_preserves_stock(self):
        before = Path(self.temp.name) / 'before'
        after = Path(self.temp.name) / 'after'
        data(before, [{'special_price': '18'}])
        data(after, [{'name': 'New chair', 'special_price': '', 'qty': '999'}, {'sku': 'WANDS-B'}])
        result = catalog.update_delta(before, after, self.delta)
        self.assertEqual((result['added_products'], result['changed_products']), (1, 1))
        existing = [row for name in result['csv_files'] for row in catalog.read_rows(self.delta / name).values() if row['sku'] == 'WANDS-A']
        self.assertEqual(existing, [{'sku': 'WANDS-A', 'name': 'New chair', 'special_price': catalog.EMPTY}])
        self.assertEqual(json.loads((self.delta / 'before-values.json').read_text())['WANDS-A']['special_price'], '18')

    def test_media_delta_restores_all_roles_and_plans_only_the_affected_gallery(self):
        before = Path(self.temp.name) / 'before'
        after = Path(self.temp.name) / 'after'
        data(before, [{}], {'4-media.csv': 'sku,base_image,small_image,thumbnail_image,additional_images\nWANDS-A,/wands/a.jpg,/wands/a.jpg,/wands/a.jpg,/wands/a.jpg\n'})
        data(after, [{}], {'4-media.csv': 'sku,base_image,small_image,thumbnail_image,additional_images\nWANDS-A,/wands/b.jpg,/wands/a.jpg,/wands/a.jpg,/wands/b.jpg\n'})
        result = catalog.update_delta(before, after, self.delta)
        self.assertEqual(result['gallery_reset_products'], 1)
        self.assertEqual(json.loads((self.delta / 'before-gallery.json').read_bytes()), {'WANDS-A': ['wands/a.jpg']})
        row = catalog.read_rows(self.delta / result['csv_files'][0])['WANDS-A']
        self.assertEqual(row['base_image'], '/wands/b.jpg')
        self.assertEqual(row['small_image'], '/wands/a.jpg')
        self.assertEqual(row['thumbnail_image'], '/wands/a.jpg')
        self.assertNotIn('qty', row)

    def test_changing_composer_dependencies_blocks_restore_before_quarantine(self):
        lock = self.root / 'composer.lock'
        lock.write_text('original dependencies')
        plan, snapshot = self.plan()
        self.args.confirm = plan['confirmation']
        receipt = catalog.apply(self.args, self.runtime, plan, snapshot, self.stage, self.delta)
        lock.write_text('changed dependencies')
        self.args.receipt = receipt
        self.args.apply = True
        with self.assertRaisesRegex(ValueError, 'Composer dependencies changed'):
            catalog.restore(self.args, self.runtime)
        self.assertFalse(list(receipt.glob('quarantine-*')))

    def test_reset_refuses_conflicting_wands_hierarchy_before_deleting(self):
        self.args.reset_existing_catalog = self.args.dedicated_test_installation = True
        self.runtime.snapshot['wands_structure_valid'] = False
        with self.assertRaisesRegex(ValueError, 'conflicting assignments'):
            self.plan()
        self.assertNotIn('reset', self.runtime.events)

    def test_delta_refuses_removal_type_category_and_relationship_changes(self):
        for change in ({'product_type': 'virtual'}, {'categories': 'WANDS Catalog/Other'}, {'sku': 'WANDS-B'}):
            with self.subTest(change=change):
                before = Path(self.temp.name) / ('before-' + str(len(change)) + next(iter(change)))
                after = Path(self.temp.name) / ('after-' + str(len(change)) + next(iter(change)))
                data(before, [{}])
                data(after, [change])
                with self.assertRaisesRegex(ValueError, 'structural|removes'):
                    catalog.update_delta(before, after, self.delta)

    def test_zipapp_is_reproducible_and_has_usable_cli(self):
        first = build(Path(self.temp.name) / 'one.pyz')
        second = build(Path(self.temp.name) / 'two.pyz')
        self.assertEqual(first['sha256'], second['sha256'])
        result = subprocess.run([sys.executable, str(Path(self.temp.name) / 'one.pyz'), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--reset-existing-catalog', result.stdout)

    @unittest.skipUnless(os.environ.get('WANDS_TEST_PHP'), 'Set the intended native PHP binary')
    def test_runtime_mount_probe_rejects_a_different_store_before_bootstrap(self):
        (self.root / 'app/bootstrap.php').write_text('<?php throw new RuntimeException("BOOTSTRAP_CALLED");')
        (self.root / 'app/etc/env.php').write_text('<?php return [];')
        args = catalog.parser().parse_args(['install', '--magento-root', str(self.root), '--php-command', json.dumps([os.environ['WANDS_TEST_PHP']])])
        runtime = catalog.Runtime(args)
        runtime.check_mount()
        other = Path(self.temp.name) / 'other'
        (other / 'app/etc').mkdir(parents=True)
        (other / 'app/bootstrap.php').write_text('<?php throw new RuntimeException("OTHER_BOOTSTRAP_CALLED");')
        (other / 'app/etc/env.php').write_text('<?php return [];')
        args.runtime_root = str(other)
        with self.assertRaisesRegex(RuntimeError, 'same store files'):
            catalog.Runtime(args).check_mount()

    @unittest.skipUnless(os.environ.get('WANDS_TEST_PHP'), 'Set the intended native PHP binary')
    def test_zipapp_executes_its_embedded_php_bridge(self):
        artifact = Path(self.temp.name) / 'installer.pyz'
        build(artifact)
        (self.root / 'app/bootstrap.php').write_text('<?php throw new RuntimeException("BOOTSTRAP_CALLED");')
        (self.root / 'app/etc/env.php').write_text('<?php return [];')
        result = subprocess.run([sys.executable, str(artifact), 'restore', '--magento-root', str(self.root),
            '--receipt', str(self.root / 'var/wands-installer/missing'), '--php-command', json.dumps([os.environ['WANDS_TEST_PHP']])], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('backup.json', result.stderr)
        self.assertNotIn('catalog_runtime.php', result.stderr)

    @unittest.skipUnless(os.environ.get('WANDS_INSTALLER_TEST_STORE') and os.environ.get('WANDS_TEST_PHP'),
                         'Set a disposable installer fixture and its native PHP binary')
    def test_native_gallery_caption_override_is_refused(self):
        root = Path(os.environ['WANDS_INSTALLER_TEST_STORE']).resolve()
        args = catalog.parser().parse_args(['adopt', '--magento-root', str(root),
            '--php-command', json.dumps([os.environ['WANDS_TEST_PHP']])])
        runtime = catalog.Runtime(args)
        current = root / 'var/wands-installer/current'
        baseline = json.loads((current / 'receipt.json').read_bytes())
        rows = catalog.catalog_data(current / 'data')[2]
        sku = next(sku for sku, row in rows.items() if catalog.image_names(row))
        expected = {sku: catalog.image_names(rows[sku])}
        def caption(value):
            result = subprocess.run([os.environ['WANDS_TEST_PHP'], str(DIST / 'acceptance/installer_fixture.php')],
                input=catalog.encoded({'root': str(root), 'action': 'gallery-caption', 'sku': sku, 'caption': value}),
                capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        runtime.request('check-gallery', expected=expected, media_sha256=baseline['release_media_sha256'], guard_scopes=True)
        caption('Synthetic installer guard caption')
        try:
            with self.assertRaisesRegex(RuntimeError, 'Per-store gallery overrides'):
                runtime.request('check-gallery', expected=expected, media_sha256=baseline['release_media_sha256'], guard_scopes=True)
        finally:
            caption(None)
        runtime.request('check-gallery', expected=expected, media_sha256=baseline['release_media_sha256'], guard_scopes=True)


if __name__ == '__main__':
    unittest.main()
