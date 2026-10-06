import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_expansion_install_verification import InstallVerificationTest
from catalog_reconciliation import verify_partial
class ReconciliationTest(InstallVerificationTest):
    def test_exact_partial_prefix_preserves_original_stock_and_ids(self):
        self.after['configurable_links']=copy.deepcopy(self.before['configurable_links'])
        self.assertEqual(verify_partial(self.before,self.after,self.desired,{'WANDS-NEW'},{'WANDS-NEW'}),['WANDS-NEW'])
    def test_unexamined_added_products_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'exact applied batches'):verify_partial(self.before,self.after,self.desired,set(),set())
    def test_changed_existing_stock_is_rejected(self):
        self.after['configurable_links']=copy.deepcopy(self.before['configurable_links'])
        self.after['existing_wands_stock']['cataloginventory_stock_item'][0]['qty']='0'
        with self.assertRaisesRegex(ValueError,'protected data'):verify_partial(self.before,self.after,self.desired,{'WANDS-NEW'},{'WANDS-NEW'})
