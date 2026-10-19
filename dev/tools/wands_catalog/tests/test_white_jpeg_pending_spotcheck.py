from datetime import datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from PIL import Image,ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import white_jpeg_category_run as catalog
import white_jpeg_human_approval as human
import white_jpeg_pending_spotcheck as review


class PendingReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.job=Path(self.tmp.name);self.audit=self.job/'audit-expanded-fast-20261018';self.audit.mkdir()
        originals=self.job/'originals';originals.mkdir()
        (self.job/'manifest.json').write_text(json.dumps({'originals':str(originals)}))
        self.source=self.job/'source.jpg';self.candidate=self.job/'candidate.jpg'
        for path,bg in [(self.source,(240,235,225)),(self.candidate,'white')]:
            image=Image.new('RGB',(64,64),bg);ImageDraw.Draw(image).rectangle((12,8,52,55),fill=(30,40,50));image.save(path,quality=90)
        self.db=catalog.connect(self.audit);self.addCleanup(self.db.close)
        self.db.executescript('''CREATE TABLE images(n INTEGER PRIMARY KEY,file TEXT UNIQUE,row_json TEXT,decision TEXT,reason TEXT);
            CREATE TABLE glass_outline_checks(file TEXT PRIMARY KEY,verdict TEXT);''')
        human.install(self.db)
        self.cutoff='2026-10-19T16:30:28.795822-04:00';stamp=datetime.fromisoformat(self.cutoff).timestamp()
        self.meta={}
        m={'border_median_rgb':[240,235,225],'backdrop_fit_p90':3,'retained_pixel_agreement':.98,'native_edge_retention':.99}
        for n in range(206):
            filename=f'{n:03d}.jpg';shutil.copy2(self.source,originals/filename)
            row={'n':n,'file':filename,'source_sha256':human.sha(self.source),
                 'output_file':'candidate.jpg','output_path':str(self.candidate),'output_sha256':human.sha(self.candidate)}
            decision='white'if n in (1,205)else'original'if n==2 else None
            self.db.execute('INSERT INTO images VALUES(?,?,?,?,?)',(n,filename,json.dumps(row),decision,'cutout_risk'))
            self.db.execute('INSERT INTO category_features VALUES(?,?,?,?,?)',(filename,row['source_sha256'],row['output_sha256'],catalog.NATIVE_IDENTITY,json.dumps(m)))
            if decision:
                self.db.execute('INSERT INTO category_evidence VALUES(?,?,?,?,?,?,?,?,?)',
                    (filename,catalog.policy.identity(),'context_review',row['source_sha256'],row['output_sha256'],'hash','null','{}',stamp-1 if n==205 else stamp+n))
            self.meta[filename]={'name':f'Chair {n:03d}','classes':['Chairs'],'categories':[],'skus':[f'SKU-{n}']}
        self.db.execute("INSERT INTO glass_outline_checks VALUES('000.jpg','lost')");self.db.commit()
        (self.audit/'image-categories.json').write_text(json.dumps(self.meta))

    def test_exact_checkpoint_scope_batches_and_existing_approval_pipeline(self):
        output=self.job/'review'
        receipt=review.build(self.job,output,self.cutoff,205)
        self.assertEqual(receipt['batch_sizes'],[100,100,5])
        manifest=json.loads((output/'manifest.json').read_text())
        self.assertEqual(len({x['file']for x in manifest['items']}),205)
        self.assertNotIn('205.jpg',{x['file']for x in manifest['items']})
        self.assertEqual(receipt['counts'],{'previously_original':1,'pending':203,'newly_white':1,'locked_original':1})
        self.assertEqual(len(list((output/'thumbs').glob('*.jpg'))),410)
        scope={'run_id':'review','manifest_sha256':receipt['manifest_sha256'],'deploy':False,
            'approved_batches_with_exceptions':{b['id']:b['locked_original']for b in manifest['batches']}}
        plan=human.make_plan(output/'manifest.json',receipt['manifest_sha256'],scope)
        human.apply(self.db,plan,self.meta)
        self.assertEqual(human.verify(self.db,plan),{'white':204,'original':1})
        self.assertEqual(self.db.execute("SELECT decision FROM images WHERE file='205.jpg'").fetchone()[0],'white')
        text=(output/'index.html').read_text()
        self.assertIn('remaining-review:',text);self.assertIn('exact 100 or fewer',text)
        self.assertNotIn('exact 24 or fewer',text)

    def test_changed_candidate_aborts_before_any_gallery_is_written(self):
        self.candidate.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'hash drift'):
            review.build(self.job,self.job/'review',self.cutoff,205)
        self.assertFalse((self.job/'review').exists())

    def test_wrong_checkpoint_count_cannot_silently_drop_images(self):
        with self.assertRaisesRegex(ValueError,'expected 204, found 205'):
            review.build(self.job,self.job/'review',self.cutoff,204)


if __name__=='__main__':unittest.main()
