import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_hyva_browser_components import check_state


class BrowserAcceptanceTest(unittest.TestCase):
    def fixture(self):
        cases=[{'option_id':str(i),'label':f'{i} Pieces','child_id':str(i+10),'sku':f'child-{i}','price':100.0+i} for i in range(4,8)]
        product={'product_id':'99','attribute_id':'215','initial_price':104.0,'cases':cases}
        case=cases[-1]
        state={'errors':[],'overflow':False,'priceText':'$107.00','valid':True,'value':'7',
            'options':[{'value':'','text':'Choose','disabled':False}]+[{'value':c['option_id'],'text':c['label'],'disabled':False} for c in cases],
            'selection':{'productId':'99','optionId':'215','value':'7','productIndex':'17','candidates':['17'],'skuCandidates':['child-7']},
            'priceEvent':{'amount':107.0,'isMinimalPrice':False}}
        return state,product,case

    def test_native_dom_and_event_contract(self):
        state,product,case=self.fixture();check_state(state,product,case)
        state.update(priceText='$104.00',valid=False,value='',priceEvent={'amount':104.0,'isMinimalPrice':True})
        check_state(state,product,reset=True)

    def test_wrong_visible_price_child_or_browser_error_rejected(self):
        state,product,case=self.fixture()
        for field,value in [('priceText','$104.00'),('errors',['Alpine failed']),('overflow',True),('valid',False)]:
            wrong=copy.deepcopy(state);wrong[field]=value
            with self.assertRaises(ValueError):check_state(wrong,product,case)
        wrong=copy.deepcopy(state);wrong['selection']['skuCandidates']=['wrong']
        with self.assertRaises(ValueError):check_state(wrong,product,case)
        wrong=copy.deepcopy(state);wrong['options'][1]['disabled']=True
        with self.assertRaises(ValueError):check_state(wrong,product,case)
