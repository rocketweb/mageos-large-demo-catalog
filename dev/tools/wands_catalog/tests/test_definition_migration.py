import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_definition_migration import activation, row_operation


class MigrationPlanTest(unittest.TestCase):
    def test_row_operation_preserves_unmodified_fields(self):
        before={'value_id':1,'entity_id':1257,'attribute_id':7,'store_id':0,'value':'109.990000'}
        op=row_operation('catalog_product_entity_decimal',before,{'value':'74.990000'})
        self.assertEqual(op['after']['value'],'74.990000')
        self.assertEqual(op['after']['entity_id'],1257)
        self.assertEqual(before['value'],'109.990000')
        self.assertEqual(op['selector'],{'value_id':1})

    def test_nursery_activation_rejects_stale_seed_and_promotional_dates(self):
        tables={'eav_attribute':[{'attribute_id':i,'attribute_code':c} for i,c in enumerate(('price','special_price','weight','special_from_date','special_to_date'),1)],
                'cataloginventory_stock_item':[{'item_id':1,'product_id':1257,'qty':'0.0000','manage_stock':0,'use_config_manage_stock':1},
                                               {'item_id':2,'product_id':10,'qty':'47.0000'}],
                'inventory_source_item':[{'source_item_id':1,'source_code':'default','sku':'WANDS-000056','quantity':'0.0000','status':1},
                                         {'source_item_id':2,'source_code':'default','sku':'WANDS-000056-TODDLER-56FF','quantity':'47.0000','status':1}],
                'catalog_product_entity_decimal':[{'value_id':1,'entity_id':1257,'attribute_id':1,'store_id':0,'value':'109.990000'},
                                                  {'value_id':2,'entity_id':1257,'attribute_id':3,'store_id':0,'value':None}],
                'catalog_product_entity_datetime':[]}
        entities={'WANDS-000056':{'entity_id':1257},'WANDS-000056-TODDLER-56FF':{'entity_id':10}}
        self.assertEqual(len(activation(tables,entities)),5)
        tables['cataloginventory_stock_item'][1]['qty']='46.0000'
        with self.assertRaises(ValueError):activation(tables,entities)
        tables['cataloginventory_stock_item'][1]['qty']='47.0000'
        tables['catalog_product_entity_datetime']=[{'entity_id':1257,'attribute_id':4,'store_id':2,'value':'2027-01-01 00:00:00'}]
        with self.assertRaises(ValueError):activation(tables,entities)


if __name__=='__main__':unittest.main()
