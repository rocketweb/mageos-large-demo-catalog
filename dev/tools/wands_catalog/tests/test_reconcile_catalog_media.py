import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from catalog_repairs import repair_family
from definition_resolutions import remaining_rules
from generate_reference_images import pending_jobs
from prepare_catalog import sha256
from test_catalog_repairs import family
from reconcile_catalog_media import inspect_reference, make_contract, prepare_reviews, render_review, digest, blocked_views


def fixture(sku='WANDS-022607', axes=None):
    root, children = family(sku, axes or {'wands_length': ['30 in', '36 in', '48 in'],
                                        'wands_finish': ['Walnut', 'Oak']})
    root, children, _ = repair_family(root, children, remaining_rules()[sku])
    child = next(c for c in children if c['sku'] == root['gallery_target']['sku']) if children else root
    ref = {'path': '/unread/test.jpg', 'sha256': 'a' * 64, 'source_sku': sku}
    root['reference'] = child['reference'] = ref
    review = {'root_sku': sku, 'selected_sku': child['sku'], 'reference': ref,
              'selected_options': child['variant_options'], 'sale_unit': child['catalog_fields']['lab_sale_unit'],
              'design': child['dimension_design'], 'executable': False, 'status': 'not_visually_accepted'}
    return root, children, review


class ReconcileCatalogMediaTest(unittest.TestCase):
    def test_contract_uses_corrected_options_not_old_sku_tokens(self):
        root, children, review = fixture()
        contract = make_contract(root, children, review)
        self.assertIn(contract['selected_options']['wands_finish'], {'Clear', 'Black'})
        self.assertEqual(contract['selected_options']['wands_length'], '18 in')
        self.assertEqual(contract['dimensions_cm']['lab_spec_width_cm'], 45.72)
        self.assertIn('Synthetic lab', contract['required_disclosure'])

    def test_contract_rejects_changed_review_options(self):
        root, children, review = fixture()
        review = copy.deepcopy(review)
        review['selected_options']['wands_finish'] = 'Walnut'
        with self.assertRaisesRegex(ValueError, 'options'):
            make_contract(root, children, review)

    def test_contract_rejects_cross_family_target(self):
        root, children, review = fixture()
        children[0]['parent_sku'] = 'WANDS-999999'
        review['selected_sku'] = children[0]['sku']
        root['gallery_target']['sku'] = children[0]['sku']
        with self.assertRaisesRegex(ValueError, 'family'):
            make_contract(root, children, review)

    def test_contract_rejects_changed_reference(self):
        root, children, review = fixture()
        review = copy.deepcopy(review)
        review['reference']['sha256'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'reference'):
            make_contract(root, children, review)

    def test_furniture_quantity_excludes_pillows_but_lists_them(self):
        root, children, review = fixture('WANDS-014542', {'wands_piece_count': ['2 Pieces', '3 Pieces', '4 Pieces']})
        contract = make_contract(root, children, review)
        self.assertEqual(contract['furniture_piece_count'], 4)
        self.assertEqual(contract['total_component_quantity'], 6)
        pillows = next(c for c in contract['components'] if c['component_id'] == 'pillows')
        self.assertEqual(pillows['quantity'], 2)
        self.assertFalse(pillows['counts_as_furniture'])
        self.assertEqual(contract['dimensions_cm'], {})

    def test_simple_root_does_not_require_a_retired_child(self):
        root, children, review = fixture('WANDS-003817', {'wands_size': ['Toddler', 'Twin', 'Full', 'Queen']})
        contract = make_contract(root, children, review)
        self.assertEqual(contract['selected_sku'], root['sku'])
        self.assertEqual(contract['selected_options'], {})
        self.assertIn('No infant', ' '.join(contract['constraints']))

    def test_component_count_tampering_is_rejected(self):
        root, children, review = fixture('WANDS-014542', {'wands_piece_count': ['2 Pieces', '3 Pieces', '4 Pieces']})
        chosen = next(c for c in children if c['sku'] == review['selected_sku'])
        chosen['dimension_design']['components'][0]['quantity'] = 0
        with self.assertRaisesRegex(ValueError, 'quantity'):
            make_contract(root, children, review)

    def test_valid_image_is_not_visually_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.jpg'
            Image.new('RGB', (768, 768), 'white').save(path)
            result = inspect_reference({'path': str(path), 'sha256': sha256(path)})
            self.assertEqual(result['status'], 'valid_image_bytes')
            self.assertEqual([result['width'], result['height']], [768, 768])
            self.assertFalse(result['visual_acceptance'])

    def test_wrong_hash_is_not_decoded_or_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.jpg'
            Image.new('RGB', (16, 16)).save(path)
            result = inspect_reference({'path': str(path), 'sha256': 'b' * 64})
            self.assertEqual(result['status'], 'hash_mismatch')
            self.assertFalse(result['visual_acceptance'])

    def test_corrupt_image_and_missing_reference_are_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.jpg'
            path.write_bytes(b'not an image')
            self.assertEqual(inspect_reference({'path': str(path), 'sha256': sha256(path)})['status'], 'decode_failed')
            self.assertEqual(inspect_reference({'path': str(path.with_name('absent.jpg')), 'sha256': 'a'*64})['status'], 'missing_file')
            self.assertEqual(inspect_reference(None)['status'], 'missing_reference')

    def test_geometry_or_options_change_definition_fingerprint(self):
        root, children, review = fixture()
        contract = make_contract(root, children, review)
        changed = copy.deepcopy(contract)
        changed['selected_options']['wands_finish'] = 'Other'
        self.assertNotEqual(digest(contract), digest(changed))
        changed = copy.deepcopy(contract)
        changed['dimensions_cm']['lab_spec_width_cm'] += 1
        self.assertNotEqual(digest(contract), digest(changed))

    def test_known_failure_is_byte_and_definition_bound(self):
        root, children, review = fixture()
        draft = {**review, 'finding': 'Wrong finish', 'prompt': 'Correct the finish.'}
        result = prepare_reviews([root], children, [review], [draft])[0]
        self.assertEqual(result['priority'], 0)
        self.assertEqual(result['visual_status'], 'known_reference_defect')
        self.assertIn('Correct the finish.', result['draft_prompt'])
        draft = copy.deepcopy(draft)
        draft['reference']['sha256'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'finding'):
            prepare_reviews([root], children, [review], [draft])

    def test_review_scope_is_exact_and_unique(self):
        root, children, review = fixture()
        with self.assertRaises(ValueError):
            prepare_reviews([root], children, [review, review], [])
        with self.assertRaisesRegex(ValueError, 'scope'):
            prepare_reviews([root], children, [], [])

    def test_supplemental_findings_require_reference_and_definition_hashes(self):
        root, children, review = fixture()
        finding = {'root_sku': root['sku'], 'selected_sku': review['selected_sku'],
                   'reference_sha256': review['reference']['sha256'],
                   'definition_sha256': digest(make_contract(root, children, review)),
                   'finding': 'Wrong finish', 'repair_direction': 'Use the selected Black finish.',
                   'observation': 'Local visual inspection, not manufacturer validation', 'verdict': 'fail'}
        rows = prepare_reviews([root], children, [review], [], [finding])
        self.assertEqual(rows[0]['visual_status'], 'known_reference_defect')
        for field in ('definition_sha256', 'reference_sha256', 'selected_sku'):
            changed = {**finding, field: 'changed'}
            with self.assertRaisesRegex(ValueError, 'finding'):
                prepare_reviews([root], children, [review], [], [changed])
        with self.assertRaisesRegex(ValueError, 'approval'):
            prepare_reviews([root], children, [review], [], [{**finding, 'verdict': 'pass'}])

    def test_all_five_gallery_views_are_bound_to_current_design(self):
        root, children, review = fixture()
        rows = prepare_reviews([root], children, [review], [])
        briefs = [{'source_product_id': root['source_product_id'], 'sku': review['selected_sku'],
                   'view': view, 'job_id': review['selected_sku'] + ':' + view,
                   'selected_options': review['selected_options'], 'executable': False}
                  for view in ('hero', 'angle', 'detail', 'room', 'dimensions')]
        deps = blocked_views(briefs, rows)
        self.assertEqual(len(deps), 5)
        self.assertTrue(all(d['definition_sha256'] == rows[0]['definition_sha256'] for d in deps))
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            blocked_views(briefs[:-1], rows)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            blocked_views([*briefs, briefs[0]], rows)
        briefs[0]['selected_options'] = {'wands_finish': 'Walnut'}
        with self.assertRaisesRegex(ValueError, 'options'):
            blocked_views(briefs, rows)

    def test_uncertain_observation_is_neither_a_confirmed_defect_nor_approval(self):
        root, children, review = fixture()
        note = {'root_sku': root['sku'], 'selected_sku': review['selected_sku'],
                'reference_sha256': review['reference']['sha256'],
                'definition_sha256': digest(make_contract(root, children, review)), 'verdict': 'uncertain',
                'finding': 'Geometry needs closer review.', 'repair_direction': 'Inspect proportions before choosing a repair.',
                'observation': 'Local visual triage only'}
        row = prepare_reviews([root], children, [review], [], [note])[0]
        self.assertEqual(row['visual_status'], 'reviewed_uncertain')
        self.assertFalse(row['reference_use_approved'])
        self.assertFalse(row['executable'])
        self.assertEqual(row['next_action'], 'focused_visual_design_review')
        self.assertNotIn('Confirmed reference defect', row['draft_prompt'])
        self.assertIn('not an instruction to regenerate', row['draft_prompt'])
        page = render_review([row], {'review_roots': 1, 'known_reference_defects': 0,
                                    'technically_valid_references': 0, 'blocked_gallery_views': 5,
                                    'reviewed_uncertain_references': 1, 'not_visually_reviewed_roots': 0})
        self.assertIn('Review uncertainty:', page)
        self.assertNotIn('Confirmed defect:', page)

    def test_triage_counts_do_not_count_uncertainty_as_failure_or_unreviewed(self):
        from reconcile_catalog_media import triage_counts
        rows = [{'visual_status': status} for status in
                ['known_reference_defect', 'reviewed_uncertain', 'not_reviewed_for_corrected_definition']]
        self.assertEqual(triage_counts(rows), {'known_reference_defects': 1, 'reviewed_uncertain_references': 1,
                                              'visually_reviewed_roots': 2, 'not_visually_reviewed_roots': 1})
        with self.assertRaisesRegex(ValueError, 'visual status'):
            triage_counts([{'visual_status': 'approved'}])

    def test_same_root_cannot_receive_conflicting_observations(self):
        root, children, review = fixture()
        note = {'root_sku': root['sku']}
        with self.assertRaises(ValueError):
            prepare_reviews([root], children, [review], [], [note, note])

    def test_conflicting_original_resolution_story_stays_out_of_prompt(self):
        root, children, review = fixture()
        root['repair']['rationale'] = 'Historical conflict: a walnut wardrobe with fifty drawers.'
        result = prepare_reviews([root], children, [review], [])[0]
        self.assertNotIn('fifty drawers', result['draft_prompt'])
        self.assertIn('fifty drawers', result['contract']['resolution_basis'])

    def test_non_executable_packet_cannot_be_used_as_generation_jobs(self):
        root, children, review = fixture()
        rows = prepare_reviews([root], children, [review], [])
        self.assertFalse(rows[0]['executable'])
        self.assertNotIn('output_file', rows[0])
        self.assertNotIn('prompt', rows[0])
        self.assertIn('not a manufacturer', rows[0]['draft_prompt'])
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(KeyError):
            pending_jobs(rows, Path(folder), {})

    def test_render_escapes_catalog_text_and_keeps_reference_unapproved(self):
        root, children, review = fixture()
        root['name'] = '<script>alert(1)</script>'
        rows = prepare_reviews([root], children, [review], [])
        page = render_review(rows, {'review_roots': 1, 'known_reference_defects': 0,
                                   'technically_valid_references': 0, 'blocked_gallery_views': 5})
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', page)
        self.assertNotIn('<script>alert', page)
        self.assertIn('Not visually accepted', page)
        self.assertIn('Never infer exact dimensions from pixels', page)

    def test_cli_failure_is_quiet_and_leaves_no_packet(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'review'
            result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'reconcile_catalog_media.py'),
                                     '--definitions', str(Path(folder) / 'missing'), '--output-dir', str(target)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout + result.stderr, '')
            self.assertFalse(target.exists())
            self.assertIn('stopped', target.with_suffix('.log').read_text())


if __name__ == '__main__':
    unittest.main()
