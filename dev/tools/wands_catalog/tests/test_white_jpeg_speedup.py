import itertools
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import white_jpeg_category_run as run
import white_jpeg_dark_fast as dark


class SpeedupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.job = Path(self.tmp.name)
        self.audit = self.job/'audit'
        self.audit.mkdir()
        self.source = self.job/'originals'
        self.source.mkdir()
        (self.job/'manifest.json').write_text(json.dumps({'originals': str(self.source)}))
        self.candidate = self.job/'candidate.jpg'
        a = Image.new('RGB', (256,256), (240,235,225))
        b = Image.new('RGB', a.size, 'white')
        for im in [a,b]:
            ImageDraw.Draw(im).rectangle((55,35,200,225), fill=(20,30,50))
        a.save(self.source/'a.jpg', quality=95)
        b.save(self.candidate, quality=90)
        self.row = {'n':1, 'file':'a.jpg', 'source_sha256':run.sha(self.source/'a.jpg'),
                    'output_sha256':run.sha(self.candidate), 'output_file':'candidate.jpg',
                    'output_path':str(self.candidate)}
        self.meta = {'classes':['Chairs'], 'categories':[], 'skus':['chair']}
        self.metrics = {'backdrop_fit_p90':3, 'border_edge_fraction':0, 'white_border':1,
            'visible_fraction':.4, 'retained_pixel_agreement':.98, 'native_edge_retention':.99,
            'border_median_rgb':[240,235,225], 'dimensions':[256,256], 'risk_regions':[]}
        (self.audit/'image-categories.json').write_text(json.dumps({'a.jpg':self.meta}))
        glass = self.audit/'glass-outline-audit'
        glass.mkdir()
        (glass/'scope.json').write_text(json.dumps({'images':[]}))
        self.proofs = self.job/'pilot'
        self.proofs.mkdir()
        (self.proofs/'manifest.json').write_text('{}')
        (self.proofs/'dark-pilot-results.json').write_text('[]')
        proof = {'passed':True, 'dark_identity':dark.identity(), 'cases':537, 'known_bad':37,
                 'unsafe_approvals':[], 'metadata_sha256':run.sha(self.audit/'image-categories.json'),
                 'manifest_sha256':run.sha(self.proofs/'manifest.json'),
                 'results_sha256':run.sha(self.proofs/'dark-pilot-results.json')}
        (self.proofs/'dark-validation.json').write_text(json.dumps(proof))
        (self.audit/'config.json').write_text(json.dumps({'dark_fast_checks':True,
            'native_fast_holds':True, 'speedup_validation_root':str(self.proofs)}))
        self.db = run.connect(self.audit)
        self.db.executescript('''CREATE TABLE images(n INTEGER PRIMARY KEY,file TEXT UNIQUE,
            row_json TEXT,decision TEXT,reason TEXT);
            CREATE TABLE glass_outline_checks(file TEXT,verdict TEXT);''')
        self.db.execute('INSERT INTO images VALUES(1,?,?,NULL,NULL)', ('a.jpg',json.dumps(self.row)))
        self.db.execute('INSERT INTO category_features VALUES(?,?,?,?,?)',
            ('a.jpg',self.row['source_sha256'],self.row['output_sha256'],run.NATIVE_IDENTITY,json.dumps(self.metrics)))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_real_jpeg_approval_and_export_replay_reject_changed_bytes(self):
        run.register_speedup(self.db,self.audit)
        run.speedup_fast_pass(self.job,self.audit,self.db)
        self.assertEqual(self.db.execute('SELECT decision FROM images').fetchone()[0],'white')
        self.assertEqual(self.db.execute('SELECT method FROM category_evidence').fetchone()[0],'fast_dark')
        run.validate_white(self.db,self.row,self.meta,None)
        self.candidate.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'bytes changed'):
            run.validate_white(self.db,self.row,self.meta,None)

    def test_changed_pilot_cannot_be_registered(self):
        (self.proofs/'dark-pilot-results.json').write_text('["changed"]')
        with self.assertRaisesRegex(ValueError,'pilot artifacts changed'):
            run.register_speedup(self.db,self.audit)

    def test_failed_combined_protocol_cannot_be_enabled(self):
        (self.audit/'config.json').write_text('{"combined_reviews":true}')
        with self.assertRaisesRegex(ValueError,'failed its pilot'):
            run.register_speedup(self.db,self.audit)

    def test_qualification_is_immutable(self):
        run.register_speedup(self.db,self.audit)
        for sql in ["UPDATE speedup_qualifications SET validation_json='{}'",'DELETE FROM speedup_qualifications']:
            with self.assertRaisesRegex(sqlite3.IntegrityError,'immutable'):
                self.db.execute(sql)

    def test_existing_machine_and_human_originals_are_never_reopened(self):
        run.register_speedup(self.db,self.audit)
        run.save(self.db,self.row,'original','major_damage','context_review',self.metrics)
        before = list(self.db.execute('SELECT * FROM images'))
        run.speedup_fast_pass(self.job,self.audit,self.db)
        self.assertEqual([tuple(r)for r in before],[tuple(r)for r in self.db.execute('SELECT * FROM images')])
        self.assertEqual(self.db.execute('SELECT count(*) FROM category_evidence').fetchone()[0],1)
        run.human.install(self.db)
        self.db.execute('INSERT INTO human_selections VALUES(?,?,?,?,?,?,?)',
            ('a.jpg','original',self.row['source_sha256'],self.row['output_sha256'],'F001','F001','human-plan'))
        self.db.commit()
        run.speedup_fast_pass(self.job,self.audit,self.db)
        self.assertEqual(self.db.execute('SELECT decision FROM images').fetchone()[0],'original')

    def test_held_glass_cannot_use_the_dark_fast_path(self):
        run.register_speedup(self.db,self.audit)
        (self.audit/'glass-outline-audit/scope.json').write_text('{"images":["a.jpg"]}')
        self.db.execute("INSERT INTO glass_outline_checks VALUES('a.jpg','uncertain')")
        self.db.commit()
        run.speedup_fast_pass(self.job,self.audit,self.db)
        self.assertIsNone(self.db.execute('SELECT decision FROM images').fetchone()[0])

    def test_direct_originals_equal_the_existing_reviewer_for_every_primary_verdict(self):
        cases = [dict(self.metrics,retained_pixel_agreement=.85),
                 dict(self.metrics,native_edge_retention=.7),
                 dict(self.metrics,risk_regions=[{'kind':'erased_dark_area','pixels':1000,
                     'crop':[0,0,100,100]} for _ in range(9)])]
        verdicts = itertools.product(['studio','scene','uncertain'],[True,False,None],
                                     [True,False,None],[.89,.95])
        verdicts = list(verdicts)
        for m in cases:
            self.assertIsNotNone(run.native_original_reason(m,self.meta))
            for background,white,damage,confidence in verdicts:
                review = {'background':background,'white_background':white,
                    'major_product_damage':damage,'confidence':confidence,'reason':'Control.'}
                with patch.object(run.native(self.audit).regions,'request',side_effect=AssertionError('No vision needed')):
                    reviewed,details = run.complete_review(self.job,self.audit,self.row,m,self.meta,review,{})
                    self.assertEqual(run.context_decision(self.audit,self.row,m,self.meta,reviewed,details)[0],'original')
        self.assertIsNone(run.native_original_reason(self.metrics,self.meta))


if __name__ == '__main__':unittest.main()
