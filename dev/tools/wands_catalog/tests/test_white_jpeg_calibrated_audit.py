import json
from pathlib import Path
import sys
import unittest

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import white_jpeg_audit as old
import white_jpeg_calibrated_audit as new

JOB=Path(__file__).resolve().parents[4]/'var/catalog-expansion-20260918/white-jpeg-bulk-20261012'


class CalibratedAuditTest(unittest.TestCase):
    def test_removed_shadow_does_not_reject_the_real_wood_table(self):
        examples=json.loads((JOB/'rejection-review-20261017T231350Z/chosen-examples.json').read_text())
        item=examples[1]
        with Image.open(item['original']) as a,Image.open(item['processed']) as b:
            a=a.convert('RGB');b=b.convert('RGB');m={**old.metrics(a,b),**new.features(a,b)}
        self.assertIsNone(new.screen({'output_file':'candidate.jpg'},m))

    def test_gradual_studio_backdrop_does_not_reject_the_real_blue_shelf(self):
        item=json.loads((JOB/'rejection-review-20261017T231350Z/chosen-examples.json').read_text())[0]
        with Image.open(item['original']) as a,Image.open(item['processed']) as b:
            a=a.convert('RGB');b=b.convert('RGB');m={**old.metrics(a,b),**new.features(a,b)}
        self.assertIsNone(new.screen({'output_file':'candidate.jpg'},m))

    def test_no_white_approval_without_an_individual_review(self):
        m={'white_border':1,'backdrop_fit_p90':2,'border_edge_fraction':0}
        self.assertEqual(new.choose({'output_file':'candidate.jpg'},m,None)[0],'pending')

    def test_erased_white_panel_is_rejected_despite_perfect_pixel_scores(self):
        m={'white_border':1,'backdrop_fit_p90':2,'border_edge_fraction':0}
        review={'background':'studio','confidence':1,'product_preserved':False,'white_background':True}
        self.assertEqual(new.choose({'output_file':'candidate.jpg'},m,review)[0],'original')

    def test_actual_room_scene_keeps_original_even_if_product_is_preserved(self):
        m={'white_border':1,'backdrop_fit_p90':2,'border_edge_fraction':0}
        review={'background':'scene','confidence':1,'product_preserved':True,'white_background':True}
        self.assertEqual(new.choose({'output_file':'candidate.jpg'},m,review)[0],'original')


class RegionSafetyRegressionTest(unittest.TestCase):
    def test_all_three_actual_unsafe_primary_approvals_require_more_evidence(self):
        audit=JOB/'audit-calibrated-20261017'
        items={r['index']:r for r in json.loads((audit/'reference/archive-v2/holdout.json').read_text())}
        primary=json.loads((audit/'reference/evaluations/c8b7611565a42284/holdout-results.json').read_text())
        for n in (73,75,87):
            with self.subTest(index=n):
                item=items[n];row=item['row'];a,b=new.load_pair(JOB,row);m=new.features(a,b)
                self.assertTrue(m['risk_regions'])
                review=primary[row['file']]['review']
                self.assertIs(review['product_preserved'],True)
                self.assertIn(new.choose(row,m,review)[0],{'original','pending'})

    def test_missing_or_uncertain_region_evidence_cannot_approve_a_cutout(self):
        import white_jpeg_region_review as regions
        row={'source_sha256':'original','output_sha256':'candidate','output_file':'candidate.jpg'}
        risks=[{'crop':[0,0,100,100]}]
        m={'risk_regions':risks,'white_border':1,'backdrop_fit_p90':2,'border_edge_fraction':0}
        primary={'background':'studio','confidence':.99,'product_preserved':True,'white_background':True,'reason':'Parts retained.'}
        self.assertEqual(new.choose(row,m,primary)[0],'pending')
        evidence={'identity':regions.identity(new.MODEL),'source_sha256':'original','output_sha256':'candidate',
                  'reviews':[{'crop':risks[0]['crop'],'review':{'verdict':'uncertain','confidence':.85,'reason':'Possible erased panel.'}}]}
        self.assertEqual(new.choose(row,m,primary,evidence)[0],'original')
        evidence['reviews'][0]['review']={'verdict':'safe_background','confidence':.99,'reason':'Verified plain backdrop through open frame.'}
        self.assertEqual(new.choose(row,m,primary,evidence)[0],'white')
        primary['product_preserved']=False
        self.assertEqual(new.choose(row,m,primary,evidence)[0],'original')

class SmallChangedRegionRegressionTest(unittest.TestCase):
    def test_measured_new_edges_cannot_bypass_focused_verification(self):
        audit=JOB/'audit-calibrated-20261017'
        items={r['index']:r for r in json.loads((audit/'reference/archive-v3/holdout.json').read_text())}
        old_results=json.loads((audit/'reference/evaluations/fcea5b1faacb3210/holdout-results.json').read_text())
        for n in (31,49):
            with self.subTest(index=n):
                row=items[n]['row'];a,b=new.load_pair(JOB,row);m=new.features(a,b)
                self.assertGreaterEqual(m['novel_edge_component_max'],32)
                self.assertTrue(m['risk_regions'],'A native edge anomaly must produce a review region')
                self.assertNotEqual(new.choose(row,m,old_results[row['file']]['review'])[0],'white')

class PrimaryConfidenceSafetyTest(unittest.TestCase):
    def test_lower_confidence_primary_approval_keeps_original(self):
        m={'risk_regions':[],'white_border':1,'backdrop_fit_p90':2,'border_edge_fraction':0}
        row={'output_file':'candidate.jpg','source_sha256':'source','output_sha256':'candidate'}
        review={'background':'studio','confidence':.90,'product_preserved':True,'white_background':True,'reason':'Possibly intact.'}
        self.assertEqual(new.choose(row,m,review)[0],'original')

    def test_source_eligibility_is_separate_from_accepting_a_processed_image(self):
        m={'risk_regions':[],'backdrop_fit_p90':2,'border_edge_fraction':0}
        source={'source_sha256':'source','output_file':None}
        review={'background':'studio','confidence':.90,'product_preserved':None,
                'white_background':None,'reason':'Plain seamless studio backdrop.'}
        self.assertEqual(new.choose(source,m,review)[0],'eligible')
        review['background']='scene'
        self.assertEqual(new.choose(source,m,review)[0],'original')
        review['background']='uncertain'
        self.assertEqual(new.choose(source,m,review)[0],'original')
        review['background']='studio';review['confidence']=.85
        self.assertEqual(new.choose(source,m,review)[0],'original')

if __name__=='__main__':unittest.main()
