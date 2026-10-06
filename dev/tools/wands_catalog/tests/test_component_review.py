import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from component_review import required_counts,parse_counts,accepted,identity

class ComponentReviewTest(unittest.TestCase):
 def test_coffee_table_set_requires_independent_complete_table_count(self):
  import component_review
  design={'subject':'Addyson Living Room 3 Piece Coffee Table Set','product_class':'Living Room Table Sets'}
  self.assertFalse(accepted({'model':'model'},design))
  evidence={'identity':component_review.table_identity('model'),'expected':3,'confidence':.98,'complete_tables':2,'evidence':'Two separate complete tables.'}
  self.assertFalse(accepted({'model':'model','table_component_review':evidence},design))
  evidence['complete_tables']=3
  self.assertTrue(accepted({'model':'model','table_component_review':evidence},design))
  evidence['identity']='stale'
  self.assertFalse(accepted({'model':'model','table_component_review':evidence},design))
 def test_table_counter_cannot_be_primed_by_target_quantity(self):
  import component_review
  self.assertNotIn('three',component_review.TABLE_SYSTEM.lower())
  self.assertNotIn('expected',component_review.TABLE_SCHEMA['properties'])
  self.assertEqual(component_review.required_table_count({'subject':'3 Piece Coffee Table Set','product_class':'Living Room Table Sets'}),3)
  self.assertIsNone(component_review.required_table_count({'subject':'3 Piece Bedding Set','product_class':'Bedding Sets'}))
  with self.assertRaises(ValueError):component_review.parse_table_counts(json.dumps({'complete_tables':True,'confidence':.99,'evidence':'Tables.'}))
 def test_extracts_components_without_confusing_dimensions(self):
  self.assertEqual(required_counts({'subject':'9 Drawer dresser, 36 in'}),{'drawer_fronts':9})
  self.assertEqual(required_counts({'subject':'Cabinet','construction':'two plain doors'}),{'cupboard_doors':2})
  self.assertEqual(required_counts({'subject':'4 in bowl'}),{})
 def test_handles_cannot_substitute_for_distinct_drawer_fronts(self):
  design={'subject':'9 Drawer dresser'}
  check={'identity':identity('model'),'expected':{'drawer_fronts':9},'confidence':.98,'drawer_fronts':5}
  self.assertFalse(accepted({'model':'model','component_review':check},design))
  check['drawer_fronts']=9
  self.assertTrue(accepted({'model':'model','component_review':check},design))
  self.assertFalse(accepted({'model':'model'},design))
 def test_strict_evidence(self):
  with self.assertRaises(ValueError):parse_counts(json.dumps({'drawer_fronts':9}))
  value={'drawer_fronts':5,'cupboard_doors':None,'shelf_levels':None,'confidence':.98,'evidence':'Three top drawers and two wide lower drawers.'}
  self.assertEqual(parse_counts(json.dumps(value)),value)
  value['drawer_fronts']=True
  with self.assertRaises(ValueError):parse_counts(json.dumps(value))
 def test_explicit_shelf_count_requires_independent_matching_evidence(self):
  design={'subject':'Rolling work cart','visible_component_counts':{'shelf_levels':3}}
  self.assertEqual(required_counts(design),{'shelf_levels':3})
  check={'identity':identity('model'),'expected':{'shelf_levels':3},'confidence':.98,'shelf_levels':4}
  self.assertFalse(accepted({'model':'model','component_review':check},design))
  check['shelf_levels']=3
  self.assertTrue(accepted({'model':'model','component_review':check},design))
  self.assertFalse(accepted({'model':'model'},design))
 def test_open_storage_counts_exclude_top_caps_without_priming_quantity(self):
  import component_review
  design={'profile':'desktop-shelf','construction':'two open shelves'}
  self.assertEqual(component_review.count_scope(design),'internal_open_storage')
  self.assertIsNone(component_review.count_scope({'profile':'work-cart','construction':'two open shelves and casters'}))
  scope=component_review.count_scope(design)
  self.assertNotIn('two',component_review.count_system(scope))
  check={'identity':identity('model'),'expected':{'shelf_levels':2},'confidence':.98,'shelf_levels':2}
  self.assertFalse(accepted({'model':'model','component_review':check},design))
  check.update(scope=scope,identity=identity('model',scope))
  self.assertTrue(accepted({'model':'model','component_review':check},design))
 def test_accessory_compatibility_quantity_is_not_included_furniture(self):
  self.assertEqual(required_counts({'subject':'Evelots 1 Door Draft Stopper'}),{})
  self.assertEqual(required_counts({'subject':'2 Drawer Pulls'}),{})
  self.assertEqual(required_counts({'subject':'4 Shelf Brackets'}),{})
  self.assertEqual(required_counts({'subject':'Bi Fold Closet 4 Door Snugger'}),{})
  self.assertEqual(required_counts({'subject':'2 Door Cabinet With Brass Handles'}),{'cupboard_doors':2})
 def test_named_shelf_quantity_requires_matching_useful_levels(self):
  design={'subject':'Berenice 4 - Shelf Storage Cabinet'}
  self.assertEqual(required_counts(design),{'shelf_levels':4})
  check={'identity':identity('model'),'expected':{'shelf_levels':4},'confidence':.98,'shelf_levels':3}
  self.assertFalse(accepted({'model':'model','component_review':check},design))
  check['shelf_levels']=4
  self.assertTrue(accepted({'model':'model','component_review':check},design))
  self.assertEqual(required_counts({'construction':'three open shelves'}),{'shelf_levels':3})
  self.assertEqual(required_counts({'subject':'4 inch shelf bracket'}),{})
  self.assertEqual(required_counts({'subject':'Shelf pack of four'}),{})
  with self.assertRaises(ValueError):required_counts({'subject':'4 shelf cabinet','visible_component_counts':{'shelf_levels':3}})
 def test_explicit_counts_reject_unknown_fields_and_conflicts(self):
  for counts in ({'unknown_parts':3},{'shelf_levels':True},{'shelf_levels':-1},['shelf_levels']):
   with self.assertRaises(ValueError):required_counts({'visible_component_counts':counts})
  with self.assertRaises(ValueError):
   required_counts({'subject':'9 Drawer dresser','visible_component_counts':{'drawer_fronts':5}})
