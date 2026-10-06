import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_expanded_catalog import digest
from category_image_corrections import identity as category_identity
class DirectRiserAcceptanceTest(unittest.TestCase):
 def setUp(self):
  self.design={'profile':'monitor-riser','subject':'desktop monitor riser','construction':'side cubby and open center','material':'Bamboo','color':'White'}
  self.job={'profile':'monitor-riser','reference':None,'design':self.design,'design_sha256':digest(self.design)}
  self.review={'image_sha256':'photo','design_sha256':digest(self.design),'review_identity':'review','model':'model','decision':'rejected','ocr':{'status':'ok','observations':[]},'ocr_flags':[],'vision':{'acceptable':False,'confidence':.95,'geometry_defects':False,'visible_text':False,'visible_measurements':False,'product_matches':False,'piece_count_matches':True,'issues':['White coating does not look like bamboo; desk.']}}
  self.category={'image_sha256':'photo','design_sha256':digest(self.design),'identity':category_identity('model'),'result':{'acceptable':True,'confidence':.95,'verdict':'pass','issues':[],**{k:True for k in ('separate_functional_product','product_color_correct','plausible_construction','optional_monitor_correct')}}}
  self.note='Native photograph confirms a separate riser with a broad horizontal load surface, short connected supports, an accessible side cubby and open center, white coating and no annotations. A coating cannot establish the substrate species.'
 def resolve(self):
  from direct_riser_acceptance import resolve
  return resolve(self.review,self.job,self.category,self.note)
 def test_exact_standalone_riser_category_and_native_review_resolve_identity_only(self):
  from direct_riser_acceptance import valid
  result=self.resolve();self.assertEqual(result['decision'],'accepted');self.assertEqual(result['vision'],self.review['vision']);self.assertTrue(valid(result,self.job,'review'));self.assertEqual(self.review['decision'],'rejected')
 def test_annotations_geometry_wrong_count_and_reference_never_clear(self):
  from direct_riser_acceptance import resolve
  for key in ['visible_text','visible_measurements','geometry_defects']:
   q=copy.deepcopy(self.review);q['vision'][key]=True
   with self.assertRaises(ValueError):resolve(q,self.job,self.category,self.note)
  q=copy.deepcopy(self.review);q['vision']['piece_count_matches']=False
  with self.assertRaises(ValueError):resolve(q,self.job,self.category,self.note)
  job={**self.job,'reference':{'job_id':'source'}}
  with self.assertRaises(ValueError):resolve(self.review,job,self.category,self.note)
 def test_category_failure_wrong_class_or_missing_function_never_clear(self):
  from direct_riser_acceptance import resolve
  q=copy.deepcopy(self.category);q['result']['acceptable']=False
  with self.assertRaises(ValueError):resolve(self.review,self.job,q,self.note)
  for job in [{**self.job,'profile':'desk'},{**self.job,'design':{**self.design,'profile':'desk'}}]:
   with self.assertRaises(ValueError):resolve(self.review,job,self.category,self.note)
  with self.assertRaises(ValueError):resolve(self.review,self.job,self.category,'Looks fine.')
 def test_stale_design_image_review_or_tampered_proof_fails(self):
  from direct_riser_acceptance import valid
  q=self.resolve()
  for change in [{'image_sha256':'other'},{'review_identity':'other'},{'vision':{}}]:self.assertFalse(valid({**q,**change},self.job,'review'))
  self.assertFalse(valid(q,{**self.job,'design':{**self.design,'color':'Green'}},'review'))
  r=copy.deepcopy(q);r['direct_riser_acceptance']['observations']='Forged';self.assertFalse(valid(r,self.job,'review'))
 def test_manual_holds_and_human_keeps_are_not_rewritten(self):
  from direct_riser_acceptance import resolve
  for key in ['direct_visual_failure','geometry_hold','human_keep']:
   q={**self.review,key:{'reason':'held'}}
   with self.assertRaises(ValueError):resolve(q,self.job,self.category,self.note)
