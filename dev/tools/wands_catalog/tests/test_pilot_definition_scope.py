import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scope_pilot_definition_update import COPY_FIELDS, compare, resolve_option


class DefinitionScopeTest(unittest.TestCase):
    def tables(self):
        attrs=[{'attribute_code':c,'attribute_id':str(i),'backend_type':'varchar'} for i,c in enumerate(COPY_FIELDS,1)]
        attrs += [{'attribute_code':'wands_piece_count','attribute_id':'7','backend_type':'int'},
                  {'attribute_code':'status','attribute_id':'8','backend_type':'int'}]
        return {'catalog_product_entity':[{'sku':'WANDS-A','entity_id':'1','type_id':'simple'},
                                           {'sku':'WANDS-B','entity_id':'2','type_id':'simple'}],
                'eav_attribute':attrs,'catalog_product_entity_varchar':[], 'catalog_product_entity_text':[],
                'catalog_product_entity_decimal':[], 'catalog_product_entity_datetime':[],
                'catalog_product_entity_int':[{'value_id':'1','entity_id':'2','attribute_id':'8','store_id':'0','value':'1'}],
                'eav_attribute_option':[{'attribute_id':'7','option_id':'42'},{'attribute_id':'999','option_id':'43'}],
                'eav_attribute_option_value':[{'option_id':'42','value':'5 Pieces','store_id':'0'},
                                              {'option_id':'43','value':'5 Pieces','store_id':'0'}]}

    def test_resolve_reuses_only_correct_existing_option(self):
        tables=self.tables();before=copy.deepcopy(tables)
        self.assertEqual(resolve_option('wands_piece_count','5 Pieces',tables),'42')
        self.assertEqual(tables,before)
        with self.assertRaises(ValueError):resolve_option('wands_piece_count','6 Pieces',tables)
        tables['eav_attribute_option'].append({'attribute_id':'7','option_id':'44'})
        tables['eav_attribute_option_value'].append({'option_id':'44','value':'5 Pieces','store_id':'0'})
        with self.assertRaises(ValueError):resolve_option('wands_piece_count','5 Pieces',tables)

    def test_copy_allowlist_and_retirement_keep_stock_price_and_products(self):
        fields={c:'new '+c for c in COPY_FIELDS};fields.update({'price':'999','qty':'99'})
        rows=[{'sku':'WANDS-A','kind':'simple','catalog_fields':fields,'variant_options':{'wands_piece_count':'5 Pieces'}}]
        changes,gates=compare(rows,[{'sku':'WANDS-B'}],self.tables())
        self.assertEqual(len(changes),8)
        self.assertFalse(gates)
        self.assertEqual({r['attribute'] for r in changes},set(COPY_FIELDS)|{'wands_piece_count','status'})
        self.assertEqual([r['after'] for r in changes if r['sku']=='WANDS-B'],['2'])
        self.assertFalse(any(r['operation']=='delete' for r in changes))

    def test_store_override_does_not_silently_pass(self):
        tables=self.tables();tables['catalog_product_entity_varchar']=[{'entity_id':'1','attribute_id':'1','store_id':'2','value':'localized'}]
        rows=[{'sku':'WANDS-A','kind':'simple','catalog_fields':{c:'new '+c for c in COPY_FIELDS},'variant_options':{}}]
        _,gates=compare(rows,[],tables)
        self.assertEqual(gates,[{'sku':'WANDS-A','attribute':'name','reason':'store_override_requires_review'}])

    def test_missing_option_is_an_explicit_creation_proposal_not_a_rename(self):
        rows=[{'sku':'WANDS-A','kind':'simple','catalog_fields':{c:'new '+c for c in COPY_FIELDS},'variant_options':{'wands_piece_count':'6 Pieces'}}]
        changes,gates=compare(rows,[],self.tables())
        option=next(r for r in changes if r['attribute']=='wands_piece_count')
        self.assertEqual(option['after'],{'new_option_attribute':'wands_piece_count','label':'6 Pieces'})
        self.assertTrue(any(g['reason']=='new_option_requires_creation' for g in gates))


if __name__=='__main__':unittest.main()
