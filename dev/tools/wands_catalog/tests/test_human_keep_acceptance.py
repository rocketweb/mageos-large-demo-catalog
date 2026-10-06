import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_expanded_catalog import canonical,digest
from prepare_catalog import sha256
from bulk_expansion_images import current_accepted


class HumanKeepAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'image.jpg';self.path.write_bytes(b'unchanged human-kept image')
        self.feedback=self.root/'feedback.sqlite';self.image_sha=sha256(self.path)
        self.request={'design':{'subject':'cabinet','construction':'two doors'},'design_sha256':'design'}
        with sqlite3.connect(self.feedback) as db:
            db.executescript('CREATE TABLE items(id PRIMARY KEY,payload); CREATE TABLE decisions(item_id PRIMARY KEY,choice,note,revision,updated);')
            db.execute('INSERT INTO items VALUES(?,?)',('item',canonical({'job_id':'job','image_sha256':self.image_sha})))
            db.execute('INSERT INTO decisions VALUES(?,?,?,?,?)',('item','keep','',1,1))
        self.original={'decision':'rejected','image_sha256':self.image_sha,'design_sha256':'design','review_identity':'policy',
                       'ocr':{'status':'ok','observations':[]},'ocr_flags':[],
                       'vision':{'visible_text':False,'visible_measurements':False,'product_matches':False}}
        receipt={'feedback_path':str(self.feedback),'item_id':'item','revision':1,'job_id':'job',
                 'image_sha256':self.image_sha,'request_sha256':digest(self.request),'review_identity':'policy',
                 'original_review':self.original,'annotation_resolution':None}
        self.review={**self.original,'decision':'accepted','human_keep':receipt,'human_keep_sha256':digest(receipt)}
        self.row={'job_id':'job','state':'accepted','image_path':str(self.path),'image_sha256':self.image_sha,
                  'request':canonical(self.request),'review':canonical(self.review)}

    def test_current_human_keep_can_resolve_a_product_identity_disagreement(self):
        self.assertTrue(current_accepted(self.row,'policy'))

    def test_exact_saved_keep_does_not_depend_on_a_later_source_repair(self):
        from unittest.mock import patch
        from bulk_expansion_images import current_job_accepted
        db=sqlite3.connect(':memory:');self.addCleanup(db.close)
        self.request['reference']={'job_id':'source'}
        receipt=self.review['human_keep'];receipt['request_sha256']=digest(self.request)
        self.review['human_keep_sha256']=digest(receipt)
        self.row['request']=canonical(self.request);self.row['review']=canonical(self.review)
        with patch('bulk_expansion_images.accepted_reference',return_value=False):
            self.assertTrue(current_job_accepted(db,self.row,'policy'))

    def test_undo_or_redo_revokes_human_acceptance(self):
        with sqlite3.connect(self.feedback) as db:db.execute("UPDATE decisions SET choice='redo',revision=2")
        self.assertFalse(current_accepted(self.row,'policy'))

    def test_visible_measurements_cannot_be_silently_overridden(self):
        self.original['vision']['visible_measurements']=True
        receipt=self.review['human_keep'];receipt['original_review']=self.original
        self.review['human_keep_sha256']=digest(receipt);self.row['review']=canonical(self.review)
        self.assertFalse(current_accepted(self.row,'policy'))

    def test_changed_image_request_or_receipt_cannot_reuse_approval(self):
        for kind in ('image','request','receipt'):
            with self.subTest(kind=kind):
                row=dict(self.row)
                if kind=='image':row['image_sha256']='changed'
                if kind=='request':row['request']=canonical({**self.request,'seed':7})
                if kind=='receipt':
                    review=json.loads(row['review']);review['human_keep']['revision']=2;row['review']=canonical(review)
                self.assertFalse(current_accepted(row,'policy'))

    def test_kept_image_is_not_automatically_regenerated(self):
        from unittest.mock import patch
        from bulk_expansion_images import generation_input
        from human_keep_acceptance import is_kept
        run=self.root/'run';run.mkdir()
        destination=self.root/'human-image-review';destination.mkdir()
        self.feedback.rename(destination/'feedback.sqlite')
        self.assertTrue(is_kept(run,self.row))
        with patch('feedback_reprocessing.plan_generation',side_effect=AssertionError('Must preserve Keep')):
            self.assertIsNone(generation_input(run,None,self.row,{}))

    def test_changed_source_does_not_requeue_human_accepted_image(self):
        from unittest.mock import patch
        from bulk_expansion_images import requeue_changed_sources
        db=sqlite3.connect(':memory:');self.addCleanup(db.close);db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE jobs(job_id,state,image_path,request,review,updated,pilot)')
        request={**self.request,'reference':{'job_id':'source'}}
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',('job','accepted',str(self.path),canonical(request),canonical(self.review),0,0))
        with patch('bulk_expansion_images.accepted_reference',return_value=self.path):
            self.assertEqual(requeue_changed_sources(self.root,db,'policy'),0)
        self.assertEqual(db.execute('SELECT state FROM jobs').fetchone()[0],'accepted')

    def test_cleanup_requires_preserved_original_and_hash_bound_comparison(self):
        cleaned=self.root/'cleaned.jpg';cleaned.write_bytes(b'cleaned photo')
        pin=sha256(cleaned);receipt=self.review['human_keep']
        receipt['image_sha256']=pin
        derived={**self.original,'image_sha256':pin}
        receipt['annotation_cleanup']={'original_path':str(self.path),'original_sha256':self.image_sha,
            'image_sha256':pin,'review':derived,'comparison':{'reviewer':'direct_visual_inspection',
            'original_sha256':self.image_sha,'image_sha256':pin,'decision':'only_annotations_removed',
            'observations':'Logo removed; product structure, color, finish and viewpoint preserved.'}}
        self.review.update(image_sha256=pin,human_keep_sha256=digest(receipt))
        row={**self.row,'image_path':str(cleaned),'image_sha256':pin,'review':canonical(self.review)}
        self.assertTrue(current_accepted(row,'policy'))
        receipt['annotation_cleanup']['comparison']['image_sha256']='wrong'
        self.review['human_keep_sha256']=digest(receipt);row['review']=canonical(self.review)
        self.assertFalse(current_accepted(row,'policy'))


if __name__=='__main__':unittest.main()
