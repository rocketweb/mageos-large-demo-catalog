import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_inventory_lifecycle import check_nursery_inventory


class InventoryAcceptanceTest(unittest.TestCase):
    def evidence(self):
        return {'sku':'WANDS-000056','type':'simple','status':1,'errors':[],
                'checks':{'model_is_salable':True,'inventory_is_salable':True,'salable_quantity':47,
                          'requested_1':{'salable':True,'error_codes':[]},
                          'requested_47':{'salable':True,'error_codes':[]},
                          'requested_48':{'salable':False,'error_codes':['is_salable_with_reservations-not_enough_qty']}}}

    def test_seed_available_and_overorder_rejected(self):
        check_nursery_inventory(self.evidence())

    def test_stale_index_rejected_even_when_general_salable_flag_is_true(self):
        broken=self.evidence();broken['checks']['salable_quantity']=0
        with self.assertRaises(ValueError):check_nursery_inventory(broken)

    def test_quantity_boundary_must_be_enforced(self):
        for qty in (1,47,48):
            broken=copy.deepcopy(self.evidence())
            broken['checks']['requested_'+str(qty)]['salable']=qty==48
            with self.assertRaises(ValueError):check_nursery_inventory(broken)
