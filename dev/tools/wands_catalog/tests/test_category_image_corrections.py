import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import category_image_corrections as category
from build_expanded_catalog import canonical,digest
from prepare_catalog import sha256
from image_policy import validate_prompt,NO_MEASUREMENTS


class CategoryCorrectionTest(unittest.TestCase):
    def test_recolored_child_inherits_only_a_current_native_confirmed_parent(self):
        self.db.execute('CREATE TABLE jobs(job_id,request,image_sha256,review)')
        source={**self.job,'job_id':'source'}
        self.db.execute('INSERT INTO jobs VALUES(?,?,?,?)',('source',canonical(source),'source-pixels','{}'))
        child={**self.job,'reference':{'job_id':'source'}}
        row={**self.row,'request':canonical(child),'review':canonical({'reference_sha256':'source-pixels'})}
        q={'image_sha256':'source-pixels','design_sha256':source['design_sha256'],'identity':category.identity('test-model'),
           'result':{'acceptable':True},'direct_riser_resolution':{'version':'horizontal-riser-v1',
           'image_sha256':'source-pixels','design_sha256':source['design_sha256'],'reviewer':'direct visual inspection',
           'observations':'Separate riser with a horizontal load surface.'}}
        self.db.execute('INSERT INTO category_image_reviews VALUES(?,?,?)',('source','source-pixels',canonical(q)))
        with patch('bulk_expansion_images.current_job_accepted',return_value=True):
            self.assertTrue(category.inherited_riser_confirmed(self.db,row,{'result':{'acceptable':True}},'test-model','qa'))
            wrong={**row,'review':canonical({'reference_sha256':'old-source'})}
            self.assertFalse(category.inherited_riser_confirmed(self.db,wrong,{'result':{'acceptable':True}},'test-model','qa'))
            self.db.execute("DELETE FROM category_image_reviews WHERE job_id='source'")
            self.assertFalse(category.inherited_riser_confirmed(self.db,row,{'result':{'acceptable':True}},'test-model','qa'))

    def test_category_audit_handles_retained_reservations_without_treating_them_as_catalog_jobs(self):
        self.db.execute('CREATE TABLE jobs(job_id,request,image_path,state,pilot,ordinal)')
        self.db.execute('INSERT INTO jobs VALUES(?,?,NULL,\'accepted\',0,1)',
            ('ordinary',canonical({'reference':{'job_id':'approved-source'}})))
        self.db.execute('CREATE TABLE remote_batches(state,manifest)')
        self.db.execute('INSERT INTO remote_batches VALUES(?,?)',('reserved',canonical(
            {'kind':'retained-reference-repairs','jobs':[{'job_id':'retained-only'}]})))
        self.db.execute('INSERT INTO remote_batches VALUES(?,?)',('reserved',canonical(
            {'jobs':[{'job_id':'ordinary'}]})))
        with patch('bulk_expansion_images.descriptor',return_value=self.desc), \
                patch('bulk_expansion_images.connect',return_value=self.db), \
                patch('human_keep_acceptance.prepare',return_value={'entries':[]}), \
                patch('category_image_corrections.api_key',return_value='private'):
            self.assertEqual(category.audit(self.root,Path('/private-settings')),{'reviewed':0})

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'original.jpg';self.path.write_bytes(b'preserved original')
        self.db=sqlite3.connect(':memory:');self.addCleanup(self.db.close);self.db.row_factory=sqlite3.Row
        self.db.executescript('CREATE TABLE category_corrections(job_id PRIMARY KEY,entry,entry_sha256); CREATE TABLE category_image_reviews(job_id,image_sha256,review,PRIMARY KEY(job_id,image_sha256));')
        self.design={'profile':'monitor-riser','subject':'desktop monitor riser','color':'Terracotta','material':'Bamboo',
                     'construction':'shallow drawer beneath the top','dimensions_cm':{'width':46.2}}
        self.job={'job_id':'job','profile':'monitor-riser','design':self.design,'design_sha256':digest(self.design),'seed':19,'reference':None}
        self.row={'job_id':'job','request':canonical(self.job),'attempts':3,'state':'rejected','image_path':str(self.path),'image_sha256':sha256(self.path)}
        self.desc={'vision_model':'test-model','review_identity':'standard-review'}
        self.bind()
        self.result={'verdict':'pass','confidence':1,'observed_product':'separate drawer riser','issues':[],**{k:True for k in category.BOOLS}}
        self.store_review()

    def bind(self):
        self.entry={'before':dict(self.row),'baseline_attempts':3,'request_sha256':digest(self.job),'prompt':category.prompt(self.job)}
        self.db.execute('INSERT OR REPLACE INTO category_corrections VALUES(?,?,?)',('job',canonical(self.entry),digest(self.entry)))

    def store_review(self,**updates):
        review={'image_sha256':self.row['image_sha256'],'design_sha256':self.job['design_sha256'],
                'identity':category.identity('test-model'),'result':category.parse(canonical(self.result)),
                'direct_riser_resolution':{'version':'horizontal-riser-v1','image_sha256':self.row['image_sha256'],
                    'design_sha256':self.job['design_sha256'],'reviewer':'direct visual inspection',
                    'observations':'Separate riser with a broad horizontal load surface, coherent low supports and the correct finish.'},**updates}
        self.db.execute('INSERT OR REPLACE INTO category_image_reviews VALUES(?,?,?)',('job',self.row['image_sha256'],canonical(review)))

    def planned(self,row=None,kept=False,source=None):
        with patch('human_keep_acceptance.is_kept',return_value=kept),patch('bulk_expansion_images.accepted_reference',return_value=source):
            return category.plan_generation(self.root,self.db,row or self.row,self.desc)

    def test_two_attempt_budget_never_resets_history(self):
        for n in (3,4):
            handled,plan=self.planned({**self.row,'attempts':n})
            self.assertTrue(handled);self.assertEqual(plan['attempt'],n+1)
        self.assertEqual(self.planned({**self.row,'attempts':5}),(True,None))
        self.assertEqual(self.planned({**self.row,'attempts':2}),(True,None))

    def test_current_category_evidence_required_before_regeneration(self):
        self.store_review(identity='stale')
        self.assertEqual(self.planned(),(True,None))
        self.db.execute('DELETE FROM category_image_reviews')
        self.assertEqual(self.planned(),(True,None))

    def test_explicit_monitor_revision_can_correct_old_keep(self):
        self.result['optional_monitor_correct']=False;self.store_review()
        self.assertIsNotNone(self.planned(kept=True)[1])

    def test_new_compliant_monitor_keep_and_manual_review_are_preserved(self):
        self.assertEqual(self.planned(kept=True),(True,None))
        self.store_review(manual_review_required=True)
        self.assertEqual(self.planned(),(True,None))

    def test_shoe_keep_remains_protected(self):
        self.job['profile']='shoe-bench';self.row['request']=canonical(self.job);self.bind()
        self.assertEqual(self.planned(kept=True),(True,None))

    def test_reserved_batch_keeps_its_original_admission(self):
        self.assertEqual(self.planned({**self.row,'state':'remote_reserved'}),(False,None))

    def test_changed_original_or_intent_fails_closed(self):
        self.path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'baseline changed'):self.planned()
        self.path.write_bytes(b'preserved original')
        with self.assertRaisesRegex(ValueError,'intent changed'):
            self.planned({**self.row,'request':canonical({**self.job,'seed':0})})

    def test_missing_or_failed_parent_cannot_be_recolored(self):
        self.job['reference']={'job_id':'source'};self.row['request']=canonical(self.job);self.bind()
        self.db.execute('CREATE TABLE jobs(job_id,request,image_sha256)')
        self.assertEqual(self.planned(source=self.path),(True,None))
        self.db.execute('INSERT INTO jobs VALUES(?,?,?)',('source',canonical(self.job),'parent-image'))
        self.assertEqual(self.planned(source=self.path),(True,None))

    def test_parser_fails_for_bad_structure_uncertainty_and_wrong_monitor(self):
        for content in ('[]','null','{}'):
            with self.assertRaises(ValueError):category.parse(content)
        for values in ({'optional_monitor_correct':False},{'confidence':.94},{'verdict':'uncertain'},{'issues':['colored screen']}):
            self.assertFalse(category.parse(canonical({**self.result,**values}))['acceptable'])
        with self.assertRaises(ValueError):category.parse(canonical({**self.result,'confidence':True}))

    def test_prompts_separate_product_from_monitor_without_measurements(self):
        normal=category.prompt(self.job);example=category.prompt({**self.job,'job_id':category.EXAMPLE})
        for prompt in (normal,example):
            validate_prompt(prompt);self.assertIn(NO_MEASUREMENTS,prompt);self.assertNotIn('46.2',prompt)
        self.assertIn('Only the furniture riser',normal)
        self.assertIn('whole monitor including its own neck and foot is black',example)
        shelf={**self.job,'profile':'shoe-bench','design':{**self.design,'construction':'slatted shelves'}}
        self.assertIn('slatted shoe-storage shelves',category.prompt(shelf))
        rounded={**shelf,'design':{**self.design,'construction':'vertical dividers beneath a rounded seat'}}
        self.assertIn('front-facing shoe cubbies',category.prompt(rounded));self.assertIn('long rectangular seat',category.prompt(rounded))

    def test_historical_pilot_is_for_generation_not_current_export_acceptance(self):
        with patch('bulk_expansion_images.current_accepted',return_value=True):
            self.assertEqual(category.original_pilot_image(self.db,self.row,'policy'),self.row['image_sha256'])
        with patch('bulk_expansion_images.current_accepted',return_value=False):
            self.assertIsNone(category.original_pilot_image(self.db,self.row,'policy'))

    def test_export_gate_requires_current_category_review_even_if_general_qa_passed(self):
        self.db.execute('CREATE TABLE jobs(job_id,request,image_sha256,review,state)')
        self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',('job',self.row['request'],self.row['image_sha256'],'{}','accepted'))
        self.assertEqual(category.unresolved(self.db,'test-model'),0)
        self.store_review(identity='outdated category rules')
        self.assertEqual(category.unresolved(self.db,'test-model'),1)

    def test_automatic_category_pass_cannot_export_an_unconfirmed_riser(self):
        self.db.execute('CREATE TABLE jobs(job_id,request,image_sha256,review,state)')
        self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',('job',self.row['request'],self.row['image_sha256'],'{}','accepted'))
        self.store_review(direct_riser_resolution=None)
        self.assertEqual(category.unresolved(self.db,'test-model'),1)
        self.store_review(direct_riser_resolution={'version':'horizontal-riser-v1','image_sha256':'other-photo',
            'design_sha256':self.job['design_sha256'],'reviewer':'direct visual inspection',
            'observations':'Separate riser with a broad horizontal load surface.'})
        self.assertEqual(category.unresolved(self.db,'test-model'),1)
        self.store_review()
        self.assertEqual(category.unresolved(self.db,'test-model'),0)
        self.store_review()
        self.db.execute("UPDATE jobs SET image_sha256='new image'")
        self.assertEqual(category.unresolved(self.db,'test-model'),1)

    def test_only_current_human_shoe_approval_can_resolve_category_disagreement(self):
        self.db.execute('CREATE TABLE jobs(job_id,request,image_sha256,review,state)')
        self.job['profile']='shoe-bench'
        self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',('job',canonical(self.job),'new image','{"human_keep":{"receipt":"verified separately"}}','accepted'))
        with patch('bulk_expansion_images.current_accepted',return_value=True):
            self.assertEqual(category.unresolved(self.db,'test-model','standard-review'),0)
        with patch('bulk_expansion_images.current_accepted',return_value=False):
            self.assertEqual(category.unresolved(self.db,'test-model','standard-review'),1)


if __name__=='__main__':unittest.main()
