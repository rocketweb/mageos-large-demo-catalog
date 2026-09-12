from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import preflight_pilot_media as preflight
from preflight_pilot_media import inverse, inspect
from prepare_catalog import sha256


class MediaPreflightTest(unittest.TestCase):
    def tables(self):
        return {'catalog_product_entity':[{'entity_id':'1','sku':'WANDS-A','type_id':'simple'},{'entity_id':'2','sku':'WANDS-B','type_id':'simple'}],
                'eav_attribute':[{'attribute_id':str(i),'attribute_code':n,'backend_type':'varchar'} for i,n in enumerate(('image','small_image','thumbnail','image_label','small_image_label','thumbnail_label','name','description','lab_sale_unit'),1)],
                'catalog_product_entity_varchar':[{'value_id':'3','entity_id':'1','attribute_id':'4','store_id':'0','value':'old label'},
                                                  {'value_id':'4','entity_id':'2','attribute_id':'1','store_id':'0','value':'keep.jpg'}],
                'catalog_product_entity_media_gallery_value':[], 'catalog_product_entity_media_gallery_value_to_entity':[],
                'catalog_product_entity_media_gallery':[], 'catalog_product_entity_text':[], 'catalog_product_entity_int':[],
                'catalog_product_super_link':[], 'catalog_product_website':[], 'eav_attribute_option_value':[]}

    def test_inverse_restores_labels_and_excludes_context_products(self):
        sql=inverse(self.tables(),{'database':'lab','prefix':''},{'WANDS-A'})
        self.assertIn('6f6c64206c6162656c',sql)
        self.assertNotIn('6b6565702e6a7067',sql)
        self.assertNotIn('DELETE FROM `lab`.`catalog_product_entity_media_gallery` ',sql)
        self.assertTrue(sql.rstrip().endswith('ROLLBACK;'))

    def test_missing_target_or_definition_drift_blocks(self):
        a=[{'target_sku':'WANDS-A','expected_type':'simple','expected_definition_fields':{'name':'New name'},'selected_options':{},'fields':{}}]
        result=inspect(a,{'skus':['WANDS-A','WANDS-B'],'intended_types':{'WANDS-A':'simple','WANDS-B':'simple'},'configurable_links':{}},self.tables())
        self.assertTrue(any(i['code']=='definition_mismatch' for i in result['issues']))
        a[0]['target_sku']='WANDS-MISSING'
        result=inspect(a,{'skus':['WANDS-A','WANDS-B'],'intended_types':{'WANDS-A':'simple','WANDS-B':'simple'},'configurable_links':{}},self.tables())
        self.assertTrue(any(i['code']=='missing_target' for i in result['issues']))

    def test_configurable_axes_and_option_ownership_must_match(self):
        tables=self.tables()
        tables['eav_attribute'].append({'attribute_id':'10','attribute_code':'finish'})
        tables['eav_attribute_option_value']=[{'option_id':'8','store_id':'0','value':'Bronze'}]
        tables['eav_attribute_option']=[{'option_id':'8','attribute_id':'999'}]
        tables['catalog_product_entity_int']=[{'entity_id':'1','attribute_id':'10','store_id':'0','value':'8'}]
        tables['catalog_product_super_attribute']=[]
        request={'skus':['WANDS-A','WANDS-B'],'intended_types':{},'configurable_links':{},'configurable_axes':{'WANDS-B':['finish']}}
        assignments=[{'target_sku':'WANDS-A','expected_definition_fields':{},'selected_options':{'finish':'Bronze'},'fields':{}}]
        issues={r['code'] for r in inspect(assignments,request,tables)['issues']}
        self.assertIn('configurable_axes_mismatch',issues)
        self.assertIn('selected_option_owner_mismatch',issues)

    def test_upload_plan_is_exact_hash_checked_and_non_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'sample.jpg';source.write_bytes(b'jpeg fixture')
            rows=[{'target_sku':'WANDS-A','image':{'file':'sample.jpg','sha256':sha256(source),'bytes':source.stat().st_size},
                   'fields':{'base_image':'/wands/pilot-media-v1/sample.jpg'}}]
            plan=preflight.upload_plan(rows,root)
            self.assertEqual(plan['files'][0]['source'],str(source.resolve()))
            self.assertEqual(plan['files'][0]['destination'],'/opt/comtom/stores/relevance/src/pub/media/import/wands/pilot-media-v1/sample.jpg')
            self.assertFalse(plan['overwrite_existing'])
            self.assertFalse(plan['uploaded'])
            source.write_bytes(b'changed')
            with self.assertRaises(ValueError):preflight.upload_plan(rows,root)

    def test_upload_plan_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=[{'target_sku':'WANDS-A','image':{'file':'../escape.jpg'},'fields':{}}]
            with self.assertRaises(ValueError):preflight.upload_plan(rows,Path(tmp))


if __name__=='__main__':unittest.main()
