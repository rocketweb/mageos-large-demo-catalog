import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from catalog_repairs import repair_family, validate_candidate, bundle_reference_impact
from definition_resolutions import remaining_rules, validate_resolved_definition
from repair_designs import expansion_rule, rules
from test_catalog_repairs import family


class DefinitionResolutionsTest(unittest.TestCase):
    def apply(self,pid,axes):
        root,children=family(f'WANDS-{pid:06d}',axes)
        root,children=copy.deepcopy(root),copy.deepcopy(children)
        return repair_family(root,children,remaining_rules()[root['sku']])

    def test_exact_remaining_target_set_has_no_hold_rules(self):
        rules=remaining_rules()
        self.assertEqual(len(rules),44)
        self.assertTrue(all('hold_reason' not in r for r in rules.values()))

    def test_nine_nursery_sets_have_exact_contents_without_adult_size_axes(self):
        for pid,count in [(56,3),(3817,4),(13613,8),(17413,10),(20998,5),(21006,5),(21081,11),(30143,5),(35175,3)]:
            with self.subTest(pid=pid):
                root,children,retired=self.apply(pid,{'wands_size':['Toddler','Twin','Full'],'color':['Blue','Brown']})
                self.assertEqual(root['axis_codes'],['color'])
                self.assertEqual(len(retired),4)
                for child in children:
                    self.assertEqual(child['dimension_design']['total_component_quantity'],count)
                self.assertIn('Included items',root['catalog_fields']['description'])

    def test_nursery_with_no_real_axis_becomes_simple_not_fake_adult_sizes(self):
        root,children,retired=self.apply(56,{'wands_size':['Toddler','Twin','Full','Queen']})
        self.assertEqual(root['kind'],'simple')
        self.assertFalse(children)
        self.assertEqual(len(retired),4)

    def test_six_side_cabinets_have_compact_geometry_and_preserve_shape(self):
        for pid in [1731,20322,20551,22607,27653,42337]:
            axes={'wands_length':['30 in','36 in','48 in']}
            if pid==22607: axes['wands_finish']=['Walnut','Oak']
            _,children,_=self.apply(pid,axes)
            for child in children:
                self.assertLessEqual(child['specifications']['lab_spec_width_cm']['value'],66.04)
                if pid in [1731,20322,20551]:
                    self.assertEqual(child['specifications']['lab_spec_width_cm']['value'],child['specifications']['lab_spec_depth_cm']['value'])

    def test_plastic_finish_changes_do_not_leave_wood_finish_facets(self):
        root,children=family('WANDS-022607',{'wands_length':['30 in','36 in','48 in'],'wands_finish':['Walnut','Oak']})
        for child in children:
            child['specifications']['lab_spec_finish']={'value':child['variant_options']['wands_finish'],'synthetic':True,'origin':'existing generated variant option','evidence':[]}
        parent,revised,retired=repair_family(root,children,remaining_rules()[root['sku']])
        self.assertEqual({c['variant_options']['wands_finish'] for c in revised},{'Clear','Black'})
        self.assertFalse(retired)
        for child in revised:
            self.assertNotIn(child['specifications'].get('lab_spec_finish',{}).get('value'),['Walnut','Oak'])
        validate_candidate([root,*children],[parent,*revised],retired)

    def test_all_outdoor_variants_have_exact_furniture_counts_and_complete_matrices(self):
        rules=remaining_rules()
        for sku,rule in rules.items():
            if rule.get('resolution_kind')!='outdoor_assortment': continue
            root,children=family(sku,{'wands_piece_count':['2 Pieces','3 Pieces','4 Pieces'],'color':['Blue','Brown']})
            parent,revised,retired=repair_family(root,children,rule)
            validate_candidate([root,*children],[parent,*revised],retired)
            for child in revised:
                parts=child['dimension_design']['components']
                count=sum(p['quantity'] for p in parts if p['counts_as_furniture'])
                if 'wands_piece_count' in child['variant_options']:
                    self.assertEqual(count,int(child['variant_options']['wands_piece_count'].split()[0]))
                self.assertTrue(all(p['quantity']>0 for p in parts))

    def test_abe_is_one_table_four_chairs_not_a_silent_five_chair_set(self):
        root,children,retired=self.apply(42749,{'wands_piece_count':['2 Pieces','3 Pieces','4 Pieces'],'color':['Gray','Green']})
        self.assertEqual(root['axis_codes'],['color'])
        for child in children:
            parts={p['component_id']:p['quantity'] for p in child['dimension_design']['components']}
            self.assertEqual(parts,{'table':1,'chairs':4})

    def test_flatware_is_forty_place_setting_items_plus_five_servers(self):
        root,_,_=self.apply(17842,{})
        self.assertEqual(root['dimension_design']['total_component_quantity'],45)
        parts=root['dimension_design']['components']
        self.assertEqual(sorted(p['quantity'] for p in parts),[1]*5+[8]*5)

    def test_bakeware_lid_has_explicit_matched_pan_and_ten_total_parts(self):
        root,_,_=self.apply(3897,{})
        parts={p['component_id']:p for p in root['dimension_design']['components']}
        self.assertEqual(root['dimension_design']['total_component_quantity'],10)
        for code in ['lab_spec_width_cm','lab_spec_depth_cm']:
            self.assertEqual(parts['rectangular-pan']['specifications'][code]['value'],parts['lid']['specifications'][code]['value'])
        self.assertIn('rectangular pan',root['catalog_fields']['description'])

    def test_kitchen_kit_is_two_assembled_tools_not_five_undefined_parts(self):
        root,_,_=self.apply(22642,{})
        self.assertEqual(root['dimension_design']['total_component_quantity'],2)
        self.assertIn('assembled',root['catalog_fields']['description'])

    def test_cobleskill_pair_can_use_specific_pillowcase_count_without_generic_total(self):
        root,_=family('WANDS-033289',{'wands_size':['Twin','Full','Queen'],'color':['Red','Terracotta']})
        row={'product_id':'33289','product_name':'cobleskill luxury ultra soft microfiber pillowcase','product_class':'Sheets And Sheet Sets',
             'product_features':'Product Type: pillowcase | Number of Pillowcases Included: 2 | Flat Sheet Included: no | Fitted Sheet Included: no | Pillowcase Included: yes'}
        rule=expansion_rule(row,{'parent':root,'axes':root['axes']})
        self.assertNotIn('hold_reason',rule)
        self.assertIn('2 pillowcases',rule['sale_unit'])

    def test_semantic_audit_rejects_component_mismatch_even_with_repair_flag(self):
        root,children,_=self.apply(8443,{'wands_piece_count':['2 Pieces','3 Pieces','4 Pieces'],'color':['Blue','Brown']})
        children[0]['dimension_design']['components'][0]['quantity']=9
        with self.assertRaisesRegex(ValueError,'component'):
            validate_resolved_definition(root,children,['piece_count_needs_explicit_component_manifest'])

    def test_misclassified_vada_set_can_resolve_as_one_table_with_length_options(self):
        root,children=family('WANDS-035956',{'wands_piece_count':['2 Pieces','3 Pieces','4 Pieces','5 Pieces']})
        parent,revised,_=repair_family(root,children,rules()[root['sku']])
        result=validate_resolved_definition(parent,revised,['piece_count_needs_explicit_component_manifest'])
        self.assertEqual(result['status'],'resolved_in_local_candidate')

    def test_bundle_impact_tracks_every_option_not_only_default_selection(self):
        bundles=[{'sku':'BUNDLE-1','options':[{'name':'Choose','selections':[{'sku':'KEEP'},{'sku':'RETIRE'},{'sku':'CHANGED'}]}]}]
        result=bundle_reference_impact(bundles,{'CHANGED'},{'RETIRE'})
        self.assertEqual(result['selection_references_checked'],3)
        self.assertEqual(result['retired_selection_references'][0]['selected_sku'],'RETIRE')
        self.assertEqual(result['changed_selection_references'][0]['selected_sku'],'CHANGED')
        self.assertFalse(result['live_verified'])


if __name__=='__main__': unittest.main()
