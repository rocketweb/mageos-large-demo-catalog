import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_expanded_catalog import canonical, digest
from image_policy import product_prompt
from bulk_expansion_images import connect, generation_input, review_eligible


class AuthorizedCompletionTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.run=Path(self.temp.name);self.db=connect(self.run);self.addCleanup(self.db.close)
        self.db.executescript('CREATE TABLE completion_authorization(id PRIMARY KEY, policy, policy_sha256); CREATE TABLE completion_targets(kind,target,intent_sha256,PRIMARY KEY(kind,target)); CREATE TABLE completion_review_baselines(scope,item,failures,PRIMARY KEY(scope,item));')
        self.policy={'schema':1,'active':True,'advisory_component_counts':True,'candidate_sha256':'candidate','review_identity':'qa',
            'authorization':'User requested finishing the project and removing gates as needed.',
            'jobs':{'job':{'request_sha256':digest({'job_id':'job','seed':1,'reference':None,
                'profile':'dresser','design':{'subject':'Four drawer dresser','material':'Wood','color':'White','construction':'four drawers'},
                'prompt':product_prompt('White dresser')})}},'references':{},'review_failures':{'repairs:item':3}}
        self.db.execute('INSERT INTO completion_authorization VALUES(1,?,?)',(canonical(self.policy),digest(self.policy)))
        self.db.execute('INSERT INTO completion_targets VALUES(?,?,?)',('job','job',self.policy['jobs']['job']['request_sha256']))
        self.db.execute('INSERT INTO completion_review_baselines VALUES(?,?,?)',('repairs','item',3))
        self.db.commit()

    def test_existing_review_format_failures_receive_an_additional_window_without_reset(self):
        self.db.execute('INSERT INTO review_failures VALUES(?,?,?,?)',('repairs','item',3,'{}'))
        self.assertTrue(review_eligible(self.db,'repairs','item'))
        self.assertEqual(self.db.execute('SELECT failures FROM review_failures').fetchone()[0],3)

    def test_exhausted_job_can_render_a_new_structure_without_changing_its_brief(self):
        job={'job_id':'job','seed':1,'reference':None,'profile':'dresser',
             'design':{'subject':'Four drawer dresser','material':'Wood','color':'White','construction':'four drawers'},'prompt':product_prompt('White dresser')}
        row={'request':canonical(job),'job_id':'job','state':'rejected','attempts':7,
             'review':canonical({'vision':{'product_matches':False,'issues':['Only two drawers are present.']}})}
        with patch('human_keep_acceptance.is_kept',return_value=False):
            plan=generation_input(self.run,self.db,row,{'candidate_sha256':'candidate','review_identity':'qa'})
        self.assertIsNotNone(plan)
        self.assertIsNone(plan['reference'])
        self.assertEqual(plan['attempt'],8)
        self.assertEqual(json.loads(row['request']),job)
        self.assertIn('four',plan['prompt'].lower())

    def test_changed_authorized_request_fails_closed(self):
        job={'job_id':'job','seed':1,'reference':None,'profile':'dresser','design':{},'prompt':'changed'}
        row={'request':canonical(job),'job_id':'job','state':'rejected','attempts':7,'review':'{}'}
        with patch('human_keep_acceptance.is_kept',return_value=False):
            with self.assertRaises(ValueError):
                generation_input(self.run,self.db,row,{'candidate_sha256':'candidate','review_identity':'qa'})

    def test_human_keep_still_precedes_completion_retries(self):
        row={'job_id':'job','request':'{}','state':'accepted'}
        with patch('human_keep_acceptance.is_kept',return_value=True):
            self.assertIsNone(generation_input(self.run,self.db,row,{'candidate_sha256':'candidate','review_identity':'qa'}))

    def test_duplicate_counter_can_be_advisory_without_erasing_its_observation(self):
        import component_review
        from authorized_completion import relieve_review
        design={'subject':'Four drawer dresser','construction':'four drawers'}
        q={'decision':'rejected','image_sha256':'pixels','design_sha256':digest(design),'model':'model','review_identity':'qa',
            'ocr':{'status':'ok','observations':[]},'ocr_flags':[],
            'vision':{'verdict':'pass','acceptable':True,'visible_text':False,'visible_measurements':False,
                      'geometry_defects':False,'product_matches':True,'piece_count_matches':True,'issues':[]},
            'component_review':{'drawer_fronts':5,'expected':{'drawer_fronts':4},'confidence':.98}}
        updated=relieve_review(self.db,q,design)
        self.assertEqual(updated['decision'],'accepted')
        self.assertEqual(updated['component_review']['drawer_fronts'],5)
        self.assertTrue(component_review.accepted(updated,design))
        self.assertFalse(component_review.accepted(updated,{**design,'subject':'Five drawer dresser','construction':'five drawers'}))

    def test_advisory_counter_never_clears_real_defects_or_ocr(self):
        from authorized_completion import relieve_review
        q={'decision':'rejected','image_sha256':'pixels','design_sha256':digest({}), 'review_identity':'qa',
           'ocr':{'status':'ok','observations':[]},'ocr_flags':[],
           'vision':{'verdict':'pass','acceptable':True,'visible_text':True,'visible_measurements':False,
                     'geometry_defects':False,'product_matches':True,'piece_count_matches':True,'issues':[]}}
        self.assertEqual(relieve_review(self.db,q,{})['decision'],'rejected')

    def test_advisory_counter_never_reopens_a_direct_visual_rejection(self):
        from authorized_completion import relieve_review
        design={'subject':'Four drawer dresser','construction':'four drawers'}
        q={'decision':'rejected','image_sha256':'pixels','design_sha256':digest(design),'model':'model','review_identity':'qa',
            'ocr':{'status':'ok','observations':[]},'ocr_flags':[],
            'vision':{'verdict':'pass','acceptable':True,'visible_text':False,'visible_measurements':False,
                      'geometry_defects':False,'product_matches':True,'piece_count_matches':True,'issues':[]},
            'component_review':{'drawer_fronts':5,'expected':{'drawer_fronts':4},'confidence':.98},
            'direct_visual_failure':{'observation':'Only two drawers are present.'}}
        self.assertEqual(relieve_review(self.db,q,design),q)

    def test_typed_lighting_preserves_shades_in_the_full_brief(self):
        from authorized_completion import construction_prompt
        design={'subject':'Darien Shaded Classic Chandelier - 4 Lights','product_class':'Chandeliers','material':'Metal','color':'Bronze','construction':''}
        prompt=construction_prompt(design,{},4)
        self.assertIn('individual lampshade',prompt)
        self.assertIn('Darien Shaded Classic',prompt)

    def test_annotation_diagnostics_do_not_repeat_rejected_lettering_in_render_prompts(self):
        from authorized_completion import construction_prompt
        design={'subject':'All-Clad Electrics Slow Cooker','product_class':'Slow Cookers','material':'Metal','color':'Cream'}
        review={'vision':{'visible_text':True,'issues':[
            'The control panel displays the brand name All Clad Electrics and other legible text.',
            'The glass lid is missing its handle.']}}
        prompt=construction_prompt(design,review,5)
        self.assertNotIn('All-Clad',prompt)
        self.assertNotIn('All Clad Electrics',prompt)
        self.assertIn('glass lid is missing its handle',prompt)
        self.assertIn('plain unmarked controls',prompt)
        self.assertEqual(design['subject'],'All-Clad Electrics Slow Cooker')

    def test_annotation_cleanup_preserves_named_artwork_motifs_and_identity_details(self):
        from authorized_completion import construction_prompt
        design={'subject':'Home Sweet Home Bird Houses Printed Wall Décor','product_class':'Wall Décor','material':'Wood','color':'Blue'}
        prompt=construction_prompt(design,{'vision':{'issues':['Visible words read "HOME SWEET HOME".','The required bird houses are missing.']}},4)
        self.assertNotIn('"HOME SWEET HOME"',prompt)
        self.assertIn('Bird Houses Printed Wall',prompt)
        self.assertIn('required bird houses are missing',prompt)

    def test_hamper_fronts_use_bottom_pivots_and_planters_have_mounts(self):
        from authorized_completion import construction_prompt
        hamper={'subject':'freestanding pull-out hamper cabinet','profile':'pullout-hamper','construction':'two separate tilt-out fronts','material':'Wood','color':'Beige'}
        self.assertIn('hinged along its bottom edge',construction_prompt(hamper,{},4))
        planter={'subject':'single empty railing planter with integral brackets','profile':'rail-planter','construction':'rounded rectangular body','material':'Metal','color':'Ivory'}
        self.assertIn('two hooked mounting brackets',construction_prompt(planter,{},4))

    def test_mixed_cabinet_layout_keeps_both_doors_and_drawers(self):
        from authorized_completion import construction_prompt
        design={'subject':'Dule 2 Drawer 2 Door Accent Cabinet','material':'Metal','color':'Black'}
        prompt=construction_prompt(design,{},4)
        self.assertIn('two half-width upper drawers above two lower cupboard doors',prompt)
        self.assertNotIn('two stacked full-width drawers',prompt)

    def test_native_redo_observation_reaches_completion_renderer(self):
        job={'job_id':'job','seed':1,'reference':None,'profile':'dresser','design':{'subject':'Four drawer dresser','material':'Wood','color':'White','construction':'four drawers'},'prompt':product_prompt('White dresser')}
        row={'job_id':'job','request':canonical(job),'state':'rejected','attempts':7,'review':'{}','image_sha256':'pixels'}
        self.db.execute('INSERT INTO manual_reviews VALUES(?,?,?,?)',('job','pixels','rejected','Rebuild the missing upper drawer'))
        with patch('human_keep_acceptance.is_kept',return_value=False):
            p=generation_input(self.run,self.db,row,{'candidate_sha256':'candidate','review_identity':'qa'})
        self.assertIn('Rebuild the missing upper drawer',p['prompt'])

    def test_two_bag_sorters_do_not_infer_two_rows_of_bags(self):
        from authorized_completion import construction_prompt
        d={'subject':'laundry sorting station with plain removable bags','profile':'laundry-sorter','construction':'two bags below a slatted shelf','material':'Wood','color':'White'}
        self.assertIn('exactly two fabric bags side by side in one horizontal row',construction_prompt(d,{},4))

    def test_patterned_variants_change_the_background_without_erasing_motifs(self):
        from authorized_completion import variant_prompt
        job={'design':{'subject':'Night sky constellation kitchen mat','profile':'Kitchen Mats','material':'Polyester','color':'White'},
             'reference':{'value':'White'}}
        prompt=variant_prompt(job)
        self.assertIn('background field',prompt)
        self.assertIn('contrasting',prompt)
        self.assertIn('Only motifs already present',prompt)
        self.assertNotIn('Recolor only the product surfaces',prompt)

    def test_armless_stackable_chair_cannot_become_an_enclosed_armchair(self):
        from authorized_completion import construction_prompt
        d={'subject':'Kool Armless Poly Stackable Chair - Green, Velvet',
           'product_class':'Stackable Chairs','material':'Velvet','color':'Green'}
        p=construction_prompt(d,{},4)
        self.assertIn('No armrests',p)
        self.assertIn('open space beneath the seat',p)
        self.assertIn('seat and back upholstery',p)

    def test_outdoor_set_counts_complete_furniture_not_cushions(self):
        from authorized_completion import construction_prompt
        d={'subject':'Winston Porter Outdoor Loveseat Set - Cream, 6 Pieces',
           'product_class':'Outdoor Conversation Sets','color':'Cream'}
        p=construction_prompt(d,{},4)
        self.assertIn('exactly 6 separate complete furniture assemblies',p)
        self.assertIn('Cushions and decorative pillows never count',p)

    def test_optional_monitor_is_not_added_to_an_empty_riser_variant(self):
        from authorized_completion import variant_prompt
        j={'job_id':'ordinary-riser','profile':'monitor-riser',
           'design':{'color':'Terracotta','profile':'monitor-riser'},'reference':{'value':'Terracotta'}}
        p=variant_prompt(j)
        self.assertIn('empty horizontal top',p)
        self.assertNotIn('neck and foot',p)


    def test_bedding_scene_is_a_print_on_the_actual_sale_unit(self):
        from authorized_completion import construction_prompt
        d={'subject':'Pastel Film Camera - Red, Full','product_class':'Bedding Sets','color':'Red','material':'Cotton'}
        self.assertIn('complete fabric bedding set',construction_prompt(d,{},4))
        self.assertIn('printed on the fabric',construction_prompt(d,{},4))

    def test_old_finish_does_not_contradict_the_requested_variant_in_rendering(self):
        from authorized_completion import construction_prompt
        d={'subject':'Abdulazeez 6 Drawer Double Dresser - White','product_class':'Dressers','color':'Gray','material':'Engineered Wood'}
        before=json.dumps(d,sort_keys=True)
        p=construction_prompt(d,{},4)
        self.assertIn('Gray',p)
        self.assertNotIn(' - White',p)
        self.assertEqual(json.dumps(d,sort_keys=True),before)

    def test_triple_bunk_has_three_sleeping_platforms(self):
        from authorized_completion import construction_prompt
        d={'subject':'Triple Bunk Bed - White, Twin over Twin over Twin','product_class':'Kids Beds','color':'White','material':'Solid Wood'}
        self.assertIn('3 complete sleeping platforms stacked vertically',construction_prompt(d,{},4))

    def test_one_light_chandelier_keeps_its_named_decorative_geometry(self):
        from authorized_completion import construction_prompt
        d={'subject':'Candle Style Empire Chandelier With Crystal Accents - Bronze, 1 Light',
           'product_class':'Chandeliers','color':'Bronze','material':'Metal'}
        p=construction_prompt(d,{},4)
        self.assertIn('clear faceted glass crystal pendants',p)
        self.assertIn('ivory candle sleeve',p)
        self.assertIn('One central bulb only',p)


if __name__=='__main__':unittest.main()
