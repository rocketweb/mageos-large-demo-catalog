import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_hyva_options import verify_product


class RenderedOptionsTest(unittest.TestCase):
    def fixture(self):
        labels=['4 Pieces','5 Pieces','6 Pieces','7 Pieces']
        options=[{'id':str(i),'label':label,'products':[str(i+10)]} for i,label in enumerate(labels,1)]
        prices={str(i+10):{'sku':f'child-{i}','price':10*i,'final_price':10*i} for i in range(1,5)}
        config={'productId':'99','attributes':{'215':{'options':options}},
            'index':{str(i+10):{'215':str(i)} for i in range(1,5)},
            'sku':{key:p['sku'] for key,p in prices.items()},
            'optionPrices':{key:{'finalPrice':{'amount':p['price']},'oldPrice':{'amount':p['price']}} for key,p in prices.items()}}
        product={'product_id':'99','config':config}
        product['html']='<script type="application/json">'+json.dumps(config)+'</script><label for="attribute215">Furniture pieces</label><select id="attribute215" name="super_attribute[215]" required @change="reflectOption"><option value="">Choose</option>'
        for option in options:product['html']+=f'<option value="{option["id"]}" data-option-label="{option["label"]}">{option["label"]}</option>'
        product['html']+='</select>'
        return product,labels,prices

    def test_exact_render_and_prices(self):
        product,labels,prices=self.fixture()
        self.assertEqual(verify_product(product,'Furniture pieces',labels,prices),labels)

    def test_old_label_wrong_price_or_embedded_config_rejected(self):
        product,labels,prices=self.fixture()
        for before,after in [('Furniture pieces','Piece Count'),('value="4"','value="9"'),('"productId": "99"','"productId": "98"')]:
            altered=copy.deepcopy(product);altered['html']=altered['html'].replace(before,after)
            with self.assertRaises(ValueError):verify_product(altered,'Furniture pieces',labels,prices)
        prices['11']['final_price']=99
        with self.assertRaises(ValueError):verify_product(product,'Furniture pieces',labels,prices)
