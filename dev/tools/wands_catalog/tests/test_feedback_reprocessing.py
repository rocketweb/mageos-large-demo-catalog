import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_expanded_catalog import canonical, digest
from bulk_expansion_images import generation_input
from feedback_reprocessing import (pattern, corrected_request, plan_generation,
                                   apply_catalog_patches, product_patches, INSTRUCTIONS, activate, rollback_unstarted, VERSION)
from image_policy import NO_MEASUREMENTS, validate_prompt
from prepare_catalog import sha256


class FeedbackReprocessingTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.run=Path(self.temp.name)
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE feedback_reprocessing(job_id PRIMARY KEY,entry,entry_sha256,manifest_sha256,active)')
        self.job={'job_id':'a','sku':'A','skus':['A'],'profile':'cable-tray','department':'Office',
                  'seed':42,'reference':None,'design':{'subject':'Empty Under-Desk Cable Tray','material':'Metal',
                  'color':'Terracotta','construction':'tray','profile':'cable-tray'},'prompt':'original '+NO_MEASUREMENTS}
        self.job['design_sha256']=digest(self.job['design'])
        self.after,_=corrected_request(self.job,'functional-underdesk-mounts')
        directory=self.run/'candidates/a';directory.mkdir(parents=True)
        self.baseline=directory/'attempt-03.jpg';self.baseline.write_bytes(b'old failed tray')
        self.entry={'request_before':self.job,'request_after':self.after,
                    'after_request_sha256':digest(self.after),'baseline_attempts':3,'max_attempts':5,
                    'baseline_image_path':str(self.baseline),'baseline_image_sha256':sha256(self.baseline),
                    'prompt':self.after['prompt'],'source_kind':'none','mode':'generate','catalog_patches':{}}
        self.row={'job_id':'a','state':'pending','attempts':3,'request':canonical(self.after),
                  'image_path':str(self.baseline),'image_sha256':sha256(self.baseline)}
        self.admit()

    def admit(self):
        self.db.execute('INSERT OR REPLACE INTO feedback_reprocessing VALUES(?,?,?,?,1)',
                        ('a',canonical(self.entry),digest(self.entry),'manifest'))

    def test_shared_planner_uses_new_recipe_for_exhausted_job(self):
        planned=generation_input(self.run,self.db,self.row,{'review_identity':'policy'})
        self.assertIsNotNone(planned)
        self.assertEqual(planned['attempt'],4)
        self.assertIn('mounting flanges',planned['prompt'])
        self.assertNotIn('Terracotta',planned['prompt'])

    def test_budget_is_bounded_and_attempts_preserved(self):
        handled,planned=plan_generation(self.run,self.db,self.row,{})
        self.assertTrue(handled);self.assertEqual(planned['attempt'],4)
        for number in (4,5):
            path=self.baseline.with_name(f'attempt-{number:02d}.jpg');path.write_bytes(str(number).encode())
            path.with_suffix('.json').write_text(canonical({'image_sha256':sha256(path),'actual_prompt':self.entry['prompt'],'request_sha256':digest(self.after)}))
            row={**self.row,'state':'rejected','attempts':number,'image_path':str(path),'image_sha256':sha256(path)}
            handled,planned=plan_generation(self.run,self.db,row,{})
            self.assertTrue(handled)
            self.assertEqual(planned is None,number==5)
        self.assertEqual(self.baseline.read_bytes(),b'old failed tray')

    def test_changed_request_or_baseline_fails_closed(self):
        changed={**self.row,'request':canonical({**self.after,'seed':7})}
        with self.assertRaises(ValueError):plan_generation(self.run,self.db,changed,{})
        self.baseline.write_bytes(b'changed')
        with self.assertRaises(ValueError):plan_generation(self.run,self.db,self.row,{})

    def test_accepted_images_and_unlisted_jobs_are_not_selected(self):
        self.assertEqual(plan_generation(self.run,self.db,{**self.row,'state':'accepted'},{}),(True,None))
        self.assertEqual(plan_generation(self.run,self.db,{**self.row,'job_id':'other'},{}),(False,None))

    def test_correction_history_cannot_be_replaced(self):
        path=self.baseline.with_name('attempt-04.jpg');path.write_bytes(b'new')
        path.with_suffix('.json').write_text(canonical({'image_sha256':sha256(path),'actual_prompt':'other','request_sha256':digest(self.after)}))
        with self.assertRaises(ValueError):plan_generation(self.run,self.db,{**self.row,'attempts':4}, {})

    def test_measurement_ban_is_present_in_every_recipe(self):
        for kind in INSTRUCTIONS:
            with self.subTest(kind=kind):
                after,_=corrected_request(self.job,kind)
                validate_prompt(after['prompt']);self.assertIn(NO_MEASUREMENTS,after['prompt'])

    def test_specific_size_and_material_matching(self):
        bed={**self.job,'profile':'Beds','design':{'subject':'Bed','options':{'wands_size':'Twin'}}}
        self.assertEqual(pattern(bed),'twin-bed-proportions')
        bed['design']['options']['wands_size']='Queen';self.assertIsNone(pattern(bed))
        chair={**self.job,'profile':'Office Chairs','design':{'material':'Solid Wood'}}
        self.assertEqual(pattern(chair),'chair-upholstery-only')
        chair['design']['material']='Plastic';self.assertIsNone(pattern(chair))

    def test_semantic_repair_uses_corrected_product_brief_not_wrong_source_shape(self):
        job=copy.deepcopy(self.job);job['reference']={'job_id':'wrong-source'}
        job['profile']='candle-holder';job['design'].update(material='Glass',subject='White Glass Candle Holder')
        after,semantic=corrected_request(job,'empty-candle-holder')
        self.assertTrue(semantic);self.assertIsNone(after['reference'])
        self.assertEqual(after['design']['material'],'Ceramic')
        self.assertIn('empty',after['design']['construction'])
        products={'A':{'name':'White Glass Candle Holder','lab_spec_material':'Glass','description':'Made from Glass.'}}
        patches=product_patches(job,after,products)
        self.assertEqual(patches['A']['lab_spec_material']['after'],'Ceramic')

    def test_explicit_single_underdesk_drawer_corrects_image_and_product_copy(self):
        job=copy.deepcopy(self.job)
        job['profile']='desk-drawer'
        job['design'].update(subject='Under-Desk Drawer Unit',profile='desk-drawer',
                             construction='two stacked shallow drawers')
        direct={'note':"This should be a single drawer that gets attached underneath a desk, not something like this."}
        self.assertEqual(pattern(job,direct),'single-underdesk-drawer')
        self.assertIsNone(pattern(job))
        after,semantic=corrected_request(job,'single-underdesk-drawer',direct)
        self.assertTrue(semantic)
        self.assertIsNone(after['reference'])
        self.assertIn('single shallow drawer',after['prompt'])
        self.assertIn('mounting',after['prompt'])
        validate_prompt(after['prompt'])
        products={'A':{'description':'Metal construction with two stacked shallow drawers.',
                       'short_description':'Two stacked shallow drawers.',
                       'meta_description':'Metal construction with two stacked shallow drawers.'}}
        patches=product_patches(job,after,products)
        self.assertIn('one mountable shallow drawer',patches['A']['description']['after'])
        self.assertNotIn('two stacked',patches['A']['meta_description']['after'])

    def test_frame_recipe_preserves_existing_reference_and_wood(self):
        job=copy.deepcopy(self.job);job['reference']={'job_id':'source'}
        after,semantic=corrected_request(job,'chair-upholstery-only')
        self.assertFalse(semantic);self.assertEqual(after['reference'],job['reference'])
        self.assertIn('Do not paint the wooden structure',after['prompt'])

    def test_catalog_export_updates_child_and_parent_variation_together(self):
        self.entry['catalog_patches']={'A':{'color':{'before':'Navy','after':'Black'},'name':{'before':'Navy Mirror','after':'Black Mirror'}}}
        self.admit()
        rows={'A':{'sku':'A','color':'Navy','name':'Navy Mirror','product_type':'simple'},
              'P':{'sku':'P','product_type':'configurable','configurable_variations':'sku=A,color=Navy|sku=B,color=White'}}
        apply_catalog_patches(self.db,rows)
        self.assertEqual(rows['A']['color'],'Black')
        self.assertIn('sku=A,color=Black',rows['P']['configurable_variations'])

    def test_export_rejects_duplicate_variant_options(self):
        self.entry['catalog_patches']={'A':{'color':{'before':'Navy','after':'Black'}}};self.admit()
        rows={'A':{'sku':'A','color':'Navy','product_type':'simple'},
              'P':{'sku':'P','product_type':'configurable','configurable_variations':'sku=A,color=Navy|sku=B,color=Black'}}
        with self.assertRaises(ValueError):apply_catalog_patches(self.db,rows)

    def activation_fixture(self):
        candidate=self.run/'candidate';(candidate/'data').mkdir(parents=True)
        for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv'):
            (candidate/'data'/name).write_text('sku,product_type\n'+('A,simple\n' if name=='1-simple.csv' else ''))
        (self.run/'run.json').write_text(canonical({'candidate':str(candidate)}))
        with sqlite3.connect(self.run/'ledger.sqlite') as db:
            db.executescript('CREATE TABLE jobs(job_id PRIMARY KEY,request,pilot,state,attempts,image_path,image_sha256,review,error,updated); CREATE TABLE remote_batches(state);')
            db.execute('INSERT INTO jobs VALUES(?,?,0,?,?,?,?,?,NULL,0)',
                       ('a',canonical(self.job),'rejected',3,str(self.baseline),sha256(self.baseline),'{}'))
        feedback=self.run/'feedback.sqlite'
        with sqlite3.connect(feedback) as db:
            db.executescript('CREATE TABLE items(id,payload); CREATE TABLE decisions(item_id,choice,note,revision,updated);')
        entry={**self.entry,'job_id':'a','sku':'A','before_request_sha256':digest(self.job),'baseline_state':'rejected',
               'direct_feedback':None,'pattern':'functional-underdesk-mounts'}
        plan={'version':VERSION,'run_sha256':sha256(self.run/'run.json'),'feedback_path':str(feedback),
              'jobs':[entry],'patterns':{'functional-underdesk-mounts':1}}
        manifest=self.run/'preview.json';manifest.write_text(canonical(plan))
        return manifest,{'candidate':str(candidate)}

    def test_activation_backup_queue_and_conflict_safe_rollback(self):
        manifest,desc=self.activation_fixture()
        with mock.patch('bulk_expansion_images.descriptor',return_value=desc):
            receipt=activate(self.run,manifest)
            self.assertEqual(receipt['queued'],1)
            self.assertTrue(Path(receipt['backup']).is_file())
            with sqlite3.connect(self.run/'ledger.sqlite') as db:
                row=db.execute('SELECT state,attempts,request FROM jobs').fetchone()
            self.assertEqual(row[:2],('pending',3))
            self.assertEqual(json.loads(row[2]),self.after)
            with self.assertRaises(ValueError):activate(self.run,manifest)
            result=rollback_unstarted(self.run,manifest)
            self.assertEqual(result['restored_unstarted'],['a'])
            with sqlite3.connect(self.run/'ledger.sqlite') as db:
                self.assertEqual(db.execute('SELECT state,attempts,request FROM jobs').fetchone(),('rejected',3,canonical(self.job)))

    def test_activation_rechecks_latest_human_keep(self):
        manifest,desc=self.activation_fixture()
        with sqlite3.connect(self.run/'feedback.sqlite') as db:
            db.execute('INSERT INTO items VALUES(?,?)',('choice',canonical({'job_id':'a','image_sha256':sha256(self.baseline)})))
            db.execute('INSERT INTO decisions VALUES(?,?,?,?,?)',('choice','keep','',1,1))
        with mock.patch('bulk_expansion_images.descriptor',return_value=desc):
            with self.assertRaisesRegex(ValueError,'Human Keep'):activate(self.run,manifest)
        with sqlite3.connect(self.run/'ledger.sqlite') as db:
            self.assertEqual(db.execute('SELECT state FROM jobs').fetchone()[0],'rejected')


if __name__=='__main__':unittest.main()
