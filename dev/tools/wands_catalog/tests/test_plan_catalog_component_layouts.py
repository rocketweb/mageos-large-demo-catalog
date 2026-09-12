import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reconcile_catalog_media import digest
from plan_catalog_component_layouts import make_layout, validate_layout, component_briefs, render_svg, render_html, build
from prepare_catalog import sha256


def review(parts):
    contract = {'root_sku': 'WANDS-000001', 'product_name': 'Synthetic set', 'selected_options': {'finish': 'Bronze'},
                'sale_unit': 'Listed components only', 'components': parts,
                'total_component_quantity': sum(p['quantity'] for p in parts),
                'required_disclosure': 'Synthetic lab dimensions, not manufacturer measurements.',
                'constraints': ['No extra products.']}
    return {'root_sku': contract['root_sku'], 'contract': contract, 'definition_sha256': digest(contract),
            'image_sha256': 'a' * 64, 'runtime_prompt_sha256': 'b' * 64, 'verdict': 'fail',
            'finding': 'Missing components.'}


def part(cid, qty=1, width=30, length=40, height=52):
    return {'component_id': cid, 'label': cid, 'quantity': qty, 'counts_as_furniture': True,
            'dimensions_cm': {'lab_spec_width_cm': width, 'lab_spec_length_cm': length, 'lab_spec_height_cm': height}}


def selection(row, profile='flat_lay'):
    return {'root_sku': row['root_sku'], 'definition_sha256': row['definition_sha256'], 'profile': profile,
            'layout_note': 'Abstract component envelopes, not product geometry.',
            'component_checks': {p['component_id']: ['One complete ' + p['label'] + '.'] for p in row['contract']['components']}}


class ComponentLayoutTest(unittest.TestCase):
    def test_quantities_become_exact_individual_instances(self):
        row = review([part('pan', 2), part('lid')])
        layout = make_layout(row, selection(row))
        self.assertEqual(len(layout['instances']), 3)
        self.assertEqual(len(component_briefs(row, selection(row), layout)), 2)
        self.assertEqual({s['instance_id'] for s in layout['instances']}, {'pan-01', 'pan-02', 'lid-01'})
        validate_layout(layout, row['contract'])
        self.assertFalse(layout['executable'])
        self.assertFalse(layout['reference_use_approved'])

    def test_place_settings_preserve_eight_complete_groups_and_servers(self):
        row = review([part('type-' + str(i), 8, width=3, length=14+i) for i in range(5)] +
                     [part('server-' + str(i), width=5, length=25) for i in range(5)])
        layout = make_layout(row, selection(row, 'place_settings'))
        self.assertEqual(len(layout['instances']), 45)
        self.assertEqual(len(layout['groups']), 9)
        self.assertEqual([g['label'] for g in layout['groups'][:8]], ['Place setting ' + str(i) for i in range(1,9)])
        for group in layout['groups'][:8]:
            self.assertEqual(len(group['instance_ids']), 5)
        self.assertEqual(layout['groups'][-1]['label'], 'Five serving utensils')
        validate_layout(layout, row['contract'])

    def test_place_setting_profile_rejects_different_assortment(self):
        row = review([part('fork', 8), part('spoon', 8)])
        with self.assertRaisesRegex(ValueError, 'eight five-piece'):
            make_layout(row, selection(row, 'place_settings'))

    def test_lamps_share_floor_and_preserve_synthetic_height_ratio(self):
        row = review([part('floor', height=165), part('table', 2, height=52)])
        layout = make_layout(row, selection(row, 'shared_floor'))
        boxes = [r['box'] for r in layout['instances']]
        self.assertAlmostEqual(boxes[0]['height'] / boxes[1]['height'], 165/52, places=4)
        self.assertAlmostEqual(boxes[0]['y'] + boxes[0]['height'], boxes[2]['y'] + boxes[2]['height'], places=4)

    def test_pillows_are_instances_without_inflating_furniture_count(self):
        pillow = part('pillow', 2); pillow['counts_as_furniture'] = False
        row = review([part('sofa'), part('chair', 2), part('table'), part('ottoman'), pillow])
        layout = make_layout(row, selection(row, 'footprint'))
        self.assertEqual(len(layout['instances']), 7)
        self.assertEqual(sum(s['counts_as_furniture'] for s in layout['instances']), 5)

    def test_stale_selection_passed_image_or_unknown_component_checks_rejected(self):
        row = review([part('pan')])
        stale = selection(row); stale['definition_sha256'] = 'c' * 64
        with self.assertRaises(ValueError): make_layout(row, stale)
        extra = selection(row); extra['component_checks']['other'] = ['extra']
        with self.assertRaises(ValueError): make_layout(row, extra)
        row['verdict'] = 'pass'
        with self.assertRaises(ValueError): make_layout(row, selection(row))

    def test_noninteger_quantity_missing_dimensions_and_duplicate_roles_rejected(self):
        for parts in ([part('pan', True)], [part('pan', 1.5)], [part('pan', 0)], [part('pan'), part('pan')]):
            row = review(parts)
            with self.assertRaises(ValueError): make_layout(row, selection(row))
        row = review([part('pan')]); del row['contract']['components'][0]['dimensions_cm']['lab_spec_width_cm']
        row['definition_sha256'] = digest(row['contract'])
        with self.assertRaisesRegex(ValueError, 'dimension'):
            make_layout(row, selection(row))

    def test_validator_rejects_missing_duplicate_or_wrong_instances(self):
        row = review([part('pan', 2), part('lid')])
        valid = make_layout(row, selection(row))
        changed = copy.deepcopy(valid); changed['instances'].pop()
        with self.assertRaises(ValueError): validate_layout(changed, row['contract'])
        changed = copy.deepcopy(valid); changed['instances'][1] = changed['instances'][0]
        with self.assertRaises(ValueError): validate_layout(changed, row['contract'])
        changed = copy.deepcopy(valid); changed['instances'][0]['component_id'] = 'unknown'
        with self.assertRaises(ValueError): validate_layout(changed, row['contract'])

    def test_validator_rejects_overlap_off_canvas_and_distorted_scale(self):
        row = review([part('pan', 2)])
        valid = make_layout(row, selection(row))
        for value in (-1, float('nan'), 100000):
            changed = copy.deepcopy(valid); changed['instances'][0]['box']['x'] = value
            with self.assertRaises(ValueError): validate_layout(changed, row['contract'])
        changed = copy.deepcopy(valid); changed['instances'][1]['box'] = changed['instances'][0]['box']
        with self.assertRaisesRegex(ValueError, 'overlap'): validate_layout(changed, row['contract'])
        changed = copy.deepcopy(valid); changed['instances'][0]['box']['width'] *= .5
        with self.assertRaisesRegex(ValueError, 'scale'): validate_layout(changed, row['contract'])

    def test_svg_is_schematic_and_escapes_labels(self):
        row = review([part('pan')]); row['contract']['product_name'] = '<script>bad</script>'
        row['definition_sha256'] = digest(row['contract'])
        layout = make_layout(row, selection(row))
        svg = render_svg(layout)
        self.assertNotIn('<script>', svg)
        self.assertIn('&lt;script&gt;', svg)
        self.assertIn('SCHEMATIC', svg)
        self.assertEqual(svg.count('class="component-envelope"'), 1)
        self.assertNotIn('<image', svg)

    def test_briefs_are_not_executable_jobs_or_image_approvals(self):
        row = review([part('pan', 2)])
        layout = make_layout(row, selection(row))
        brief = component_briefs(row, selection(row), layout)[0]
        self.assertEqual(brief['required_instances'], 2)
        self.assertEqual(brief['acceptance'], 'pending')
        self.assertFalse(brief['executable'])
        self.assertNotIn('prompt', brief)
        self.assertNotIn('output_file', brief)
        self.assertNotIn('reference_images', brief)

    def test_grouping_cannot_drop_or_reassign_an_instance(self):
        row = review([part('pan', 2), part('lid')])
        layout = make_layout(row, selection(row))
        layout['groups'][0]['instance_ids'] = ['lid-01']
        with self.assertRaisesRegex(ValueError, 'grouping'):
            validate_layout(layout, row['contract'])

    def test_shifted_lamp_breaks_shared_floor_even_without_overlap(self):
        row = review([part('floor', height=165), part('table', 2, height=52)])
        layout = make_layout(row, selection(row, 'shared_floor'))
        layout['instances'][1]['box']['y'] -= 1
        with self.assertRaisesRegex(ValueError, 'floor plane'):
            validate_layout(layout, row['contract'])

    def test_briefs_preserve_parent_appearance_and_exclusions(self):
        row = review([part('pan')])
        row['contract']['specifications'] = {'material': {'value': 'Copper finish'}}
        row['definition_sha256'] = digest(row['contract'])
        brief = component_briefs(row, selection(row), make_layout(row, selection(row)))[0]
        self.assertEqual(brief['parent_specifications'], row['contract']['specifications'])
        self.assertEqual(brief['parent_constraints'], ['No extra products.'])
        self.assertEqual(brief['selected_options'], {'finish': 'Bronze'})

    def test_build_pins_scope_and_preserves_existing_output(self):
        row = review([part('pan', 2), part('lid')]); row['next_direction'] = 'Review complete components.'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'review'; source.mkdir()
            (source/'manifest.json').write_text(json.dumps({'run': str(root/'run')}))
            choices = root/'selection.json'; choices.write_text(json.dumps([selection(row)]))
            output = root/'layout'
            with patch('plan_catalog_component_layouts.read_review', return_value=([row], {})):
                counts = build(source, choices, output)
                self.assertEqual((counts['layouts'], counts['component_types'], counts['physical_instances']), (1, 2, 3))
                before = (output/'manifest.json').read_bytes()
                with self.assertRaisesRegex(ValueError, 'fresh'): build(source, choices, output)
                self.assertEqual((output/'manifest.json').read_bytes(), before)
            manifest = json.loads(before)
            self.assertEqual(manifest['inputs'][str(choices.resolve())], sha256(choices))
            self.assertFalse(manifest['generation_approved'])
            self.assertEqual(len(manifest['outputs']), 4)

    def test_input_change_prevents_partial_packet_publication(self):
        row = review([part('pan')]); row['next_direction'] = 'Review one component.'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'review'; source.mkdir()
            (source/'manifest.json').write_text(json.dumps({'run': str(root/'run')}))
            choices = root/'selection.json'; choices.write_text(json.dumps([selection(row)]))
            changed = root/'pinned-input'; changed.write_text('changed')
            output = root/'layout'
            with patch('plan_catalog_component_layouts.read_review', return_value=([row], {str(changed): 'a'*64})):
                with self.assertRaisesRegex(ValueError, 'Pinned input changed'):
                    build(source, choices, output)
            self.assertFalse(output.exists())
            self.assertEqual(changed.read_text(), 'changed')

    def test_review_displays_readable_actions_instead_of_unbreakable_internal_codes(self):
        counts = {'layouts': 0, 'component_types': 0, 'physical_instances': 0, 'model_calls': 0}
        coverage = [{'root_sku':'WANDS-000001', 'action':'retain_local_candidate_pending_use_approval',
                     'reason':'Keep the initial pass local.'}]
        html = render_html([], [], coverage, counts)
        self.assertNotIn('retain_local_candidate_pending_use_approval', html)
        self.assertIn('Keep local; image use not approved', html)

    def test_cli_failure_stays_in_log_without_output_packet(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); out = root / 'layout'
            cmd = [sys.executable, str(Path(__file__).resolve().parents[1] / 'plan_catalog_component_layouts.py'),
                   '--review', str(root / 'missing'), '--selection', str(root / 'missing.json'), '--output-dir', str(out)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout + result.stderr, '')
            self.assertFalse(out.exists())
            self.assertIn('Component layout planning stopped', out.with_suffix('.log').read_text())


if __name__ == '__main__':
    unittest.main()
