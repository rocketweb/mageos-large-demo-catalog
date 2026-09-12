import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reconcile_catalog_media import digest, make_contract, prepare_reviews
from test_reconcile_catalog_media import fixture
from plan_catalog_media_repairs import make_plan, verify_review_packet, render_plan, SETTINGS


def inputs(verdict='uncertain', disposition='clarify_hero'):
    root, children, review = fixture()
    note = {'root_sku': root['sku'], 'selected_sku': review['selected_sku'],
            'reference_sha256': review['reference']['sha256'],
            'definition_sha256': digest(make_contract(root, children, review)),
            'finding': 'Unclear surface', 'repair_direction': 'Use the approved Black finish.',
            'observation': 'Inspected locally', 'verdict': verdict}
    rows = prepare_reviews([root], children, [review], [], [note])
    decision = {k: note[k] for k in ('root_sku', 'selected_sku', 'reference_sha256', 'definition_sha256', 'observation')}
    decision.update(disposition=disposition, evidence='Visible identity is plausible.', direction='Keep the selected finish.')
    selection = [{'root_sku': root['sku'], 'challenge': 'Finish', 'framing': 'Show one compact nightstand.'}]
    return rows, [decision] if verdict == 'uncertain' else [], selection


class MediaRepairPlanTest(unittest.TestCase):
    def test_clarity_action_does_not_relabel_uncertainty_as_a_defect(self):
        rows, decisions, selection = inputs()
        original = copy.deepcopy(rows)
        plan, counts = make_plan(rows, decisions, selection)
        self.assertEqual(plan[0]['proposed_action'], 'clarify_hero')
        self.assertEqual(counts['confirmed_repairs'], 0)
        self.assertEqual(counts['clarity_repairs'], 1)
        self.assertNotIn('Confirmed reference defect:', plan[0]['draft_instruction'])
        self.assertEqual(rows, original)

    def test_known_defect_remains_repair_and_does_not_need_a_focused_decision(self):
        rows, decisions, selection = inputs('fail')
        plan, counts = make_plan(rows, decisions, selection)
        self.assertEqual(plan[0]['proposed_action'], 'repair_confirmed_defect')
        self.assertEqual(counts['confirmed_repairs'], 1)
        self.assertIn('Confirmed reference defect:', plan[0]['draft_instruction'])

    def test_retained_candidates_are_excluded_from_pilot_and_repair_count(self):
        rows, decisions, selection = inputs(disposition='retain_candidate')
        with self.assertRaisesRegex(ValueError, 'retained'):
            make_plan(rows, decisions, selection)
        other, _, other_selection = inputs('fail')
        other[0]['contract']['root_sku'] = 'WANDS-999999'
        other[0]['definition_sha256'] = digest(other[0]['contract'])
        other_selection[0]['root_sku'] = 'WANDS-999999'
        plan, counts = make_plan(rows + other, decisions, other_selection)
        retained = next(p for p in plan if p['proposed_action'] == 'retain_candidate')
        self.assertIsNone(retained['proposed_image_basename'])
        self.assertIsNone(retained['draft_instruction'])
        self.assertFalse(retained['reference_use_approved'])
        self.assertEqual(counts['retained_candidates'], 1)
        self.assertEqual(counts['proposed_repair_images'], 1)

    def test_focused_decisions_require_exact_unique_uncertain_scope(self):
        rows, decisions, selection = inputs()
        for notes in ([], decisions + decisions, [{**decisions[0], 'root_sku': 'unknown'}]):
            with self.subTest(notes=notes), self.assertRaises(ValueError):
                make_plan(rows, notes, selection)
        with self.assertRaises(ValueError):
            make_plan(rows + rows, decisions, selection)

    def test_stale_focused_observation_and_approval_are_rejected(self):
        rows, decisions, selection = inputs()
        for field in ('selected_sku', 'reference_sha256', 'definition_sha256', 'disposition', 'evidence', 'direction', 'observation'):
            value = '' if field in {'evidence', 'direction', 'observation'} else 'approved'
            with self.subTest(field=field), self.assertRaises(ValueError):
                make_plan(rows, [{**decisions[0], field: value}], selection)

    def test_pilot_must_be_nonempty_unique_known_and_bounded(self):
        rows, decisions, selection = inputs()
        for specs in ([], selection * 2, selection * 13, [{**selection[0], 'root_sku': 'unknown'}]):
            with self.subTest(specs=specs), self.assertRaises(ValueError):
                make_plan(rows, decisions, specs)

    def test_unreviewed_and_approved_rows_cannot_enter_plan(self):
        rows, decisions, selection = inputs()
        for status in ('not_reviewed_for_corrected_definition', 'approved'):
            changed = copy.deepcopy(rows); changed[0]['visual_status'] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                make_plan(changed, decisions, selection)

    def test_plan_is_non_executable_and_uses_fingerprint_names(self):
        rows, decisions, selection = inputs()
        plan, counts = make_plan(rows, decisions, selection)
        row = plan[0]
        self.assertFalse({'prompt', 'output_file', 'reference_images'} & set(row))
        self.assertFalse(row['executable'])
        self.assertFalse(row['reference_use_approved'])
        self.assertIn('Do not condition generation on the existing reference', row['draft_instruction'])
        self.assertEqual(counts['images_generated'], 0)
        self.assertEqual(counts['model_calls'], 0)
        self.assertEqual(counts['pilot_images_proposed'], 1)
        changed = copy.deepcopy(decisions); changed[0]['direction'] = 'A different approved direction.'
        other, _ = make_plan(rows, changed, selection)
        self.assertNotEqual(row['proposed_image_basename'], other[0]['proposed_image_basename'])
        self.assertEqual(Path(row['proposed_image_basename']).name, row['proposed_image_basename'])
        self.assertEqual(SETTINGS['max_attempts_per_root'], 1)

    def test_component_checklist_preserves_counts_and_scopes(self):
        rows, decisions, selection = inputs('fail')
        rows[0]['contract']['components'] = [{'component_id': 'chairs', 'label': 'Chair', 'quantity': 4,
                                            'scope': 'each chair', 'dimensions_cm': {'lab_spec_width_cm': 50, 'lab_spec_depth_cm': 50},
                                            'counts_as_furniture': True}]
        rows[0]['contract']['total_component_quantity'] = 4
        rows[0]['contract']['furniture_piece_count'] = 4
        plan, _ = make_plan(rows, decisions, selection)
        self.assertEqual(plan[0]['acceptance_contract']['components'], rows[0]['contract']['components'])
        self.assertEqual(plan[0]['acceptance_contract']['sale_unit'], rows[0]['contract']['sale_unit'])

    def test_renderer_keeps_proposal_distinct_from_generated_results(self):
        rows, decisions, selection = inputs()
        plan, counts = make_plan(rows, decisions, selection)
        page = render_plan(plan, counts)
        self.assertIn('Awaiting approval', page)
        self.assertIn('No images have been generated', page)
        self.assertIn('Stop after', page)
        self.assertIn('not a random sample', page)

    def test_verifier_rejects_unsafe_or_unexpected_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            for outputs in ({'../escape': 'a' * 64}, {}):
                (p / 'manifest.json').write_text(json.dumps({'outputs': outputs, 'inputs': {}}))
                with self.subTest(outputs=outputs), self.assertRaises(ValueError):
                    verify_review_packet(p)

    def test_independent_row_verification_rejects_rehashed_semantic_tampering(self):
        from plan_catalog_media_repairs import verify_review_row
        rows, _, _ = inputs('fail')
        root, children, review = fixture()
        rows[0]['integrity']['status'] = 'valid_image_bytes'
        mutations = [
            lambda r: r['contract'].update(product_name='Different product'),
            lambda r: r.update(definition_sha256='b' * 64),
            lambda r: r['reference'].update(sha256='b' * 64),
            lambda r: r['finding'].update(verdict='pass'),
            lambda r: r['finding'].update(selected_sku='different'),
            lambda r: r.update(reference_use_approved=True),
            lambda r: r.update(executable=True),
            lambda r: r.update(visual_status='reviewed_uncertain'),
            lambda r: r['integrity'].update(status='decode_failed'),
        ]
        with patch('plan_catalog_media_repairs.sha256', return_value='a' * 64):
            verify_review_row(rows[0], root, children, review)
            for index, mutate in enumerate(mutations):
                changed = copy.deepcopy(rows[0]); mutate(changed)
                with self.subTest(mutation=index), self.assertRaises(ValueError):
                    verify_review_row(changed, root, children, review)

    def test_cli_failure_is_quiet_and_publishes_no_packet(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'plan'
            result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'plan_catalog_media_repairs.py'),
                                     '--review', str(Path(folder) / 'missing'), '--decisions', 'missing.json',
                                     '--pilot-selection', 'missing.json', '--output-dir', str(target)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout + result.stderr, '')
            self.assertFalse(target.exists())
            self.assertIn('stopped', target.with_suffix('.log').read_text())


if __name__ == '__main__':
    unittest.main()
