import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import white_jpeg_human_approval as human
import white_jpeg_recreated_approval as recreated
import test_white_jpeg_human_approval as fixtures


class RecreatedApprovalTest(unittest.TestCase):
    def setUp(self):
        fixtures.HumanApprovalTest.setUp(self)
        self.scope['approved_batches_with_exceptions']['F001'] = [i['id'] for i in self.manifest['items'][:3]]
        self.prior_plan = human.make_plan(self.path, human.sha(self.path), self.scope)
        human.apply(self.db, self.prior_plan, self.meta)
        images = []
        for n, prior in enumerate(self.manifest['items'][:3], 1):
            replacement = self.root / f'recreated-{n}.jpg'
            replacement.write_bytes(f'recreated image {n}'.encode())
            images.append({'id': f'RE{n:03d}', 'batch': 'R01', 'previous_review_id': prior['id'],
                           'original_path': prior['original_path'], 'source_sha256': prior['source_sha256'],
                           'rejected_url': Path(prior['candidate_path']).as_uri(),
                           'replacement_path': str(replacement) if n != 2 else None,
                           'replacement_sha256': human.sha(replacement) if n != 2 else None,
                           'state': 'awaiting_review' if n != 2 else 'needs_attention',
                           'name': prior['name'], 'skus': prior['skus']})
        self.recreated_manifest = {'run_id': 'recreated-fixture', 'state': 'ready_for_review_with_exceptions', 'items': images}
        self.recreated_path = self.root / 'recreated-manifest.json'
        self.recreated_path.write_text(json.dumps(self.recreated_manifest))
        self.recreated_scope = {'run_id': 'recreated-fixture', 'manifest_sha256': human.sha(self.recreated_path),
                                'deploy': False, 'approved_batches_with_exceptions': {'R01': ['RE002']}}
        self.plan = recreated.make_plan(self.recreated_path, human.sha(self.recreated_path), self.recreated_scope, self.db)

    def test_exact_supersession_uses_new_bytes_export_validator_and_scoped_inverse(self):
        before = [tuple(r) for r in self.db.execute('SELECT * FROM images ORDER BY file')]
        receipt = recreated.apply(self.db, self.plan, self.meta)
        self.assertFalse(receipt['idempotent'])
        self.assertEqual(recreated.verify(self.db, self.plan), {'white': 2, 'original': 1})
        self.assertTrue(recreated.apply(self.db, self.plan, self.meta)['idempotent'])
        row = json.loads(self.db.execute("SELECT row_json FROM images WHERE file='1.jpg'").fetchone()[0])
        self.assertEqual(row['output_path'], str(self.root / 'recreated-1.jpg'))
        self.assertEqual(row['output_file'], human.sha(self.root / 'recreated-1.jpg') + '.jpg')
        human.validate_white(self.db, row, self.meta['1.jpg'])
        self.assertEqual(tuple(self.db.execute("SELECT decision,reason FROM images WHERE file='4.jpg'").fetchone()), (None, 'pending'))
        self.db.execute("UPDATE images SET decision='original',reason='stale_worker' WHERE file='1.jpg'")
        self.db.execute("UPDATE images SET decision='white',reason='stale_worker' WHERE file='2.jpg'")
        self.db.commit();recreated.verify(self.db, self.plan)
        recreated.rollback(self.db, self.plan)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM images ORDER BY file')], before)
        human.verify(self.db, self.prior_plan)
        self.assertEqual(self.db.execute('SELECT count(*) FROM human_approval_requests').fetchone()[0], 2)

    def test_blocked_replacement_cannot_be_approved(self):
        self.recreated_scope['approved_batches_with_exceptions']['R01'] = []
        with self.assertRaisesRegex(ValueError, 'Unavailable replacement'):
            recreated.make_plan(self.recreated_path, human.sha(self.recreated_path), self.recreated_scope, self.db)

    def test_manifest_and_prior_directive_drift_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'manifest hash'):
            recreated.make_plan(self.recreated_path, 'wrong', self.recreated_scope, self.db)
        self.db.execute("UPDATE human_selections SET item_id='different' WHERE file='3.jpg'");self.db.commit()
        with self.assertRaisesRegex(ValueError, 'Prior selection changed'):
            recreated.apply(self.db, self.plan, self.meta)
        self.assertEqual(self.db.execute("SELECT count(*) FROM images WHERE decision='white'").fetchone()[0], 0)

    def test_replacement_byte_drift_aborts_entire_transaction(self):
        (self.root / 'recreated-3.jpg').write_bytes(b'changed after approval')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            recreated.apply(self.db, self.plan, self.meta)
        human.verify(self.db, self.prior_plan)
        self.assertEqual(self.db.execute('SELECT count(*) FROM human_approval_requests').fetchone()[0], 1)

    def test_held_glass_remains_excluded(self):
        self.db.execute("INSERT INTO glass_outline_checks VALUES('3.jpg','lost')");self.db.commit()
        with self.assertRaisesRegex(ValueError, 'glass outline'):
            recreated.apply(self.db, self.plan, self.meta)
        human.verify(self.db, self.prior_plan)

    def test_room_bundle_remains_excluded(self):
        self.meta['3.jpg']['classes'] = ['Room Bundle']
        with self.assertRaisesRegex(ValueError, 'Room Bundle'):
            recreated.apply(self.db, self.plan, self.meta)
        human.verify(self.db, self.prior_plan)


if __name__ == '__main__':
    unittest.main()
