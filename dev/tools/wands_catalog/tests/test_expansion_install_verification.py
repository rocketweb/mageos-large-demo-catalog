import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_expansion_install import compare

class InstallVerificationTest(unittest.TestCase):
 def setUp(self):
  self.before={'schema':2,'root':'/var/www/html','website_id':2,'store_id':2,'shared_wands_skus':[],
   'products':{'WANDS-P':{'id':1,'type':'configurable','websites':[2],'wands':True},'WANDS-C':{'id':2,'type':'simple','websites':[2],'wands':True},'OTHER':{'id':3,'type':'simple','websites':[1],'wands':False}},
   'protected':{'config':{'rows':1,'sha256':'protected'}},'configurable_links':[{'parent':'WANDS-P','child':'WANDS-C'}],
   'existing_wands_stock':{'cataloginventory_stock_item':[{'item_id':'1','product_id':'2','qty':'7.0000'}],'inventory_source_item':[{'source_item_id':'1','sku':'WANDS-C','quantity':'7.0000'}]}}
  self.after=copy.deepcopy(self.before);self.after['products']['WANDS-NEW']={'id':4,'type':'simple','websites':[2],'wands':True}
  self.after['configurable_links'].append({'parent':'WANDS-P','child':'WANDS-NEW'})
  self.after['existing_wands_stock']['cataloginventory_stock_item'].append({'item_id':'2','product_id':'4','qty':'8.0000'})
  self.after['existing_wands_stock']['inventory_source_item'].append({'source_item_id':'2','sku':'WANDS-NEW','quantity':'8.0000'})
  self.desired={'WANDS-P':{'product_type':'configurable'},'WANDS-C':{'product_type':'simple'},'WANDS-NEW':{'product_type':'simple'}}
  self.links={('WANDS-P','WANDS-C'),('WANDS-P','WANDS-NEW')}
 def test_accepts_exact_expansion_with_existing_stock_and_other_products_preserved(self):
  self.assertTrue(compare(self.before,self.after,self.desired,self.links)['passed'])
 def test_catches_old_stock_mutation_missing_relationship_and_unrelated_change(self):
  self.after['existing_wands_stock']['cataloginventory_stock_item'][0]['qty']='0.0000'
  self.after['configurable_links'].pop();self.after['products']['OTHER']['type']='virtual'
  report=compare(self.before,self.after,self.desired,self.links)
  self.assertFalse(report['passed']);self.assertEqual(report['changed_existing_stock_rows']['cataloginventory_stock_item'],1)
  self.assertEqual(report['missing_links'],1);self.assertEqual(report['unrelated_product_changes'],1)
 def test_catches_wrong_website_and_protected_data_change(self):
  self.after['products']['WANDS-NEW']['websites']=[1,2];self.after['protected']['config']['sha256']='changed'
  report=compare(self.before,self.after,self.desired,self.links)
  self.assertFalse(report['passed']);self.assertEqual(report['incorrect_product_websites'],1);self.assertEqual(report['changed_protected_tables'],['config'])
