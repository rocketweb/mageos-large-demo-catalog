import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_bulk_visual_repairs import repair_prompt
from verify_bulk_snapshot import verify, sha256


class BulkVerificationTest(unittest.TestCase):
    def test_empty_special_price_is_not_equivalent_to_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def lines(name,rows):
                (root/(name+'.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rows))
            lines('catalog_product_entity',[{'sku':'WANDS-1','entity_id':1,'type_id':'simple'}])
            lines('eav_attribute',[{'attribute_code':'special_price','attribute_id':1,'backend_type':'decimal','frontend_input':'price'},
                                   {'attribute_code':'lab_price_synthetic','attribute_id':2,'backend_type':'int','frontend_input':'boolean'}])
            lines('catalog_product_entity_int',[{'entity_id':1,'attribute_id':2,'store_id':0,'value':1}])
            for name in ['varchar','text','decimal','datetime']:
                lines('catalog_product_entity_'+name,[])
            for name in ['eav_attribute_option_value','catalog_product_super_link','catalog_product_super_attribute']:
                lines(name,[])
            lines('products',[{'sku':'WANDS-1','kind':'simple'}])
            for name in ['simple-updates.csv','parent-content-only.csv','disable-children.csv']:
                with (root/name).open('w') as stream:
                    writer=csv.DictWriter(stream,fieldnames=['sku','special_price','lab_price_synthetic'])
                    writer.writeheader()
                    if name == 'simple-updates.csv':
                        writer.writerow({'sku':'WANDS-1','special_price':'__EMPTY__VALUE__','lab_price_synthetic':'Yes'})
            def manifest():
                (root/'manifest.json').write_text(json.dumps({'missing_skus':[],'captured_at':'fixture','tables':{p.stem:{'sha256':sha256(p)} for p in root.glob('*.jsonl')}}))
            manifest()
            self.assertTrue(verify(root,root,root)['passed'])
            lines('catalog_product_entity_decimal',[{'entity_id':1,'attribute_id':1,'store_id':0,'value':'0.0000'}])
            manifest()
            result=verify(root,root,root)
            self.assertFalse(result['passed'])
            self.assertEqual(result['errors'][0]['field'],'special_price')

    def test_repair_targets_household_textile_not_wearable_skirt(self):
        contract={'root_sku':'WANDS-1','product_name':'Nursery Decor Set','selected_options':{'wands_color':'Blue'},
                  'components':[{'quantity':1,'label':'Crib skirt'}]}
        prompt=repair_prompt({'contract':contract})
        self.assertIn('unfolded as a cross',prompt)
        self.assertIn('not clothing',prompt)

    def test_unaffected_image_is_not_regenerated(self):
        self.assertIsNone(repair_prompt({'contract':{'root_sku':'WANDS-1','product_name':'Round Table','selected_options':{}}}))
