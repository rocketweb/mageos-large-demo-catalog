import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_mageos_rehearsal import check_nursery, verify_models, FIELDS, ROOTS, VERSIONS


class NurseryRuntimeTest(unittest.TestCase):
    def test_actual_runtime_values_and_both_stock_representations(self):
        d={'products':[{'sku':'WANDS-000056','type':'simple','price':'74.990000','special_price':'63.740000','nursery_final_price':63.74,'weight':'1.750000','children':[]}],
           'nursery_stock':[{'qty':'47.0000','manage_stock':1,'use_config_manage_stock':0,'is_in_stock':1}],
           'nursery_sources':[{'source_code':'default','quantity':'47.0000','status':1}]}
        check_nursery(d)
        for change in ('qty','price','type'):
            broken=copy.deepcopy(d)
            if change=='qty':broken['nursery_sources'][0]['quantity']='51'
            elif change=='price':broken['products'][0]['nursery_final_price']=74.99
            else:broken['products'][0]['type']='configurable'
            with self.assertRaises(ValueError):check_nursery(broken)


class CompleteModelEvidenceTest(unittest.TestCase):
    def fixture(self):
        products=[];active=[]
        for sku in sorted(ROOTS):
            axes=[];children=[]
            if sku in ('WANDS-030335','WANDS-035295'):
                attr='wands_piece_count' if sku=='WANDS-030335' else 'wands_finish'
                key='piece_count' if sku=='WANDS-030335' else 'finish'
                axes=[{'label':'Furniture pieces' if key=='piece_count' else 'Finish'}]
                for i in range(4):
                    child_sku=sku+'-'+str(i);fields={f:child_sku+f for f in FIELDS}
                    children.append({'sku':child_sku,'type':'simple','catalog_fields':fields,'name':fields['name'],'sale_unit':fields['lab_sale_unit'],'status':1,key:str(i)})
                    active.append({'sku':child_sku,'kind':'simple','catalog_fields':fields,'parent_sku':sku,'variant_options':{attr:str(i)}})
            fields={f:sku+f for f in FIELDS};kind='configurable' if axes else 'simple'
            products.append({'sku':sku,'type':kind,'catalog_fields':fields,'name':fields['name'],'sale_unit':fields['lab_sale_unit'],'children':children,'option_labels':[a['label'] for a in axes]})
            active.append({'sku':sku,'kind':kind,'catalog_fields':fields,'axes':axes})
        nursery=next(p for p in products if p['sku']=='WANDS-000056')
        nursery.update(price='74.99',special_price='63.74',nursery_final_price='63.74',weight='1.75')
        retired=[{'sku':'old-'+str(i),'entity_id':str(i+100),'status':2} for i in range(4)]
        after={'products':products,'versions':VERSIONS,'database':'wands_rehearsal_test','probe_sha256':'same',
               'magento_models_loaded':True,'live_writes':False,'storefront_verified':False,'salability_verified':False,
               'retained_children':retired,'nursery_stock':[{'qty':47,'manage_stock':1,'use_config_manage_stock':0,'is_in_stock':1}],
               'nursery_sources':[{'source_code':'default','quantity':47,'status':1}]}
        before=copy.deepcopy(after)
        old_nursery=next(p for p in before['products'] if p['sku']=='WANDS-000056')
        old_nursery.update(type='configurable',children=copy.deepcopy(retired))
        for child in before['retained_children']:child['status']=1
        return before,after,copy.deepcopy(before),copy.deepcopy({'active':active,'retired':retired})

    def test_complete_evidence(self):
        self.assertEqual(verify_models(*self.fixture())['copy_fields_verified'],78)

    def test_copy_corruption_rejected(self):
        values=self.fixture();values[1]['products'][0]['catalog_fields']['description']='wrong'
        with self.assertRaisesRegex(ValueError,'Copy mismatch'):verify_models(*values)

    def test_rollback_drift_rejected(self):
        values=self.fixture();values[2]['nursery_stock'][0]['qty']=48
        with self.assertRaisesRegex(ValueError,'Rollback model mismatch'):verify_models(*values)

    def test_retired_identity_drift_rejected(self):
        values=self.fixture();values[1]['retained_children'][0]['entity_id']='999'
        with self.assertRaisesRegex(ValueError,'identity changed'):verify_models(*values)

    def test_option_drift_rejected(self):
        values=self.fixture()
        next(p for p in values[1]['products'] if p['sku']=='WANDS-030335')['children'][0]['piece_count']='wrong'
        with self.assertRaisesRegex(ValueError,'Option mismatch'):verify_models(*values)
