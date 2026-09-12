import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synthetic_dimensions import add_dimensions, summarize_family, validate_dimensions, PROFILES


def record(cls='Accent Chairs', name='Example armchair', options=None, pid='12'):
    options = options or {}
    return {'sku': 'WANDS-' + pid, 'source_product_id': pid, 'source_class': cls,
            'name': name, 'kind': 'simple', 'variant_options': options,
            'axis_codes': list(options), 'specifications': {}}


class SyntheticDimensionsTest(unittest.TestCase):
    def test_deterministic_and_color_invariant_with_explicit_provenance(self):
        a = record(options={'color': 'Blue'})
        b = record(options={'color': 'Red'}); b['sku'] += '-RED'
        before = copy.deepcopy(a)
        first = add_dimensions(a)
        self.assertEqual(a, before)
        self.assertEqual(first['specifications'], add_dimensions(b)['specifications'])
        self.assertEqual(first, add_dimensions(a))
        for fact in first['specifications'].values():
            self.assertTrue(fact['synthetic'])
            self.assertEqual(fact['origin'], 'approved synthetic lab dimension')
            self.assertTrue(fact['rule_version'])
            self.assertTrue(fact['evidence'])
        validate_dimensions(first)

    def test_preserves_original_measurements_and_evidence(self):
        a = record()
        fact = {'value': 80, 'synthetic': False, 'origin': 'WANDS', 'evidence': [{'raw': '80 cm'}]}
        a['specifications']['lab_spec_width_cm'] = fact
        enriched = add_dimensions(a)
        self.assertEqual(enriched['specifications']['lab_spec_width_cm'], fact)
        self.assertGreater(len(enriched['specifications']), 1)

    def test_rectangular_size_is_option_derived_not_source_measurement(self):
        r = add_dimensions(record('Area Rugs', 'Area rug', {'wands_size': '5 ft x 7 ft'}))
        self.assertEqual(r['specifications']['lab_spec_width_cm']['value'], 152.4)
        self.assertEqual(r['specifications']['lab_spec_length_cm']['value'], 213.36)
        self.assertTrue(r['specifications']['lab_spec_width_cm']['synthetic'])
        self.assertIn('wands_size', str(r['specifications']['lab_spec_width_cm']['evidence']))

    def test_pack_count_does_not_multiply_tile_measurements(self):
        a = record('Floor & Wall Tile', 'Tile', {'wands_size': '12 in x 12 in', 'wands_pack_size': 'Pack of 4'})
        b = copy.deepcopy(a); b['variant_options']['wands_pack_size'] = 'Pack of 6'
        self.assertEqual(add_dimensions(a)['specifications'], add_dimensions(b)['specifications'])
        self.assertEqual(add_dimensions(a)['dimension_design']['scope'], 'one tile, not the pack')

    def test_small_medium_large_are_monotonic(self):
        rows = [add_dimensions(record('Kids Desks', 'Desk', {'wands_size': size})) for size in ['Small', 'Medium', 'Large', 'Extra Large']]
        for code in ['lab_spec_width_cm', 'lab_spec_depth_cm', 'lab_spec_height_cm']:
            values = [r['specifications'][code]['value'] for r in rows]
            self.assertEqual(values, sorted(set(values)))

    def test_seat_dimensions_are_inside_overall_envelope(self):
        for size in ['18 in', '24 in', '26 in', '30 in']:
            r = add_dimensions(record('Bar Stools', 'Stool with back', {'wands_seat_height': size}))
            validate_dimensions(r)
            self.assertLess(r['specifications']['lab_spec_seat_height_cm']['value'], r['specifications']['lab_spec_height_cm']['value'])

    def test_round_shape_not_forced_into_rectangular_option(self):
        r = record('Area Rugs', 'Round rug', {'wands_size': '5 ft x 7 ft'})
        r['specifications']['lab_spec_shape'] = {'value': 'Round', 'synthetic': False}
        result = add_dimensions(r)
        self.assertEqual(result['specifications'], r['specifications'])
        self.assertIn('shape_option_conflict', result['dimension_design']['issues'])

    def test_incompatible_options_and_mixed_assortments_remain_flagged(self):
        for cls, name, options in [
            ('Crib Bedding Sets', 'Crib bedding', {'wands_size': 'Queen'}),
            ('Valances & Kitchen Curtains', 'Valance', {'wands_length': '95 in'}),
            ('Sheets And Sheet Sets', 'Body Pillowcase', {'wands_size': 'Queen'}),
            ('Outdoor Conversation Sets', 'Seating group', {'wands_piece_count': '4 Pieces'}),
            ('Kids Beds', 'Triple Bunk bed', {'wands_size': 'Twin'}),
        ]:
            with self.subTest(cls=cls):
                r = add_dimensions(record(cls, name, options))
                self.assertFalse(r['specifications'])
                self.assertEqual(r['dimension_design']['status'], 'needs_identity_or_component_review')
                self.assertTrue(r['dimension_design']['issues'])

    def test_unknown_class_is_not_assigned_department_default(self):
        r = add_dimensions(record('Mystery Accessories', 'Unknown'))
        self.assertFalse(r['specifications'])
        self.assertIn('no_class_profile', r['dimension_design']['issues'])

    def test_small_kitchen_products_have_item_not_room_scale_dimensions(self):
        mug = add_dimensions(record('Mugs & Teacups|Licensed Products', 'Coffee mug'))
        self.assertEqual(mug['dimension_design']['status'], 'synthetic_design_complete')
        self.assertLess(mug['specifications']['lab_spec_height_cm']['value'], 15)
        self.assertIn('capacity unspecified', mug['dimension_design']['scope'])

    def test_source_dimension_outside_profile_envelope_is_not_overwritten_or_completed(self):
        r = record()
        r['specifications']['lab_spec_width_cm'] = {'value': 2000, 'synthetic': False, 'evidence': [{'raw': '20 m'}]}
        result = add_dimensions(r)
        self.assertEqual(result['specifications'], r['specifications'])
        self.assertIn('dimension_outside_design_bounds: width', result['dimension_design']['issues'])

    def test_all_supported_light_counts_fit_the_authored_design_bounds(self):
        for count in [1,3,4,6,8]:
            r=add_dimensions(record('Wall Sconces','Wall fixture',{'wands_light_count':str(count)+' Lights'}))
            self.assertEqual(r['dimension_design']['status'],'synthetic_design_complete',r['dimension_design'])

    def test_round_mug_body_does_not_make_handle_inclusive_footprint_square(self):
        r=record('Mugs & Teacups','Round mug')
        r['specifications']['lab_spec_shape']={'value':'Round','synthetic':False}
        r=add_dimensions(r)
        self.assertGreater(r['specifications']['lab_spec_width_cm']['value'],r['specifications']['lab_spec_depth_cm']['value'])

    def test_mixed_chair_class_uses_named_parsons_subtype(self):
        r=add_dimensions(record('Accent Chairs|Dining Chairs|Office Chairs','Upholstered Parsons Chair'))
        self.assertEqual(r['dimension_design']['profile'],'dining_chair')

    def test_family_reports_ranges_not_one_false_parent_size(self):
        parent = record('Area Rugs', 'Rug'); parent['kind'] = 'configurable'
        children = [add_dimensions(record('Area Rugs', 'Rug', {'wands_size': size})) for size in ['2 ft x 3 ft', '5 ft x 7 ft']]
        result = summarize_family(parent, children)
        self.assertNotIn('lab_spec_width_cm', result['specifications'])
        self.assertEqual(result['dimension_design']['ranges_cm']['lab_spec_width_cm']['min'], 60.96)
        self.assertEqual(result['dimension_design']['ranges_cm']['lab_spec_width_cm']['max'], 152.4)
        self.assertEqual(result['dimension_design']['status'], 'synthetic_family_complete')

    def test_partial_family_does_not_promote_common_child_dimensions(self):
        parent = record('Area Rugs', 'Rug'); parent['kind'] = 'configurable'
        children = [add_dimensions(record('Area Rugs', 'Rug', {'wands_size': size})) for size in ['2 ft x 3 ft', 'mystery']]
        result = summarize_family(parent, children)
        self.assertFalse(result['specifications'])
        self.assertEqual(result['dimension_design']['status'], 'synthetic_family_partial')

    def test_corrupt_or_unlabelled_synthetic_dimensions_fail_validation(self):
        r = add_dimensions(record())
        r['specifications']['lab_spec_seat_width_cm']['value'] = 900
        with self.assertRaises(ValueError): validate_dimensions(r)
        r = add_dimensions(record())
        r['specifications']['lab_spec_width_cm'].pop('rule_version')
        with self.assertRaises(ValueError): validate_dimensions(r)

    def test_new_exterior_profiles_do_not_claim_installation_fit(self):
        cases=[('Beverage Refrigerators & Coolers|Wine Refrigerators','Beverage refrigerator'),
               ('Vanities','Single bathroom vanity'),('Shower and Bathtub Enclosures','Shower enclosure'),
               ('Sheds','Metal storage shed'),('Tubs And Whirlpools','Bathtub')]
        for cls,name in cases:
            with self.subTest(cls=cls):
                r=add_dimensions(record(cls,name))
                self.assertEqual(r['dimension_design']['status'],'synthetic_design_complete')
                self.assertIn('installation',r['dimension_design']['scope'])
                self.assertTrue(all(f['synthetic'] for f in r['specifications'].values()))

    def test_named_title_dimensions_constrain_only_the_synthetic_design(self):
        r=add_dimensions(record('Shower and Bathtub Enclosures','46 In . W X 34 3/8 In . D X 72 In . H Shower Enclosure'))
        for axis,value in [('width',116.84),('depth',87.3125),('height',182.88)]:
            fact=r['specifications']['lab_spec_'+axis+'_cm']
            self.assertEqual(fact['value'],value)
            self.assertTrue(fact['synthetic'])
            self.assertIn('title_design_constraint',str(fact['evidence']))

    def test_title_constraint_cannot_replace_source_or_selected_size(self):
        r=record('Vanities','30 in W Vanity',{'wands_length':'48 in'})
        enriched=add_dimensions(r)
        self.assertEqual(enriched['specifications']['lab_spec_width_cm']['value'],121.92)
        r=record('Vanities','30 in W Vanity')
        r['specifications']['lab_spec_width_cm']={'value':85,'synthetic':False,'evidence':[{'raw':'85 cm'}]}
        self.assertEqual(add_dimensions(r)['specifications']['lab_spec_width_cm'],r['specifications']['lab_spec_width_cm'])

    def test_fitted_sheet_source_context_resolves_class_without_relabeling_options(self):
        r=record('Sheets And Sheet Sets','Ethnic Sheet Set',{'wands_size':'Queen'})
        r['design_context']={'features':{'fittedsheetincluded':['yes'],'flatsheetincluded':['no'],'pillowcaseincluded':['no']}}
        enriched=add_dimensions(r)
        self.assertEqual(enriched['dimension_design']['profile'],'fitted_sheet')
        self.assertEqual(enriched['variant_options'],r['variant_options'])
        self.assertEqual(enriched['specifications']['lab_spec_width_cm']['value'],152.4)
        self.assertIn('not a mattress-fit guarantee',enriched['dimension_design']['scope'])

    def test_unknown_fabric_sale_unit_is_not_invented(self):
        r=add_dimensions(record('Fabric','Pineapple Fabric'))
        self.assertFalse(r['specifications'])
        self.assertIn('sale_unit_requires_definition',r['dimension_design']['issues'])

    def test_accessory_profiles_require_a_known_subtype(self):
        known=add_dimensions(record('Laundry Accessories','Tower Expandable Platform Riser'))
        unknown=add_dimensions(record('Laundry Accessories','Laundry Accessory'))
        self.assertEqual(known['dimension_design']['profile'],'platform_riser')
        self.assertFalse(unknown['specifications'])

    def test_bunk_and_stowed_trundle_profiles_do_not_claim_clearances(self):
        for name,size in [('Bunk Bed','Twin over Full'),('Bed With Trundle','Twin'),('Hanging Daybed','Full'),('Adjustable Bed Base And Mattress','Queen')]:
            r=add_dimensions(record('Kids Beds' if 'Bunk' in name or 'Trundle' in name else 'Daybeds & Guest Beds' if 'Daybed' in name else 'Adjustable Beds',name,{'wands_size':size}))
            self.assertEqual(r['dimension_design']['status'],'synthetic_design_complete',r['dimension_design'])
            self.assertIn('excluded',r['dimension_design']['scope'])
        r=add_dimensions(record('Kids Beds','Bed With Trundle',{'wands_size':'Toddler'}))
        self.assertTrue(r['dimension_design']['issues'])

    def test_mortar_and_pestle_have_separate_dimensions_not_one_set_width(self):
        r=add_dimensions(record('Kitchen Gadgets','Marble Mortar And Pestle'))
        self.assertEqual(r['dimension_design']['status'],'synthetic_components_complete')
        self.assertFalse(r['specifications'])
        components=r['dimension_design']['components']
        self.assertEqual([(c['component_id'],c['quantity']) for c in components],[('mortar',1),('pestle',1)])
        self.assertTrue(all(len(c['specifications'])>=2 and c['composition_evidence'] for c in components))
        validate_dimensions(r)

    def test_mixing_bowl_lids_match_bowls_and_piece_counts(self):
        r=record('Mixing Bowls','8 Piece Mixing Bowl Set')
        r['design_context']={'source_name':r['name'],'features':{'numberoflidsincluded':['4']}}
        r=add_dimensions(r)
        components=r['dimension_design']['components']
        self.assertEqual(sum(c['quantity'] for c in components),8)
        pairs={c['component_id']:c for c in components}
        for i in range(1,5):
            self.assertEqual(pairs['bowl-'+str(i)]['specifications']['lab_spec_width_cm']['value'],pairs['lid-'+str(i)]['specifications']['lab_spec_width_cm']['value'])

    def test_conflicting_assortment_count_is_not_filled(self):
        r=record('Wall Mounted Shelves','3 Piece Triangle Shelf Set')
        r['design_context']={'source_name':r['name'],'features':{'totalnumberofpiecesincluded':['1']}}
        r=add_dimensions(r)
        self.assertFalse(r['specifications'])
        self.assertIn('conflicting_component_counts',r['dimension_design']['issues'])

    def test_shelf_set_option_applies_to_largest_shelf_not_installed_span(self):
        r=record('Bathroom Storage|Wall Mounted Shelves','5 Piece Wall Shelf Set',{'wands_length':'36 in'})
        r['design_context']={'source_name':r['name'],'features':{'totalnumberofpiecesincluded':['5'],'numberofshelves':['5'],'piecesincluded':['5 shelves']}}
        r=add_dimensions(r)
        components=r['dimension_design']['components']
        self.assertEqual(len(components),5)
        self.assertEqual(max(c['specifications']['lab_spec_width_cm']['value'] for c in components),91.44)
        self.assertFalse(r['specifications'])
        self.assertIn('not an installed span',r['dimension_design']['scope'])

    def test_component_family_does_not_promote_set_dimensions_to_parent(self):
        parent=record('Kitchen Gadgets','Mortar And Pestle');parent['kind']='configurable'
        a=add_dimensions(record('Kitchen Gadgets','Mortar And Pestle',{'color':'Black'}))
        b=add_dimensions(record('Kitchen Gadgets','Mortar And Pestle',{'color':'White'}))
        result=summarize_family(parent,[a,b])
        self.assertEqual(result['dimension_design']['status'],'synthetic_family_complete')
        self.assertEqual(result['dimension_design']['component_children'],2)
        self.assertFalse(result['specifications'])

    def test_unknown_length_option_on_component_set_is_not_silently_ignored(self):
        r=add_dimensions(record('Kitchen Gadgets','Mortar And Pestle',{'wands_length':'36 in'}))
        self.assertEqual(r['dimension_design']['status'],'needs_identity_or_component_review')

    def test_component_validator_rejects_duplicate_roles_and_bad_quantities(self):
        r=add_dimensions(record('Kitchen Gadgets','Mortar And Pestle'))
        r['dimension_design']['components'].append(copy.deepcopy(r['dimension_design']['components'][0]))
        with self.assertRaises(ValueError):validate_dimensions(r)
        r=add_dimensions(record('Kitchen Gadgets','Mortar And Pestle'))
        r['dimension_design']['components'][0]['quantity']=0
        with self.assertRaises(ValueError):validate_dimensions(r)

    def test_bath_set_preserves_fifteen_pieces_and_sizes_only_the_mat(self):
        r=record('Bath Rugs & Mats|Shower Curtains','15 Piece Bath Set',{'wands_size':'24 in x 36 in'})
        r['design_context']={'source_name':r['name'],'features':{'numberofhooksincluded':['12'],
            'productsincluded':['bath mat/rug','contour mat','shower curtain','hooks'],'piecesincluded':['15']}}
        r=add_dimensions(r)
        parts={c['component_id']:c for c in r['dimension_design']['components']}
        self.assertEqual(sum(c['quantity'] for c in parts.values()),15)
        self.assertEqual(parts['hooks']['quantity'],12)
        self.assertEqual(parts['bath-mat']['specifications']['lab_spec_width_cm']['value'],60.96)
        self.assertGreater(parts['curtain']['specifications']['lab_spec_width_cm']['value'],150)
        self.assertFalse(r['specifications'])

    def test_chair_with_ottoman_requires_inclusion_evidence(self):
        r=record('Massage Chairs|Recliners','Salon Chair With Ottoman')
        self.assertTrue(add_dimensions(r)['dimension_design']['issues'])
        r['design_context']={'features':{'ottomanincluded':['yes']}}
        r=add_dimensions(r)
        self.assertEqual({c['component_id'] for c in r['dimension_design']['components']},{'chair','ottoman'})

    def test_repair_queue_has_exact_affected_skus_without_changing_records(self):
        from synthetic_dimensions import repair_proposals
        p=record('Kids Beds','Toddler Bed');p['kind']='configurable';p['axes']=[{'attribute':'wands_size','values':['Toddler','Full']}]
        child=record('Kids Beds','Toddler Bed',{'wands_size':'Full'});child['sku']='CHILD';child['parent_sku']=p['sku']
        child=add_dimensions(child);parent=summarize_family(p,[child])
        before=copy.deepcopy([parent,child])
        plan=repair_proposals([parent,child])
        self.assertEqual(len(plan),1)
        self.assertEqual(plan[0]['affected_skus'],['CHILD',p['sku']])
        self.assertEqual(plan[0]['affected_record_count'],2)
        self.assertEqual(plan[0]['resolution_scope'],'catalog_option_definition')
        self.assertFalse(plan[0]['executable'])
        self.assertEqual([parent,child],before)

    def test_liner_with_mat_sizes_is_an_option_problem_not_an_unknown_assortment(self):
        r=record('Bath Rugs & Mats|Shower Curtains','Vinyl Shower Curtain Liner',{'wands_size':'18 in x 30 in'})
        r['design_context']={'features':{'productsincluded':['liner']}}
        r=add_dimensions(r)
        self.assertIn('option_class_or_component_mismatch',r['dimension_design']['issues'])
        self.assertFalse(r['specifications'])

    def test_component_validator_rejects_inconsistent_declared_total(self):
        r=add_dimensions(record('Kitchen Gadgets','Mortar And Pestle'))
        r['dimension_design']['total_component_quantity']=3
        with self.assertRaises(ValueError):validate_dimensions(r)


if __name__ == '__main__': unittest.main()
