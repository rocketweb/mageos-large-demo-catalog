import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_pricing_lifecycle import check_price_rows


class PricingAcceptanceTest(unittest.TestCase):
    def fixture(self):
        rows=[{'sku':'WANDS-000056','price':74.99,'final_price':63.74,'min_price':63.74,'max_price':63.74},
              {'sku':'parent','price':174.99,'final_price':174.99,'min_price':134.99,'max_price':209.99},
              {'sku':'child1','price':134.99,'final_price':134.99,'min_price':134.99,'max_price':134.99},
              {'sku':'child2','price':209.99,'final_price':209.99,'min_price':209.99,'max_price':209.99}]
        products=[{'sku':r['sku'],'type':'configurable' if r['sku']=='parent' else 'simple','base_price':r['price'],
                   'checks':{'pricing_final':r['min_price'],'model_final':r['min_price']}} for r in rows]
        return products,rows,{'parent':['child1','child2']}

    def test_parent_range_and_simple_promotion(self):
        check_price_rows(*self.fixture())

    def test_stale_promotion_or_range_rejected(self):
        for sku,field in [('WANDS-000056','final_price'),('parent','max_price')]:
            data=copy.deepcopy(self.fixture())
            next(r for r in data[1] if r['sku']==sku)[field]=0
            with self.assertRaises(ValueError):check_price_rows(*data)
