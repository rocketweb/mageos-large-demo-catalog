import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bulk_expansion_images import current_accepted, require_bulk_gate, current_job_accepted, connect, accept_ocr_review, hold_half_round_geometry, accept_geometry_review, awaiting_direct_geometry_review
from repair_expansion_references import queue
from prepare_catalog import sha256


class BulkAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.run = Path(self.directory.name)
        self.image = self.run / 'image.jpg'
        self.image.write_bytes(b'immutable image test fixture')
        self.pin = sha256(self.image)
        self.row = {'job_id':'a', 'state':'accepted', 'image_path':str(self.image),
                    'image_sha256':self.pin, 'request':json.dumps({'design_sha256':'design'}),
                    'review':json.dumps({'decision':'accepted', 'review_identity':'policy',
                                         'image_sha256':self.pin, 'design_sha256':'design'})}
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE jobs(job_id, state, image_path, image_sha256, request, review, pilot)')
        self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,1)', tuple(self.row.values()))
        self.desc = {'review_identity':'policy', 'candidate_sha256':'catalog'}

    def receipt(self):
        (self.run/'pilot-acceptance.json').write_text(json.dumps({
            'images':{'a':self.pin}, 'candidate_sha256':'catalog',
            'visual_review_receipt_sha256':'visual-review'}))

    def test_no_receipt_or_incomplete_review_can_start_bulk(self):
        with self.assertRaises(ValueError):require_bulk_gate(self.run,self.db,self.desc)
        self.receipt()
        require_bulk_gate(self.run,self.db,self.desc)
        self.db.execute("UPDATE jobs SET state='review_required'")
        with self.assertRaises(ValueError):require_bulk_gate(self.run,self.db,self.desc)

    def test_changed_image_or_design_or_policy_invalidates_acceptance(self):
        self.assertTrue(current_accepted(self.row,'policy'))
        self.assertFalse(current_accepted(self.row,'changed-policy'))
        self.assertFalse(current_accepted({**self.row,'request':json.dumps({'design_sha256':'changed'})},'policy'))
        self.image.write_bytes(b'replacement image')
        self.assertFalse(current_accepted(self.row,'policy'))
        self.receipt()
        with self.assertRaises(ValueError):require_bulk_gate(self.run,self.db,self.desc)

    def test_changed_catalog_invalidates_pilot(self):
        self.receipt()
        with self.assertRaises(ValueError):
            require_bulk_gate(self.run,self.db,{**self.desc,'candidate_sha256':'changed'})

    def test_variant_must_match_current_accepted_source_bytes(self):
        source={**self.row,'job_id':'source'}
        self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,1)',tuple(source.values()))
        derived={**self.row,'request':json.dumps({'design_sha256':'design','reference':{'job_id':'source'}})}
        evidence=json.loads(derived['review']);evidence['reference_sha256']=self.pin
        derived['review']=json.dumps(evidence)
        self.assertTrue(current_job_accepted(self.db,derived,'policy'))
        evidence['reference_sha256']='outdated-source';derived['review']=json.dumps(evidence)
        self.assertFalse(current_job_accepted(self.db,derived,'policy'))

    def test_repair_queue_waits_for_review_and_stops_after_three_failures(self):
        db=connect(self.run);self.addCleanup(db.close)
        db.execute('CREATE TABLE references_to_review(image_sha256,design_sha256,path,design,review)')
        db.execute('INSERT INTO references_to_review VALUES(?,?,?,?,?)',
                   ('original','design',str(self.image),'{}',json.dumps({'decision':'rejected'})))
        self.assertEqual(queue(db,False)[0][1],1)
        db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,NULL)',
                   ('original','design',1,str(self.image),self.pin))
        self.assertEqual(queue(db,False),[])
        for attempt in range(1,4):
            db.execute('INSERT OR REPLACE INTO reference_repairs VALUES(?,?,?,?,?,?)',
                       ('original','design',attempt,str(self.image),self.pin,json.dumps({'decision':'rejected'})))
        self.assertEqual(queue(db,False),[])

    def test_uncertain_ocr_reference_gets_a_new_reviewed_repair_not_an_override(self):
        db=connect(self.run);self.addCleanup(db.close)
        db.execute('CREATE TABLE references_to_review(image_sha256,design_sha256,path,design,review)')
        db.execute('INSERT INTO references_to_review VALUES(?,?,?,?,?)',
                   ('original','design',str(self.image),'{}',json.dumps({'decision':'review_required'})))
        self.assertEqual(queue(db,False)[0][1],1)
        for attempt in range(1,4):
            db.execute('INSERT OR REPLACE INTO reference_repairs VALUES(?,?,?,?,?,?)',
                       ('original','design',attempt,str(self.image),self.pin,json.dumps({'decision':'review_required'})))
        self.assertEqual(queue(db,False),[])

    def test_direct_ocr_resolution_cannot_override_failed_vision(self):
        db=connect(self.run)
        db.execute('CREATE TABLE jobs(job_id,state,image_path,image_sha256,request,review,pilot,updated)')
        db.execute('CREATE TABLE references_to_review(review)')
        evidence={**json.loads(self.row['review']),'vision':{'acceptable':False},'ocr_flags':[{'text':'Tl'}]}
        row={**self.row,'state':'review_required','review':json.dumps(evidence)}
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,1,NULL)',tuple(row.values()));db.commit()
        with mock.patch('bulk_expansion_images.descriptor',return_value=self.desc):
            with self.assertRaises(ValueError):accept_ocr_review(self.run,'a',self.pin,'Inspected image directly')
            self.assertEqual(db.execute('SELECT state FROM jobs').fetchone()[0],'review_required')
            evidence['vision']['acceptable']=True
            db.execute('UPDATE jobs SET review=?',(json.dumps(evidence),));db.commit()
            accept_ocr_review(self.run,'a',self.pin,'Inspected plain legs; the OCR text is a shape false positive')
        self.assertEqual(db.execute('SELECT state FROM jobs').fetchone()[0],'accepted')
        db.close()

    def test_half_round_tables_need_direct_geometry_review_after_normal_qa(self):
        clean={'decision':'accepted','vision':{'acceptable':True},'ocr_flags':[]}
        design={'profile':'balcony-table','construction':'half-round top and straight legs'}
        held=hold_half_round_geometry(clean,design)
        self.assertEqual(held['decision'],'review_required')
        self.assertEqual(held['geometry_hold']['required'],'visible straight rear tabletop edge')
        self.assertEqual(clean['decision'],'accepted')
        self.assertEqual(hold_half_round_geometry(clean,{'profile':'balcony-table','construction':'round top'}),clean)

    def test_resolved_ocr_does_not_bypass_half_round_geometry(self):
        db=connect(self.run);self.addCleanup(db.close)
        db.execute('CREATE TABLE jobs(job_id,state,image_path,image_sha256,request,review,pilot,updated)')
        db.execute('CREATE TABLE references_to_review(review)')
        request={'design_sha256':'design','reference':None,
                 'design':{'profile':'balcony-table','construction':'half-round top and straight legs'}}
        evidence={**json.loads(self.row['review']),'decision':'review_required',
                  'vision':{'acceptable':True},'ocr_flags':[{'text':'E'}],'model':'test'}
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,1,NULL)',('a','review_required',str(self.image),self.pin,
                   json.dumps(request),json.dumps(evidence)));db.commit()
        with mock.patch('bulk_expansion_images.descriptor',return_value=self.desc):
            accept_ocr_review(self.run,'a',self.pin,'The plain tabletop and leg formed the OCR E; no printed character.')
            row=dict(db.execute('SELECT * FROM jobs').fetchone())
            self.assertEqual(row['state'],'review_required')
            self.assertTrue(awaiting_direct_geometry_review(row))
            resolved=json.loads(row['review']);resolved['manual_ocr_resolution']['image_sha256']='stale'
            db.execute('UPDATE jobs SET review=?',(json.dumps(resolved),));db.commit()
            with self.assertRaises(ValueError):
                accept_geometry_review(self.run,'a',self.pin,'The top has a straight rear edge and curved front.')
            db.execute('UPDATE jobs SET review=?',(row['review'],));db.commit()
            accept_geometry_review(self.run,'a',self.pin,'The top has a straight rear edge and curved front.')
        self.assertEqual(db.execute('SELECT state FROM jobs').fetchone()[0],'accepted')

    def test_geometry_review_hold_does_not_consume_another_generation_attempt(self):
        evidence={'decision':'review_required','geometry_hold':{'version':'half-round-geometry-v1'},
                  'vision':{'acceptable':True},'ocr_flags':[]}
        self.assertTrue(awaiting_direct_geometry_review({'state':'review_required','review':json.dumps(evidence)}))
        self.assertFalse(awaiting_direct_geometry_review({'state':'rejected','review':json.dumps(evidence)}))
        self.assertFalse(awaiting_direct_geometry_review({'state':'review_required','review':json.dumps({**evidence,'ocr_flags':['mark']})}))

    def test_direct_geometry_acceptance_requires_exact_hash_and_clean_qa(self):
        db=connect(self.run);self.addCleanup(db.close)
        db.execute('CREATE TABLE jobs(job_id,state,image_path,image_sha256,request,review,pilot,updated)')
        db.execute('CREATE TABLE references_to_review(review)')
        request={'design_sha256':'design','reference':None,
                 'design':{'profile':'balcony-table','construction':'half-round top and straight legs'}}
        evidence={**json.loads(self.row['review']),'decision':'review_required','vision':{'acceptable':True},
                  'ocr_flags':[],'model':'test','geometry_hold':{'version':'half-round-geometry-v1',
                                                               'required':'visible straight rear tabletop edge'}}
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,1,NULL)',('a','review_required',str(self.image),self.pin,
                   json.dumps(request),json.dumps(evidence)));db.commit()
        with mock.patch('bulk_expansion_images.descriptor',return_value=self.desc):
            with self.assertRaises(ValueError):accept_geometry_review(self.run,'a','stale','A straight rear edge is visible')
            with self.assertRaises(ValueError):accept_geometry_review(self.run,'a',self.pin,'Looks fine')
            accept_geometry_review(self.run,'a',self.pin,'The tabletop has a visible straight rear edge and a curved front rim.')
        row=db.execute('SELECT state,review FROM jobs WHERE job_id=?',('a',)).fetchone()
        self.assertEqual(row['state'],'accepted')
        self.assertEqual(json.loads(row['review'])['decision'],'accepted')
        self.assertTrue(db.execute("SELECT 1 FROM manual_reviews WHERE job_id='a' AND decision='accepted'").fetchone())
        db.close()


if __name__ == '__main__':unittest.main()
