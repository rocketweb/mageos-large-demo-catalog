import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from catalog_repairs import repair_family
from repair_designs import rules
from verify_catalog_repairs import verify_operations
from test_catalog_repairs import family


class VerifyCatalogRepairsTest(unittest.TestCase):
    def packet_records(self):
        root,children=family('WANDS-011451',{'wands_size':['Toddler','Twin','Full'],'color':['Blue','Brown']})
        before={r['sku']:copy.deepcopy(r) for r in [root,*children]}
        parent,revised,retired=repair_family(root,children,rules()[root['sku']])
        after=[parent,*revised];changes=[];inverse=[]
        for row in after:
            old=before[row['sku']]
            changes.append({'sku':row['sku'],'executable':False,'fields':{
                k:{'before':old.get(k),'after':row.get(k)} for k in set(old)|set(row) if old.get(k)!=row.get(k)}})
            inverse.append({'sku':row['sku'],'restore':old,'executable':False})
        for item in retired:
            item['before']=before[item['sku']]
            inverse.append({'sku':item['sku'],'restore':item['before'],'executable':False})
        return before,after,changes,inverse,retired

    def test_complete_retirement_and_field_round_trip(self):
        before,*packet=self.packet_records()
        self.assertEqual(verify_operations(*packet),before)

    def test_missing_inverse_rejected_even_if_other_counts_look_reasonable(self):
        _,after,changes,inverse,retired=self.packet_records()
        with self.assertRaisesRegex(ValueError,'Inverse coverage'):
            verify_operations(after,changes,inverse[:-1],retired)

    def test_incomplete_field_diff_rejected(self):
        _,after,changes,inverse,retired=self.packet_records()
        changes[0]['fields'].pop('name')
        with self.assertRaisesRegex(ValueError,'Incomplete forward'):
            verify_operations(after,changes,inverse,retired)

    def test_incorrect_forward_value_rejected(self):
        _,after,changes,inverse,retired=self.packet_records()
        changes[0]['fields']['name']['after']='Not the candidate name'
        with self.assertRaisesRegex(ValueError,'Forward field value'):
            verify_operations(after,changes,inverse,retired)

    def test_different_retirement_snapshot_rejected(self):
        _,after,changes,inverse,retired=self.packet_records()
        retired=copy.deepcopy(retired)
        retired[0]['before']['name']='Different snapshot'
        with self.assertRaisesRegex(ValueError,'Retirement snapshot'):
            verify_operations(after,changes,inverse,retired)

    def test_executable_operation_rejected(self):
        _,after,changes,inverse,retired=self.packet_records()
        changes[0]['executable']=True
        with self.assertRaisesRegex(ValueError,'Executable forward'):
            verify_operations(after,changes,inverse,retired)


if __name__=='__main__': unittest.main()
