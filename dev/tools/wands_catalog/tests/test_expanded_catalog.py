import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_expanded_catalog import make_design, product_row, image_job, variations, encode_variations, extension_candidates, normalize_category
from expansion_profiles import EXISTING, EXISTING_QUOTAS, EXPANSIONS
from image_policy import validate_prompt, product_prompt, GuardedImageModel
from image_review import parse_review


class ExpandedCatalogTest(unittest.TestCase):
    def test_approved_quotas_are_complete(self):
        self.assertEqual(sum(q[0] for q in EXISTING_QUOTAS.values()),27000)
        self.assertEqual(sum(q[1] for q in EXISTING_QUOTAS.values()),1000)
        self.assertEqual(sum(q[1]+4*q[2] for q in EXPANSIONS.values()),18844)
        self.assertEqual(sum(q[2] for q in EXPANSIONS.values()),1000)
        self.assertEqual(sum(len(q[3]) for q in EXPANSIONS.values()),32)

    def test_designs_vary_physical_identity_not_just_name_or_color(self):
        for profile in [p for profiles in EXISTING.values() for p in profiles]:
            seen=set()
            for index in range(600):
                d=make_design(profile,index,'Rugs','WANDS Catalog/Rugs','WANDS-SYN-S-X','existing-categories')
                signature=(d['subject'],d['material'],d['construction'],tuple(d['dimensions_cm'].items()))
                self.assertNotIn(signature,seen)
                seen.add(signature)
                if profile.key=='round-rug':self.assertEqual(d['dimensions_cm']['width'],d['dimensions_cm']['depth'])

    def test_dimension_metadata_survives_without_entering_image_prompt(self):
        d=make_design(EXISTING['Furniture'][0],0,'Furniture','WANDS Catalog/Furniture','WANDS-SYN-S-X','existing-categories')
        row=product_row(d);job=image_job(d,[d['sku']])
        self.assertIn('lab_spec_width_cm',row)
        self.assertIn('fictional lab specifications',row['description'])
        validate_prompt(job['prompt'])
        self.assertFalse(row['wands_product_id'])
        self.assertFalse(row['wands_review_count'])

    def test_parent_has_no_single_size_for_variable_children(self):
        d=make_design(EXISTING['Furniture'][0],0,'Furniture','WANDS Catalog/Furniture','WANDS-SYN-P-X','existing-categories')
        parent=product_row(d,parent=True)
        a=product_row(d,options={'color':'Black','wands_size':'Small'},scale=.85)
        b=product_row(d,options={'color':'Black','wands_size':'Large'},scale=1.15)
        self.assertNotIn('lab_spec_width_cm',parent)
        self.assertLess(float(a['lab_spec_width_cm']),float(b['lab_spec_width_cm']))
        self.assertEqual(a['visibility'],'Not Visible Individually')
        self.assertEqual(a['categories'],'')

    def test_relationship_round_trip_and_duplicate_field_rejection(self):
        groups=[{'sku':'CHILD','color':'Black','wands_size':'Small'}]
        self.assertEqual(variations({'sku':'P','configurable_variations':encode_variations(groups)}),groups)
        with self.assertRaises(ValueError):variations({'sku':'P','configurable_variations':'sku=C,color=Black,color=White'})

    def test_category_punctuation_does_not_create_duplicate_tree(self):
        self.assertEqual(normalize_category('WANDS Catalog/Pet/Litter-Box Furniture'),normalize_category('WANDS Catalog/Pet/Litter Box Furniture'))

    def test_old_unsafe_generation_queue_is_rejected_before_model_call(self):
        class Model:
            def generate_image(self,**kwargs):raise AssertionError('Unsafe prompt reached model')
        with self.assertRaises(ValueError):GuardedImageModel(Model()).generate_image(prompt='Draw a 12 inch chair with dimension labels')
        with self.assertRaises(ValueError):validate_prompt(product_prompt('one chair'),view='dimensions')


class ReviewGateTest(unittest.TestCase):
    def good(self):
        return {'verdict':'pass','confidence':.99,'visible_measurements':False,'visible_text':False,
                'geometry_defects':False,'product_matches':True,'piece_count_matches':True,
                'observed_product':'One coherent wooden chair, no markings.','issues':[]}

    def parse(self,value):
        import json
        return parse_review(json.dumps(value))

    def test_pass_word_cannot_override_measurements_or_missing_evidence(self):
        good=self.good();self.assertTrue(self.parse(good)['acceptable'])
        for flag in ['visible_measurements','visible_text','geometry_defects']:
            value={**good,flag:True};self.assertFalse(self.parse(value)['acceptable'])
        for field in good:
            value=copy.deepcopy(good);del value[field]
            with self.assertRaises(ValueError):self.parse(value)

    def test_uncertain_low_confidence_or_string_booleans_never_pass(self):
        for change in [{'verdict':'uncertain'},{'confidence':.89},{'product_matches':False},{'issues':['possible ruler']}]:
            self.assertFalse(self.parse({**self.good(),**change})['acceptable'])
        with self.assertRaises(ValueError):self.parse({**self.good(),'visible_measurements':'false'})


if __name__=='__main__':unittest.main()
