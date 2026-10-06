import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_expanded_catalog import digest
import component_review
class DirectComponentResolutionTest(unittest.TestCase):
 def fixture(self):
  design={'subject':'Eskew 7 Drawer Dresser','color':'Gray'}
  original={'decision':'rejected','image_sha256':'a'*64,'design_sha256':digest(design),'review_identity':'review','model':'model','ocr':{'status':'ok','observations':[]},'ocr_flags':[],
   'vision':{'acceptable':True,'visible_text':False,'visible_measurements':False,'geometry_defects':False,'product_matches':True,'piece_count_matches':True},
   'component_review':{'identity':component_review.identity('model'),'expected':{'drawer_fronts':7},'drawer_fronts':8,'confidence':.95}}
  proof={'version':'direct-component-resolution-v1','reviewer':'direct_visual_inspection','image_sha256':original['image_sha256'],'design_sha256':digest(design),'review_identity':'review','observed':{'drawer_fronts':7},'drawer_fronts_by_row':[3,2,1,1],'observations':'Three upper fronts, two middle fronts and two separate full-width lower fronts; complete seams visible.','original_review':original}
  review={**original,'decision':'accepted','direct_component_resolution':proof,'direct_component_resolution_sha256':digest(proof)}
  return design,review
 def test_direct_front_count_resolves_only_false_component_count(self):
  d,r=self.fixture();self.assertTrue(component_review.accepted(r,d))
  self.assertEqual(r['component_review']['drawer_fronts'],8)
 def test_stale_or_unmatched_or_incomplete_resolution_cannot_pass(self):
  for change in ('hash','design','count','layout','annotation','general','digest','no_expected','direct_hold','geometry_hold'):
   d,r=self.fixture();p=r['direct_component_resolution']
   if change=='hash':p['image_sha256']='b'*64
   elif change=='design':d['color']='White'
   elif change=='count':p['observed']['drawer_fronts']=6
   elif change=='layout':p['drawer_fronts_by_row']=[3,2,2,1]
   elif change=='annotation':p['original_review']['ocr_flags']=[{'text':'cm'}]
   elif change=='general':p['original_review']['vision']['acceptable']=False
   elif change=='no_expected':d['subject']='Chest'
   elif change=='direct_hold':p['original_review']['direct_visual_failure']={'observations':'Wrong product shape.'};r['direct_visual_failure']=p['original_review']['direct_visual_failure']
   elif change=='geometry_hold':p['original_review']['geometry_hold']={'required':'Direct shape inspection'};r['geometry_hold']=p['original_review']['geometry_hold']
   elif change=='digest':r['direct_component_resolution_sha256']='invalid'
   if change!='digest':r['direct_component_resolution_sha256']=digest(p)
   self.assertFalse(component_review.accepted(r,d),change)
 def test_direct_component_proof_cannot_bypass_table_count(self):
  d,r=self.fixture();d.update(subject='3 Piece Coffee Table Set',product_class='Living Room Table Sets');self.assertFalse(component_review.accepted(r,d))

 def test_resolver_preserves_original_and_refuses_other_qa_failures(self):
  from direct_component_resolution import resolve
  d,r=self.fixture();original=copy.deepcopy(r['direct_component_resolution']['original_review'])
  resolved=resolve(original,d,{'drawer_fronts':7},'Three, two, one and one complete drawer fronts.',[3,2,1,1])
  self.assertTrue(component_review.accepted(resolved,d));self.assertEqual(original['decision'],'rejected')
  self.assertEqual(resolved['component_review']['drawer_fronts'],8)
  original['vision']['geometry_defects']=True
  with self.assertRaises(ValueError):resolve(original,d,{'drawer_fronts':7},'Three, two, one and one.',[3,2,1,1])
