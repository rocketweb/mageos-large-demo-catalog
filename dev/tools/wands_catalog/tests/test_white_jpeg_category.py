import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import white_jpeg_category_policy as policy
import white_jpeg_category_run as run


class CategoryPolicyTest(unittest.TestCase):
    def setUp(self):
        self.row = {'n': 1, 'file': 'a.jpg', 'source_sha256': 'source', 'output_sha256': 'output', 'output_file': 'output.jpg'}
        self.meta = {'classes': ['Tables'], 'categories': ['WANDS Catalog/Furniture/Tables']}
        self.metrics = {'backdrop_fit_p90': 4, 'border_edge_fraction': 0, 'white_border': 1,
            'visible_fraction': .3, 'retained_pixel_agreement': .995, 'native_edge_retention': .99,
            'dimensions': [768, 768], 'risk_regions': []}
        self.review = {'background': 'studio', 'white_background': True, 'major_product_damage': False,
                       'confidence': .9, 'reason': 'Minor edge change, white backdrop.'}

    def test_plain_product_passes_fast_checks(self):
        self.assertEqual(policy.route(self.row, self.metrics, self.meta)[0], 'white')

    def test_room_bundle_original_even_with_perfect_metrics(self):
        self.meta['classes'] = ['Room Bundle']
        self.assertEqual(policy.route(self.row, self.metrics, self.meta)[0], 'original')

    def test_shared_image_in_room_bundle_is_excluded(self):
        self.meta['categories'].append('WANDS Catalog/Room Bundles/Bedroom')
        self.assertEqual(policy.route(self.row, self.metrics, self.meta)[0], 'original')

    def test_bedding_requires_review(self):
        self.meta['classes'] = ['Bedding Sets']
        self.assertEqual(policy.route(self.row, self.metrics, self.meta)[0], 'review')

    def test_mirror_requires_review(self):
        self.meta['classes'] = ['Wall Mirrors']
        self.assertEqual(policy.route(self.row, self.metrics, self.meta)[0], 'review')

    def test_either_background_flag_requires_review(self):
        for key, value in [('backdrop_fit_p90', 17), ('border_edge_fraction', .05)]:
            with self.subTest(key=key):
                m = {**self.metrics, key: value}
                self.assertEqual(policy.route(self.row, m, self.meta)[0], 'review')

    def test_minor_contour_or_corner_change_is_accepted(self):
        self.metrics['risk_regions'] = [{'kind': 'new_cutout_edge', 'pixels': 126}, {'kind': 'enclosed_whitened_area', 'pixels': 226}]
        self.assertEqual(policy.route(self.row, self.metrics, self.meta)[0], 'white')

    def test_large_panel_and_canvas_changes_require_review(self):
        for kind, pixels in [('enclosed_whitened_area', 1144), ('new_cutout_edge', 396), ('erased_dark_area', 23078), ('missing_source_edge', 7795)]:
            with self.subTest(kind=kind):
                self.metrics['risk_regions'] = [{'kind': kind, 'pixels': pixels}]
                self.assertEqual(policy.route(self.row, self.metrics, self.meta)[0], 'review')

    def test_nearly_empty_and_missing_candidates_keep_original(self):
        self.assertEqual(policy.route({**self.row, 'output_file': None}, None, self.meta)[0], 'original')
        self.metrics['visible_fraction'] = .001
        self.assertEqual(policy.route(self.row, self.metrics, self.meta)[0], 'original')

    def test_review_accepts_minor_changes_at_ninety_percent(self):
        self.assertEqual(policy.choose_review(self.review)[0], 'white')

    def test_scene_uncertain_and_major_loss_are_rejected(self):
        for change in ({'background': 'scene'}, {'background': 'uncertain'}, {'major_product_damage': True},
                       {'major_product_damage': None}, {'white_background': None}, {'confidence': .89}):
            with self.subTest(change=change):
                self.assertEqual(policy.choose_review({**self.review, **change})[0], 'original')


class CategoryEvidenceTest(unittest.TestCase):
    def setUp(self):
        CategoryPolicyTest.setUp(self)
        self.directory = tempfile.TemporaryDirectory()
        self.audit = Path(self.directory.name)
        self.db = run.connect(self.audit)
        self.db.execute('CREATE TABLE images(n INTEGER PRIMARY KEY,file TEXT,row_json TEXT,decision TEXT,reason TEXT)')
        self.db.execute('INSERT INTO images VALUES(1,?,?,NULL,NULL)', ('a.jpg', json.dumps(self.row)))
        self.db.execute('INSERT INTO category_features VALUES(?,?,?,?,?)', ('a.jpg', 'source', 'output', run.NATIVE_IDENTITY, json.dumps(self.metrics)))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.directory.cleanup()

    def test_export_validates_actual_fast_evidence(self):
        run.save(self.db, self.row, 'white', 'fast_pass', 'fast', self.metrics)
        run.validate_white(self.db, self.row, self.meta, None)

    def test_changed_candidate_cannot_reuse_proof(self):
        run.save(self.db, self.row, 'white', 'fast_pass', 'fast', self.metrics)
        with self.assertRaisesRegex(ValueError, 'matching'):
            run.validate_white(self.db, {**self.row, 'output_sha256': 'changed'}, self.meta, None)

    def test_changed_metrics_cannot_reuse_proof(self):
        run.save(self.db, self.row, 'white', 'fast_pass', 'fast', self.metrics)
        self.db.execute("UPDATE category_features SET features='{}'")
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            run.validate_white(self.db, self.row, self.meta, None)

    def test_room_bundle_cannot_be_exported_as_white(self):
        run.save(self.db, self.row, 'white', 'fast_pass', 'fast', self.metrics)
        with self.assertRaisesRegex(ValueError, 'Room Bundle'):
            run.validate_white(self.db, self.row, {'classes': ['Room Bundle']}, None)

    def test_duplicate_decision_cannot_overwrite_negative(self):
        run.save(self.db, self.row, 'original', 'scene', 'context_review', self.metrics, {**self.review, 'background': 'scene'})
        with self.assertRaises(sqlite3.IntegrityError):
            run.save(self.db, self.row, 'white', 'retry', 'fast', self.metrics)
        self.assertEqual(self.db.execute('SELECT decision FROM images').fetchone()[0], 'original')

    def test_review_outage_drains_and_preserves_negative_decision(self):
        from image_review import ReviewServiceUnavailable
        second = {**self.row, 'n': 2, 'file': 'b.jpg'}
        self.db.execute('INSERT INTO images VALUES(2,?,?,NULL,NULL)', ('b.jpg', json.dumps(second)))
        self.db.execute('INSERT INTO category_features VALUES(?,?,?,?,?)', ('b.jpg', 'source', 'output', run.NATIVE_IDENTITY, json.dumps(self.metrics)))
        self.db.commit()
        (self.audit/'image-categories.json').write_text(json.dumps({'a.jpg': self.meta, 'b.jpg': self.meta}))
        def result(job, audit, row, metrics, meta):
            if row['file'] == 'b.jpg': raise ReviewServiceUnavailable([])
            return {**self.review, 'major_product_damage': True}, {'model': policy.MODEL, 'policy': policy.identity()}
        with patch.object(run, 'request_pair', side_effect=result):
            with self.assertRaises(ReviewServiceUnavailable): run.review_pending(self.audit, self.audit, self.db)
        self.assertEqual(self.db.execute("SELECT decision FROM images WHERE file='a.jpg'").fetchone()[0], 'original')
        self.assertIsNone(self.db.execute("SELECT decision FROM images WHERE file='b.jpg'").fetchone()[0])

    def test_large_region_damage_vetoes_a_positive_primary_review(self):
        import white_jpeg_region_review as regions
        m = {**self.metrics, 'risk_regions': [{'kind': 'erased_dark_area', 'pixels': 23078,
            'crop': [0, 0, 100, 100], 'box': [0, 0, 100, 100]}]}
        self.db.execute('UPDATE category_features SET features=?', (json.dumps(m),)); self.db.commit()
        (self.audit/'image-categories.json').write_text(json.dumps({'a.jpg': self.meta}))
        details = {'model': policy.MODEL, 'policy': policy.identity(),
            'context_identity': run.context_identity(self.audit) if hasattr(run, 'context_identity') else None,
            'focus': {'identity': regions.identity(policy.MODEL), 'source_sha256': 'source', 'output_sha256': 'output',
                'reviews': [{'crop': [0, 0, 100, 100], 'review': {'verdict': 'product_damage', 'confidence': .95, 'reason': 'Canvas erased.'}}]}}
        with patch.object(run, 'request_pair', return_value=(self.review, details)):
            run.review_pending(self.audit, self.audit, self.db)
        self.assertEqual(self.db.execute('SELECT decision FROM images').fetchone()[0], 'original')

    def test_export_replays_valid_context_evidence(self):
        details = {'model': policy.MODEL, 'policy': policy.identity(), 'context_identity': run.context_identity(self.audit)}
        run.save(self.db, self.row, 'white', 'review_pass', 'context_review', self.metrics, self.review, details)
        run.validate_white(self.db, self.row, {'classes': ['Bedding Sets'], 'categories': []}, None)

    def test_export_replays_major_region_votes(self):
        import white_jpeg_region_review as regions
        m = {**self.metrics, 'risk_regions': [{'kind': 'erased_dark_area', 'pixels': 23078, 'crop': [0, 0, 100, 100]}]}
        self.db.execute('UPDATE category_features SET features=?', (json.dumps(m),)); self.db.commit()
        details = {'model': policy.MODEL, 'policy': policy.identity(), 'context_identity': run.context_identity(self.audit),
            'focus': {'identity': regions.identity(policy.MODEL), 'source_sha256': 'source', 'output_sha256': 'output',
                      'reviews': [{'crop': [0, 0, 100, 100], 'review': {'verdict': 'safe_background', 'confidence': .95, 'reason': 'Cast shadow only.'}}]}}
        run.save(self.db, self.row, 'white', 'review_pass', 'context_review', m, self.review, details)
        run.validate_white(self.db, self.row, self.meta, None)

    def test_export_cannot_ignore_a_negative_region_vote(self):
        import white_jpeg_region_review as regions
        m = {**self.metrics, 'risk_regions': [{'kind': 'erased_dark_area', 'pixels': 23078, 'crop': [0, 0, 100, 100]}]}
        self.db.execute('UPDATE category_features SET features=?', (json.dumps(m),)); self.db.commit()
        details = {'model': policy.MODEL, 'policy': policy.identity(), 'context_identity': run.context_identity(self.audit),
            'focus': {'identity': regions.identity(policy.MODEL), 'source_sha256': 'source', 'output_sha256': 'output',
                      'reviews': [{'crop': [0, 0, 100, 100], 'review': {'verdict': 'product_damage', 'confidence': .95, 'reason': 'Canvas erased.'}}]}}
        run.save(self.db, self.row, 'white', 'corrupt_positive', 'context_review', m, self.review, details)
        with self.assertRaisesRegex(ValueError, 'does not pass'):
            run.validate_white(self.db, self.row, self.meta, None)

    def test_unqualified_export_report_does_not_suppress_deadline_retry(self):
        (self.audit/'config.json').write_text(json.dumps({'freeze_at': 0}))
        destination = self.audit/'selections/deadline'
        destination.mkdir(parents=True)
        (destination/'verification.json').write_text(json.dumps({'state': 'complete'}))
        with patch.object(run, 'spawn', return_value={'pid': 99999}) as spawn:
            run.maybe_deadline_export(self.audit)
        spawn.assert_called_once()

    def test_integrity_failure_requires_attention_before_retry(self):
        (self.audit/'config.json').write_text(json.dumps({'freeze_at': 0}))
        (self.audit/'export-status.json').write_text(json.dumps({'state': 'needs_attention'}))
        with patch.object(run, 'spawn', side_effect=AssertionError('Must not restart failed integrity verification')):
            run.maybe_deadline_export(self.audit)


if __name__ == '__main__': unittest.main()
