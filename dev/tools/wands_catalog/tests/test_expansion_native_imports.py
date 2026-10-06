import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_expansion_native_imports as runner


class NativeImportBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.stage = self.root / 'var/expansion'
        self.stage.mkdir(parents=True)
        (self.stage / 'products.csv').write_text('sku\nWANDS-SYN-EXAMPLE\n')
        self.before = self.root / 'before.json'
        self.before.write_text('{"schema":2,"fixture":true}')
        self.snapshot = self.root / 'expansion_store_snapshot.php'
        shutil.copyfile(Path(runner.__file__).with_name('expansion_store_snapshot.php'), self.snapshot)
        self.plan = {'target_root': '/fixture', 'website_code': 'wands',
                     'candidate_sha256': runner.CANDIDATE_SHA256,
                     'delta': {'before_wands_products': 53844, 'after_wands_products': 107688,
                               'product_inserts': 53844, 'products_deleted': 0},
                     'snapshot_sha256': runner.sha256(self.before),
                     'files': {'products.csv': runner.sha256(self.stage / 'products.csv')},
                     'actions': [{'action': 'native-import', 'file': 'products.csv', 'rows': 1,
                                  'preserve_existing_stock': True, 'validate_before_apply': True}]}
        self.save_plan()
        # This is a filesystem-only command-runner fixture, never a Magento store.
        patcher = patch.dict(runner.TARGETS, {str(self.root): ('/fixture', ['fixture-php'])})
        patcher.start()
        self.addCleanup(patcher.stop)

    def save_plan(self):
        (self.stage / 'deployment.json').write_text(json.dumps(self.plan))
        self.pin = runner.sha256(self.stage / 'deployment.json')

    def execute(self, **kwargs):
        return runner.execute(self.root, self.stage, self.pin, self.root / 'receipt',
                              self.before, self.snapshot, **kwargs)

    def test_dry_run_never_invokes_store_commands(self):
        with patch.object(runner.subprocess, 'run') as run:
            self.assertEqual(self.execute()['state'], 'prepared; no store commands run')
            run.assert_not_called()
        self.assertFalse((self.root / 'receipt').exists())

    def test_missing_backup_blocks_before_any_store_command(self):
        with patch.object(runner.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'backups and an exact inverse'):
                self.execute(apply=True)
            run.assert_not_called()

    def test_stock_preservation_cannot_be_disabled(self):
        self.plan['actions'][0]['preserve_existing_stock'] = False
        self.save_plan()
        with self.assertRaisesRegex(ValueError, 'must preserve stock'):
            self.execute()

    def test_product_deletion_is_outside_the_native_import_plan(self):
        self.plan['delta']['products_deleted'] = 1
        self.save_plan()
        with self.assertRaisesRegex(ValueError, 'Unexpected catalog mutation scope'):
            self.execute()

    def test_changed_batch_cannot_be_imported(self):
        (self.stage / 'products.csv').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Deployment file changed'):
            self.execute()

    def test_remote_media_recovery_requires_full_acceptance_and_replays_no_metadata(self):
        (self.stage/'0001-media.csv').write_text('sku\nWANDS-SYN-EXAMPLE\n')
        self.plan.update(target_root='/var/www/html',reconciliation={'schema':1,'candidate_sha256':runner.CANDIDATE_SHA256,'original_before_wands_products':53844,'before_wands_products':107688,'already_imported_skus':['WANDS-SYN-'+str(i) for i in range(53844)],'source_pins':{}},media_tail_reconciliation={'database_acceptance':{'passed':True,'wands_products':107688},'completed_media_rows':107454})
        self.plan['delta'].update(before_wands_products=107688,product_inserts=0)
        self.plan['actions'][0].update(file='0001-media.csv')
        self.plan['files']={'0001-media.csv':runner.sha256(self.stage/'0001-media.csv')};self.save_plan()
        with patch.dict(runner.TARGETS,{str(self.root):('/var/www/html',['fixture-php'])}):
            self.assertEqual(self.execute()['native_batches'],1)
            self.plan['actions'][0]['file']='products.csv';self.plan['files']['products.csv']=runner.sha256(self.stage/'products.csv');self.save_plan()
            with self.assertRaisesRegex(ValueError,'Media tail'):self.execute()

    def test_validation_failure_stops_before_native_import(self):
        calls = []
        def fake_run(argv, **kwargs):
            calls.append(argv)
            if '--root=/fixture' in argv:
                kwargs['stdout'].write(self.before.read_bytes())
                return SimpleNamespace(returncode=0)
            self.assertIn('--validate-only', argv)
            return SimpleNamespace(returncode=1)
        with patch.object(runner, 'verify_backups', return_value={}), \
                patch.object(runner.subprocess, 'run', side_effect=fake_run):
            with self.assertRaisesRegex(RuntimeError, 'Native import stage failed'):
                self.execute(apply=True, backups=self.root / 'backup-receipt.json')
        self.assertEqual(len(calls), 2)
        state = json.loads((self.root / 'receipt/state.json').read_text())
        self.assertEqual(state['index'], 0)
        self.assertIn('failed', state['state'])

    def test_changed_destination_stops_before_validation_or_import(self):
        def snapshot(argv, **kwargs):
            kwargs['stdout'].write(b'{"schema":2,"fixture":"changed"}')
            return SimpleNamespace(returncode=0)
        with patch.object(runner, 'verify_backups', return_value={}), \
                patch.object(runner.subprocess, 'run', side_effect=snapshot) as run:
            with self.assertRaisesRegex(ValueError, 'Destination changed'):
                self.execute(apply=True, backups=self.root / 'backup-receipt.json')
            self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()

class NativeJsonValidationTest(NativeImportBoundaryTest):
    def test_zero_exit_with_native_validation_errors_stops_before_import(self):
        calls=[]
        def fake_run(argv,**kwargs):
            calls.append(argv)
            if '--root=/fixture' in argv:kwargs['stdout'].write(self.before.read_bytes())
            elif '--validate-only' in argv:kwargs['stdout'].write(b'{"validated_only":true,"errors":6,"invalid_rows":6}')
            else:self.fail('Import ran despite reported validation errors')
            return SimpleNamespace(returncode=0)
        with patch.object(runner,'verify_backups',return_value={}),patch.object(runner.subprocess,'run',side_effect=fake_run):
            with self.assertRaisesRegex(RuntimeError,'Native import stage failed'):self.execute(apply=True,backups=self.root/'backups.json')
        self.assertEqual(len(calls),2)
