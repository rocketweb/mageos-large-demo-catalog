import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_cart_rehearsal import verify_positive


class CartAcceptanceTest(unittest.TestCase):
    def fixture(self):
        return {'accepted':True,'exception':None,'message':None,'sku':'parent','selected_sku':'child','qty':1,
                'items':[{'product_id':'1','product_type':'configurable','parent_product_id':None,'item_sku':'child','qty':1,'unit_price':189.99,'row_total':189.99,'has_error':None},
                         {'product_id':'2','product_type':'simple','parent_product_id':'1','item_sku':'child','qty':1,'unit_price':0,'row_total':0,'has_error':None}]}

    def test_exact_selected_child_and_line_price(self):
        verify_positive(self.fixture(),{'parent':'1','child':'2'},189.99)

    def test_wrong_child_identity_or_price_rejected(self):
        for field,value in [('product_id','3'),('parent_product_id','4')]:
            data=copy.deepcopy(self.fixture());data['items'][1][field]=value
            with self.assertRaises(ValueError):verify_positive(data,{'parent':'1','child':'2'},189.99)
        data=self.fixture();data['items'][0]['row_total']=1
        with self.assertRaises(ValueError):verify_positive(data,{'parent':'1','child':'2'},189.99)
