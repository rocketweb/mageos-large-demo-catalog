import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bulk_expansion_images import connect, review
from image_review import ReviewUnavailable, ReviewServiceUnavailable
from prepare_catalog import sha256

class FailureIsolationTest(unittest.TestCase):
    def test_operator_checkpoint_finishes_current_job_and_leaves_next_unreviewed(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);db=connect(run)
            db.executescript('CREATE TABLE jobs(job_id,ordinal,request,pilot,state,attempts,image_path,image_sha256,review,error,updated); CREATE TABLE references_to_review(review);')
            for number in range(2):
                path=run/f'{number}.jpg';path.write_bytes(str(number).encode())
                db.execute('INSERT INTO jobs VALUES(?,?,?,1,\'generated\',1,?,?,NULL,NULL,NULL)',(str(number),number,json.dumps({'design':{},'reference':None}),str(path),sha256(path)))
            db.commit();db.close()
            def checkpoint(*args,**kwargs):
                (run/'STOP').touch();return {'decision':'accepted'}
            with patch('bulk_expansion_images.descriptor',return_value={'vision_model':'test','review_identity':'test'}),patch('bulk_expansion_images.Reviewer') as reviewer:
                reviewer.return_value.inspect.side_effect=checkpoint
                review(run,Path('unused'),None,pilot=True)
            db=connect(run)
            self.assertEqual([r[0] for r in db.execute('SELECT state FROM jobs ORDER BY ordinal')],['accepted','generated'])
            db.close()

    def test_operator_checkpoint_leaves_next_reference_or_repair_unreviewed(self):
        from repair_expansion_references import review_repairs
        for repair in (False,True):
            with self.subTest(repair=repair),tempfile.TemporaryDirectory() as directory:
                run=Path(directory);db=connect(run)
                db.execute('CREATE TABLE references_to_review(image_sha256,design_sha256,path,design,review)')
                for number in range(2):
                    path=run/f'{number}.jpg';path.write_bytes(str(number).encode())
                    db.execute('INSERT INTO references_to_review VALUES(?,?,?,?,NULL)',(sha256(path),'design',str(path),'{}'))
                    db.execute('INSERT INTO reference_repairs VALUES(?,?,1,?,?,NULL)',(sha256(path),'design',str(path),sha256(path)))
                db.commit();db.close()
                module='repair_expansion_references' if repair else 'bulk_expansion_images'
                def checkpoint(*args,**kwargs):
                    (run/'STOP').touch();return {'decision':'accepted'}
                with patch(module+'.descriptor',return_value={'vision_model':'test','review_identity':'test'}), \
                        patch(module+'.status'),patch(module+'.Reviewer') as reviewer:
                    reviewer.return_value.inspect.side_effect=checkpoint
                    if repair:review_repairs(run,Path('unused'),None)
                    else:review(run,Path('unused'),None,references=True)
                db=connect(run);table='reference_repairs' if repair else 'references_to_review'
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table+' WHERE review IS NULL').fetchone()[0],1)
                db.close()

    def test_reference_and_repair_outages_do_not_spend_review_budget(self):
        from repair_expansion_references import review_repairs
        for repair in (False,True):
            with self.subTest(repair=repair),tempfile.TemporaryDirectory() as directory:
                run=Path(directory);db=connect(run)
                path=run/'reference.jpg';path.write_bytes(b'reference')
                db.execute('CREATE TABLE references_to_review(image_sha256,design_sha256,path,design,review)')
                db.execute('INSERT INTO references_to_review VALUES(?,?,?,?,NULL)',(sha256(path),'design',str(path),'{}'))
                db.execute('INSERT INTO reference_repairs VALUES(?,?,1,?,?,NULL)',(sha256(path),'design',str(path),sha256(path)))
                db.commit();db.close()
                module='repair_expansion_references' if repair else 'bulk_expansion_images'
                with patch(module+'.descriptor',return_value={'vision_model':'test','review_identity':'test'}), \
                        patch(module+'.status'),patch(module+'.Reviewer') as reviewer:
                    reviewer.return_value.inspect.side_effect=ReviewServiceUnavailable([{'service_unavailable':True}])
                    with self.assertRaises(ReviewServiceUnavailable):
                        if repair:review_repairs(run,Path('unused'),None)
                        else:review(run,Path('unused'),None,references=True)
                db=connect(run)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM review_failures').fetchone()[0],0)
                self.assertIsNone(db.execute('SELECT review FROM references_to_review').fetchone()[0])
                self.assertIsNone(db.execute('SELECT review FROM reference_repairs').fetchone()[0])
                db.close()
                self.assertTrue((run/'review-service-errors.jsonl').is_file())

    def test_service_outage_preserves_job_and_does_not_spend_review_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);db=connect(run)
            db.executescript('CREATE TABLE jobs(job_id,ordinal,request,pilot,state,attempts,image_path,image_sha256,review,error,updated); CREATE TABLE references_to_review(review);')
            path=run/'candidate.jpg';path.write_bytes(b'candidate')
            db.execute("INSERT INTO jobs VALUES('one',1,?,1,'generated',1,?,?,NULL,NULL,NULL)",
                       (json.dumps({'design':{},'reference':None}),str(path),sha256(path)))
            db.commit();db.close()
            with patch('bulk_expansion_images.descriptor',return_value={'vision_model':'test','review_identity':'test'}),patch('bulk_expansion_images.Reviewer') as reviewer:
                reviewer.return_value.inspect.side_effect=ReviewServiceUnavailable([{'service_unavailable':True}])
                with self.assertRaises(ReviewServiceUnavailable):review(run,Path('unused'),None,pilot=True)
            db=connect(run)
            self.assertEqual(db.execute('SELECT state,review FROM jobs').fetchone()[:],('generated',None))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM review_failures').fetchone()[0],0)
            db.close()
            self.assertTrue((run/'review-service-errors.jsonl').is_file())

    def test_bad_response_holds_one_job_and_reviews_next(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);db=connect(run)
            db.executescript('CREATE TABLE jobs(job_id,ordinal,request,pilot,state,attempts,image_path,image_sha256,review,error,updated); CREATE TABLE references_to_review(review);')
            for number in range(2):
                path=run/f'{number}.jpg';path.write_bytes(str(number).encode())
                db.execute('INSERT INTO jobs VALUES(?,?,?,1,\'generated\',1,?,?,NULL,NULL,NULL)',(str(number),number,json.dumps({'design':{},'reference':None}),str(path),sha256(path)))
            db.commit();db.close()
            with patch('bulk_expansion_images.descriptor',return_value={'vision_model':'test','review_identity':'test'}),patch('bulk_expansion_images.Reviewer') as reviewer:
                reviewer.return_value.inspect.side_effect=[ReviewUnavailable([{'finish_reason':'length'}]),{'decision':'accepted'}]
                review(run,Path('unused'),None,pilot=True)
            db=connect(run)
            self.assertEqual([r[0] for r in db.execute('SELECT state FROM jobs ORDER BY ordinal')],['review_error','accepted'])
            evidence=json.loads(db.execute('SELECT evidence FROM review_failures').fetchone()[0])
            self.assertEqual(evidence['attempts'][0]['finish_reason'],'length')
            db.close()
