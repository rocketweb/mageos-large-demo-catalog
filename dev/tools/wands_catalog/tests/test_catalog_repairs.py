import copy
import itertools
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog_repairs import repair_family, validate_candidate, make_design, sparse_proposals, refine_facts, image_repair_drafts
from repair_designs import rules, expansion_rule
from synthetic_dimensions import LABEL


def family(sku, axes):
    root = {'sku': sku, 'source_product_id': sku[-6:].lstrip('0') or '0', 'name': 'Old name',
            'source_class': 'Nightstands', 'kind': 'configurable', 'variant_options': {},
            'axes': [{'attribute': k, 'label': k, 'values': v} for k, v in axes.items()],
            'axis_codes': sorted(axes), 'specifications': {}, 'withheld': [], 'price': 100,
            'salable': True, 'identity': {'sku': sku, 'product_type': 'configurable', 'url_key': sku},
            'catalog_fields': {'sku': sku, 'name': 'Old name', 'price': '100.00', 'qty': '0',
                               'is_in_stock': '1', 'manage_stock': '1', 'description': '<p>Old</p>'}}
    children = []
    for i, values in enumerate(itertools.product(*axes.values())):
        child = copy.deepcopy(root)
        child.update(sku=sku+'-'+str(i), kind='simple', parent_sku=sku,
                     variant_options=dict(zip(axes, values)), price=100+i)
        child['identity'] = {'sku': child['sku'], 'product_type': 'simple', 'url_key': child['sku']}
        child['catalog_fields'].update(sku=child['sku'], price=str(100+i), qty=str(10+i))
        children.append(child)
    return root, children


class CatalogRepairsTest(unittest.TestCase):
    def test_width_correction_keeps_skus_stock_and_prices(self):
        root, children = family('WANDS-014741', {'wands_length':['30 in','36 in','48 in'], 'wands_finish':['Oak','Walnut']})
        original = copy.deepcopy([root, *children])
        parent, revised, retired = repair_family(root, children, rules()[root['sku']])
        self.assertEqual([root, *children], original)
        self.assertFalse(retired)
        self.assertEqual({c['variant_options']['wands_length'] for c in revised}, {'18 in','22 in','26 in'})
        self.assertEqual(parent['name'], 'Three-Drawer Solid Wood Nightstand')
        for old, new in zip(children, revised):
            self.assertEqual(old['identity'], new['identity'])
            for field in ['price','qty','is_in_stock']:
                self.assertEqual(old['catalog_fields'][field], new['catalog_fields'][field])
            self.assertLess(new['specifications']['lab_spec_width_cm']['value'], 70)
            self.assertIn('Synthetic lab', new['catalog_fields']['description'])
        validate_candidate(original, [parent, *revised], retired)

    def test_crib_size_collapse_preserves_one_child_per_color_and_inverse_identity(self):
        root, children = family('WANDS-011451', {'wands_size':['Toddler','Twin','Full'], 'color':['Blue','Brown']})
        parent, revised, retired = repair_family(root, children, rules()[root['sku']])
        self.assertEqual(parent['axis_codes'], ['color'])
        self.assertEqual(len(revised), 2)
        self.assertEqual(len(retired), 4)
        self.assertTrue(all('wands_size' not in c['variant_options'] for c in revised))
        self.assertTrue(all(c['dimension_design']['total_component_quantity']==4 for c in revised))
        self.assertTrue(all(r['executable'] is False for r in retired))
        validate_candidate([root, *children], [parent, *revised], retired)

    def test_single_remaining_variant_becomes_root_simple_in_candidate_only(self):
        root, children = family('WANDS-017166', {'wands_size':['Toddler','Twin','Full','Queen']})
        parent, revised, retired = repair_family(root, children, rules()[root['sku']])
        self.assertEqual(parent['kind'], 'simple')
        self.assertFalse(revised)
        self.assertEqual(len(retired), 4)
        self.assertEqual(parent['catalog_fields']['qty'], children[0]['catalog_fields']['qty'])
        self.assertTrue(all(r['replacement_sku']==root['sku'] for r in retired))
        self.assertEqual(root['kind'], 'configurable')
        validate_candidate([root, *children], [parent], retired)

    def test_duplicate_map_is_rejected_instead_of_silently_losing_variants(self):
        root, children = family('WANDS-014741', {'wands_length':['30 in','36 in','48 in'], 'wands_finish':['Oak','Walnut']})
        rule = copy.deepcopy(rules()[root['sku']])
        rule['axis']['map']['48 in'] = '22 in'
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            repair_family(root, children, rule)

    def test_unknown_option_fails_closed(self):
        root, children = family('WANDS-014741', {'wands_length':['60 in']})
        with self.assertRaisesRegex(ValueError, 'option'):
            repair_family(root, children, rules()[root['sku']])

    def test_bistro_variants_have_exact_piece_counts_and_table(self):
        root, children = family('WANDS-002448', {'wands_piece_count':['2 Pieces','3 Pieces','4 Pieces','5 Pieces']})
        parent, revised, retired = repair_family(root, children, rules()[root['sku']])
        for child in revised:
            design = child['dimension_design']
            self.assertEqual(design['total_component_quantity'], int(child['variant_options']['wands_piece_count'].split()[0]))
            self.assertEqual(sum(c['quantity'] for c in design['components'] if c['component_id']=='table'), 1)
            self.assertTrue(all(c['composition_synthetic'] for c in design['components']))
        self.assertNotIn('lab_spec_width_cm', parent['specifications'])

    def test_curtain_set_scope_and_geometry_are_not_whole_window_measurements(self):
        root, children = family('WANDS-000933', {'wands_length':['63 in','84 in','95 in'], 'color':['Black','Natural']})
        _, revised, _ = repair_family(root, children, rules()[root['sku']])
        part = revised[0]['dimension_design']['components']
        self.assertEqual(sum(c['quantity'] for c in part), 3)
        self.assertEqual(next(c for c in part if c['component_id']=='tiers')['quantity'], 2)
        self.assertNotIn('lab_spec_width_cm', revised[0]['specifications'])

    def test_toddler_keeps_toddler_geometry_after_removing_size_axis(self):
        root, children = family('WANDS-009621', {'wands_size':['Toddler','Twin','Full'], 'color':['Blue','Natural']})
        _, revised, retired = repair_family(root, children, rules()[root['sku']])
        self.assertEqual(len(retired), 4)
        self.assertLess(revised[0]['specifications']['lab_spec_length_cm']['value'], 150)

    def test_color_never_changes_component_geometry(self):
        root, children = family('WANDS-020492', {'wands_piece_count':['2 Pieces','3 Pieces','4 Pieces'], 'color':['White','Beige']})
        _, revised, _ = repair_family(root, children, rules()[root['sku']])
        a, b = revised[:2]
        self.assertEqual(a['dimension_design']['components'], b['dimension_design']['components'])

    def test_family_component_ranges_include_roles_absent_from_smallest_variant(self):
        root, children = family('WANDS-020492', {'wands_piece_count':['2 Pieces','3 Pieces','4 Pieces']})
        parent, _, _ = repair_family(root, children, rules()[root['sku']])
        armless = next(c for c in parent['dimension_design']['component_ranges'] if c['component_id']=='armless')
        self.assertEqual(armless['quantity_per_design'], [0,1,2])
        self.assertEqual(armless['present_children'], 2)

    def test_merlyn_accessories_are_included_but_not_counted_as_furniture(self):
        root, children = family('WANDS-030335', {'wands_piece_count':['2 Pieces','3 Pieces','4 Pieces','5 Pieces']})
        _, revised, _ = repair_family(root, children, rules()[root['sku']])
        for child in revised:
            design = child['dimension_design']
            count = int(child['variant_options']['wands_piece_count'].split()[0])
            self.assertEqual(design['furniture_piece_count'], count)
            self.assertEqual(design['total_component_quantity'], count+2)
            pillows = next(c for c in design['components'] if c['component_id']=='pillows')
            self.assertFalse(pillows['counts_as_furniture'])

    def test_parent_assortments_list_only_values_actually_available(self):
        root, children = family('WANDS-033594', {'wands_piece_count':['2 Pieces','3 Pieces','4 Pieces'], 'color':['White','Terracotta']})
        parent, _, _ = repair_family(root, children, rules()[root['sku']])
        self.assertNotIn('5 Pieces', parent['catalog_fields']['description'])

    def test_source_facts_never_overwritten_to_fit_repair(self):
        r = family('WANDS-014741', {'wands_length':['30 in']})[1][0]
        r['specifications']['lab_spec_width_cm'] = {'value': 999, 'synthetic': False, 'evidence':[{'raw':'999 cm'}]}
        with self.assertRaisesRegex(ValueError, 'source dimension'):
            make_design(r, {'profile':'nightstand', 'bindings': {'wands_length':'width'}})

    def test_sparse_proposals_always_pair_measurements_with_disclosure(self):
        root, children = family('WANDS-014741', {'wands_length':['30 in','36 in','48 in'], 'wands_finish':['Oak','Walnut']})
        parent, revised, _ = repair_family(root, children, rules()[root['sku']])
        proposals = sparse_proposals([parent, *revised])
        for proposal in proposals:
            if any(k.endswith('_cm') for k in proposal['set']):
                self.assertEqual(proposal['set']['lab_spec_dimension_disclosure'], LABEL)
            self.assertEqual(proposal['clear'], [])
            self.assertFalse(proposal['executable'])

    def test_ambiguous_source_definitions_are_not_fabricated(self):
        for sku in ['WANDS-017842','WANDS-022642','WANDS-034345','WANDS-042749']:
            self.assertIn('hold_reason', rules()[sku])

    def test_facet_aliases_recover_only_unambiguous_supported_values(self):
        r=family('WANDS-014741', {'color':['Blue']})[0]
        r['withheld']=[{'attribute':'lab_spec_style','reason':'outside controlled vocabulary',
                        'evidence':[{'key':'dsprimaryproductstyle','raw':'country / farmhouse'},{'key':'style','raw':'Farmhouse'}]}]
        after=refine_facts(r)
        self.assertEqual(after['specifications']['lab_spec_style']['value'], 'Farmhouse')
        self.assertFalse(after['specifications']['lab_spec_style']['synthetic'])
        self.assertEqual(after['specifications']['lab_spec_style']['evidence'],r['withheld'][0]['evidence'])
        self.assertEqual(len(r['withheld']),1)

    def test_facet_aliases_never_erase_conflicting_or_variable_source_values(self):
        r=family('WANDS-014741', {'color':['Blue']})[0]
        r['withheld']=[{'attribute':'lab_spec_style','reason':'outside controlled vocabulary',
                        'evidence':[{'key':'dsprimaryproductstyle','raw':'boho'},{'key':'style','raw':'Traditional'}]},
                      {'attribute':'lab_spec_color','reason':'varies_by_family_axis','evidence':[{'key':'color','raw':'White'}]}]
        after=refine_facts(r)
        self.assertEqual(after['withheld'],r['withheld'])
        self.assertFalse(after['specifications'])

    def test_bulb_base_formatting_does_not_change_electrical_value(self):
        r=family('WANDS-014741', {'color':['Blue']})[0]
        r['withheld']=[{'attribute':'lab_spec_bulb_base','reason':'outside controlled vocabulary',
                        'evidence':[{'key':'bulbbase','raw':'e26/medium ( standard )'}]}]
        self.assertEqual(refine_facts(r)['specifications']['lab_spec_bulb_base']['value'],'E26')

    def test_cylindrical_nightstand_expansion_preserves_circular_footprint(self):
        root, children = family('WANDS-004880', {'wands_length':['30 in','36 in','48 in'], 'wands_finish':['Walnut','Oak']})
        row = {'product_id':'4880','product_name':'mirefield cylindrical wooden 2 drawer nightstand',
               'product_class':'Nightstands','product_features':''}
        rule = expansion_rule(row, {'parent':root,'axes':root['axes']})
        _, revised, _ = repair_family(root,children,rule)
        for child in revised:
            self.assertEqual(child['specifications']['lab_spec_width_cm']['value'],child['specifications']['lab_spec_depth_cm']['value'])

    def test_four_width_expansion_is_narrow_monotonic_and_not_three_choice_copy(self):
        root, children = family('WANDS-004322', {'wands_length':['30 in','36 in','48 in','60 in']})
        row = {'product_id':'4322','product_name':'1 - drawer solid wood nightstand in walnut',
               'product_class':'Nightstands','product_features':''}
        rule = expansion_rule(row, {'parent':root,'axes':root['axes']})
        parent, revised, _ = repair_family(root,children,rule)
        widths = [c['specifications']['lab_spec_width_cm']['value'] for c in revised]
        self.assertEqual(widths,sorted(set(widths)))
        self.assertLessEqual(max(widths),66.04)
        self.assertNotIn('three',parent['catalog_fields']['description'])

    def test_expansion_does_not_use_class_only_or_plastic_wood_finish_match(self):
        for pid,name in [('1731','hugh end table with storage'),('22607','small ghost buster nightstand')]:
            root,_ = family('WANDS-'+pid.zfill(6), {'wands_length':['30 in','36 in','48 in']})
            rule = expansion_rule({'product_id':pid,'product_name':name,'product_class':'Nightstands',
                'product_features':'Frame Material: Plastic'}, {'parent':root,'axes':root['axes']})
            self.assertTrue(rule is None or 'hold_reason' in rule)

    def test_pillowcase_pack_count_conflict_is_a_hold(self):
        root,_ = family('WANDS-002739', {'wands_size':['Twin','Full','King']})
        rule = expansion_rule({'product_id':'2739','product_name':'pillowcase','product_class':'Sheets And Sheet Sets',
            'product_features':'Product Type: Pillowcase | Number of Pieces Included: 1 | Number of Pillowcases Included: 2'},
            {'parent':root,'axes':root['axes']})
        self.assertIn('hold_reason',rule)

    def test_pillowcase_pair_keeps_two_separately_dimensioned_cases(self):
        root,children = family('WANDS-037955', {'wands_size':['Twin','Full','King'],'color':['Gray','Green']})
        row = {'product_id':'37955','product_name':'oberlin ticking striped 100 % cotton pillowcase',
            'product_class':'Sheets And Sheet Sets',
            'product_features':'Product Type: Pillowcase | Number of Pieces Included: 2 | Number of Pillowcases Included: 2 | Fitted Sheet Included: No | Flat Sheet Included: No | Pillowcase Included: Yes | Pillowcase Type: King | Pillowcase Type: Standard'}
        rule = expansion_rule(row,{'parent':root,'axes':root['axes']})
        _,revised,_ = repair_family(root,children,rule)
        for child in revised:
            self.assertEqual(child['dimension_design']['total_component_quantity'],2)
            self.assertNotIn('lab_spec_width_cm',child['specifications'])
            self.assertIn('2 pillowcases',child['catalog_fields']['description'])

    def test_expansion_source_identity_or_option_drift_fails_closed(self):
        root,_ = family('WANDS-004880', {'wands_length':['30 in','36 in','72 in']})
        row = {'product_id':'4880','product_name':'mirefield cylindrical wooden 2 drawer nightstand','product_class':'Nightstands','product_features':''}
        self.assertIn('hold_reason',expansion_rule(row,{'parent':root,'axes':root['axes']}))
        row['product_name'] = 'mirefield dining table'
        self.assertIn('hold_reason',expansion_rule(row,{'parent':root,'axes':root['axes']}))

    def test_image_observation_cannot_be_reused_on_changed_reference(self):
        with self.assertRaisesRegex(ValueError,'reference changed'):
            image_repair_drafts([{'root_sku':'WANDS-012133','reference':{'sha256':'changed'}}])

    def test_parent_description_lists_static_assortment_not_just_total(self):
        root,children=family('WANDS-038422',{'wands_size':['Toddler','Twin','Full'],'color':['Red','Beige']})
        parent,_,_=repair_family(root,children,rules()[root['sku']])
        description=parent['catalog_fields']['description']
        self.assertIn('2 x Valance',description)
        self.assertIn('3 x Wall hanging',description)
        self.assertNotIn('booties',description)


if __name__ == '__main__':
    unittest.main()
