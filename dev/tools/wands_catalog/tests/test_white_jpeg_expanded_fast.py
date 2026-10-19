import sys
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import white_jpeg_expanded_fast as fast


class ExpandedFastTest(unittest.TestCase):
    def setUp(self):
        self.row = {'output_file': 'white.jpg'}
        self.meta = {'classes': ['Accent Pillows'], 'categories': []}
        self.metrics = {'backdrop_fit_p90': 4, 'border_edge_fraction': 0,
            'white_border': 1, 'visible_fraction': .3, 'retained_pixel_agreement': .99,
            'native_edge_retention': .9, 'dimensions': [768, 768],
            'risk_regions': [{'kind': 'missing_source_edge', 'pixels': 2000}]}
        self.safe = {'source_chroma_loss_fraction': .01, 'envelope_foreground_loss_fraction': .03}

    def test_large_printed_product_erasure_is_not_recovered(self):
        # Measured spot-check cases: printed pillow and two erased art canvases.
        for color_loss, inside_loss in [(.376, .004), (.721, .08), (.682, .08)]:
            with self.subTest(color_loss=color_loss):
                extra = {'source_chroma_loss_fraction': color_loss,
                         'envelope_foreground_loss_fraction': inside_loss}
                self.assertEqual(fast.route(self.row, self.metrics, self.meta, extra)[0], 'review')

    def test_erased_neutral_panel_is_not_recovered(self):
        extra = {**self.safe, 'envelope_foreground_loss_fraction': .4}
        self.assertEqual(fast.route(self.row, self.metrics, self.meta, extra)[0], 'review')

    def test_new_fast_approval_requires_material_measurements(self):
        self.assertEqual(fast.route(self.row, self.metrics, self.meta)[0], 'measure')

    def test_local_edge_flags_with_preserved_material_can_clear(self):
        self.assertEqual(fast.route(self.row, self.metrics, self.meta, self.safe)[0], 'white')

    def test_excluded_categories_and_backgrounds_stay_out(self):
        for cls in ['Room Bundle', 'Bedding Sets', 'Wall Mirrors']:
            self.assertNotEqual(fast.route(self.row, self.metrics, {'classes': [cls]}, self.safe)[0], 'white')
        for key, val in [('backdrop_fit_p90', 25), ('border_edge_fraction', .1),
                         ('white_border', .9), ('retained_pixel_agreement', .8), ('native_edge_retention', .5)]:
            self.assertEqual(fast.route(self.row, {**self.metrics, key: val}, self.meta, self.safe)[0], 'review')

    def test_large_holes_and_removed_structure_still_need_review(self):
        for kind in ['enclosed_whitened_area', 'erased_dark_area', 'missing_source_edge', 'new_cutout_edge']:
            m = {**self.metrics, 'risk_regions': [{'kind': kind, 'pixels': 30000}]}
            self.assertEqual(fast.route(self.row, m, self.meta, self.safe)[0], 'review')

    def test_pixels_detect_whole_colored_surface_erasure(self):
        from PIL import Image, ImageDraw
        original = Image.new('RGB', (256, 256), (245, 237, 220))
        ImageDraw.Draw(original).rectangle((45, 30, 210, 225), fill=(30, 120, 40))
        intact = Image.new('RGB', (256, 256), 'white')
        ImageDraw.Draw(intact).rectangle((45, 30, 210, 225), fill=(30, 120, 40))
        damaged = intact.copy()
        ImageDraw.Draw(damaged).rectangle((120, 30, 210, 225), fill='white')
        good = fast.features(original, intact)
        bad = fast.features(original, damaged)
        self.assertLess(good['source_chroma_loss_fraction'], .01)
        self.assertGreater(bad['source_chroma_loss_fraction'], .5)
        self.assertEqual(fast.route(self.row, self.metrics, self.meta, good)[0], 'white')
        self.assertEqual(fast.route(self.row, self.metrics, self.meta, bad)[0], 'review')


class ExpandedEvidenceTest(unittest.TestCase):
    def setUp(self):
        import white_jpeg_category_run as run
        self.run = run
        ExpandedFastTest.setUp(self)
        self.directory = tempfile.TemporaryDirectory()
        self.audit = Path(self.directory.name)
        self.db = run.connect(self.audit)
        self.row.update(n=1, file='a.jpg', source_sha256='source', output_sha256='output')
        self.db.execute('CREATE TABLE images(n INTEGER PRIMARY KEY,file TEXT UNIQUE,row_json TEXT,decision TEXT,reason TEXT)')
        self.db.execute('INSERT INTO images VALUES(1,?,?,NULL,NULL)', ('a.jpg', json.dumps(self.row)))
        self.db.execute('INSERT INTO category_features VALUES(?,?,?,?,?)',
                        ('a.jpg', 'source', 'output', run.NATIVE_IDENTITY, json.dumps(self.metrics)))
        self.db.execute('INSERT INTO expanded_features VALUES(?,?,?,?,?)',
                        ('a.jpg', 'source', 'output', fast.measurement_identity(), json.dumps(self.safe)))
        self.db.commit()
        (self.audit/'config.json').write_text(json.dumps({'expanded_fast_checks': True}))
        (self.audit/'image-categories.json').write_text(json.dumps({'a.jpg': self.meta}))

    def tearDown(self):
        self.db.close(); self.directory.cleanup()

    def test_pending_batch_and_export_use_both_actual_protocols(self):
        self.run.fast_pass(self.audit, self.db)
        self.assertEqual(self.db.execute('SELECT decision FROM images').fetchone()[0], 'white')
        self.assertEqual(self.db.execute('SELECT method FROM category_evidence').fetchone()[0], 'fast_expanded')
        self.run.validate_white(self.db, self.row, self.meta, None)

    def test_terminal_negative_is_preserved(self):
        self.db.execute("UPDATE images SET decision='original',reason='scene'"); self.db.commit()
        self.run.fast_pass(self.audit, self.db)
        self.assertEqual(self.db.execute('SELECT decision FROM images').fetchone()[0], 'original')
        self.assertEqual(self.db.execute('SELECT count(*) FROM category_evidence').fetchone()[0], 0)

    def test_changed_supplemental_bytes_or_protocol_cannot_reuse_approval(self):
        self.run.fast_pass(self.audit, self.db)
        for column, value in [('source_sha256', 'different'), ('identity', 'stale')]:
            self.db.execute('UPDATE expanded_features SET '+column+'=?', (value,))
            with self.assertRaisesRegex(ValueError, 'different bytes or protocol'):
                self.run.validate_white(self.db, self.row, self.meta, None)
            self.db.rollback()
        self.db.execute('UPDATE expanded_features SET features=?', (json.dumps({**self.safe, 'source_chroma_loss_fraction': .8}),))
        with self.assertRaisesRegex(ValueError, 'does not pass'):
            self.run.validate_white(self.db, self.row, self.meta, None)


if __name__ == '__main__': unittest.main()
