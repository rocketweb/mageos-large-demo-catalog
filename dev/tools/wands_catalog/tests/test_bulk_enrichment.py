import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bulk_enrichment import enrich_specs, build_links, medium_selection, commerce_scenarios, search_cases


def row(sku='WANDS-000001', kind='simple', **values):
    return {'sku':sku, 'product_type':kind, 'product_online':'1', 'visibility':'Catalog, Search',
            'name':'Example lamp', 'description':'Original description', 'price':'100.00',
            'qty':'10', 'is_in_stock':'1', 'url_key':sku.lower(), 'wands_product_class':'Table Lamps', **values}


class BulkEnrichmentTest(unittest.TestCase):
    def test_specs_are_sparse_and_inputs_untouched(self):
        rows = {'WANDS-000001':row()}
        source = {'1':{'product_id':'1','product_name':'Example lamp','product_class':'Table Lamps',
                        'product_features':'Style: Modern|Width: unknown','category hierarchy':'Lighting / Lamps'}}
        before = copy.deepcopy(rows)
        records = enrich_specs(rows, source, {}, synthetic=False)
        self.assertEqual(rows, before)
        self.assertEqual(records[0]['specifications']['lab_spec_style']['value'], 'Modern')
        self.assertNotIn('lab_spec_width_cm', records[0]['specifications'])

    def test_disabled_rows_never_receive_enrichment(self):
        self.assertEqual(enrich_specs({'WANDS-000001':row(product_online='2')}, {}, {}), [])

    def test_current_axes_override_historical_sku_tokens(self):
        parent = row(kind='configurable', configurable_variations='sku=WANDS-000001-BROWN,color=White')
        child = row('WANDS-000001-BROWN', visibility='Not Visible Individually', color='White')
        source = {'1':{'product_id':'1','product_name':'Lamp','product_class':'Table Lamps',
                        'product_features':'Color: Brown','category hierarchy':'Lighting'}}
        records = enrich_specs({parent['sku']:parent,child['sku']:child},source,{},synthetic=False)
        record = next(r for r in records if r['sku']==child['sku'])
        self.assertEqual(record['specifications']['lab_spec_color']['value'],'White')
        self.assertTrue(record['specifications']['lab_spec_color']['synthetic'])

    def test_medium_profile_includes_family_and_bundle_closure(self):
        rows = {r['sku']:r for r in [row('A','configurable',configurable_variations='sku=B,color=White'),
            row('B',visibility='Not Visible Individually'),row('C','bundle',bundle_values='name=Light,sku=B')]}
        self.assertEqual(set(medium_selection(rows, 1)), {'A','B','C'})

    def test_merchandising_excludes_hidden_disabled_and_self(self):
        def record(sku, price=100):
            return {'sku':sku,'source_product_id':sku,'source_class':'Table Lamps','department':'Lighting',
                    'price':price,'salable':True,'specifications':{'lab_spec_style':{'value':'Modern','synthetic':False}}}
        rows = {k:row(k) for k in ['A','B','C']}; rows['C']['visibility']='Not Visible Individually'
        links = build_links(rows, [record('A'),record('B'),record('C')])
        self.assertEqual(links['A']['related_skus'], ['B'])
        self.assertNotIn('C',links)

    def test_scenarios_are_independent_and_do_not_change_catalog(self):
        rows = {'A':row('A')}; before=copy.deepcopy(rows)
        scenarios=commerce_scenarios(rows)
        self.assertEqual(rows,before)
        self.assertTrue(scenarios)
        self.assertTrue(all(s['apply_to']=='isolated disposable fixture only' for s in scenarios))
        tier=next(s for s in scenarios if s['kind']=='tier-price')
        self.assertEqual(tier['expected']['line_total_ex_tax'],'425.00')

    def test_search_seeds_are_not_fabricated_relevance_judgments(self):
        rows={'A':row('A')}
        records=[{'sku':'A','source_product_id':'1','source_class':'Table Lamps','department':'Lighting',
                  'specifications':{'lab_spec_color':{'value':'White'}}}]
        cases=search_cases(rows,records,20)
        self.assertTrue(cases)
        self.assertTrue(all(c['judgment'] is None and not c['ranking_ground_truth'] for c in cases))


if __name__ == '__main__':
    unittest.main()
