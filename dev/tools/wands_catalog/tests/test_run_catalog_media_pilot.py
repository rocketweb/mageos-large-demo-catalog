import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_catalog_media_pilot import compile_prompt, check_token_budget, pending_cases, generate_cases, verify_plan, publish_exclusive
from generate_images import append_event
from prepare_catalog import sha256
from PIL import Image


def case():
    return {'root_sku': 'WANDS-000001', 'selected_sku': 'WANDS-000001-OLD-OAK',
            'definition_sha256': 'a' * 64, 'proposed_seed': 42,
            'acceptance_contract': {'product_name': 'Synthetic One-Drawer Cabinet',
                'selected_options': {'finish': 'Black'}, 'sale_unit': '1 cabinet',
                'specifications': {'lab_spec_care': {'value': 'wash'}, 'lab_spec_finish': {'value': 'Black'}},
                'dimensions_cm': {'lab_spec_width_cm': 45}, 'components': [],
                'required_disclosure': 'Synthetic lab dimensions, not manufacturer measurements.'},
            'pilot_case': {'framing': 'Exactly one drawer; no extra furniture.'}}


def execution_case():
    return {**case(), 'runtime_prompt': compile_prompt(case()), 'runtime_prompt_sha256': 'b' * 64,
            'candidate_filename': 'WANDS-000001-hero-test.webp'}


class MediaPilotRunTest(unittest.TestCase):
    def test_prompt_keeps_visual_facts_not_admin_story_or_old_sku(self):
        c = case(); c['acceptance_contract']['resolution_basis'] = 'Wrong historical oak wardrobe'
        text = compile_prompt(c)
        self.assertIn('Black', text)
        self.assertIn('Exactly one drawer', text)
        self.assertNotIn('OLD-OAK', text)
        self.assertNotIn('wardrobe', text)
        self.assertNotIn('wash', text)
        self.assertNotIn('DRAFT ONLY', text)

    def test_component_quantities_and_geometry_survive_prompt_compaction(self):
        c = case(); c['acceptance_contract']['components'] = [
            {'quantity': 8, 'label': 'Dinner fork', 'dimensions_cm': {'lab_spec_length_cm': 20}},
            {'quantity': 1, 'label': 'Serving spoon', 'dimensions_cm': {'lab_spec_length_cm': 25}}]
        text = compile_prompt(c)
        self.assertIn('8 x Dinner fork', text)
        self.assertIn('1 x Serving spoon', text)
        self.assertIn('L20cm', text)
        self.assertIn('L25cm', text)

    def test_token_budget_rejects_truncation_instead_of_silently_slicing(self):
        tokenizer = Mock()
        tokenizer.apply_chat_template.return_value = 'wrapped'
        tokenizer.return_value = {'input_ids': list(range(513))}
        with self.assertRaisesRegex(ValueError, '512-token'):
            check_token_budget('prompt', tokenizer)
        tokenizer.return_value = {'input_ids': list(range(512))}
        self.assertEqual(check_token_budget('prompt', tokenizer), 512)
        self.assertFalse(tokenizer.call_args.kwargs['truncation'])

    def test_no_attempt_can_be_retried_after_interruption_or_failure(self):
        c = execution_case()
        for terminal in (None, 'failed'):
            with tempfile.TemporaryDirectory() as folder:
                p = Path(folder); ledger = p/'events.jsonl'
                append_event(ledger, {'status': 'attempt_started', 'root_sku': c['root_sku']})
                if terminal:
                    append_event(ledger, {'status': terminal, 'root_sku': c['root_sku']})
                with self.assertRaisesRegex(ValueError, 'already attempted'):
                    pending_cases([c], p)

    def test_unknown_duplicate_and_malformed_attempt_history_is_rejected(self):
        c = execution_case()
        histories = [
            [{'status': 'attempt_started', 'root_sku': 'unknown'}],
            [{'status': 'attempt_started', 'root_sku': c['root_sku']}] * 2,
            [{'status': 'generated', 'root_sku': c['root_sku']}],
        ]
        for history in histories:
            with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
                p = Path(folder)
                for event in history: append_event(p/'events.jsonl', event)
                pending_cases([c], p)
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            p = Path(folder); (p/'events.jsonl').write_text('{broken\n')
            pending_cases([c], p)

    def test_untracked_or_symlink_output_is_never_overwritten(self):
        c = execution_case()
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder); target=p/c['candidate_filename']; target.write_bytes(b'user data')
            with self.assertRaises(ValueError): pending_cases([c], p)
            self.assertEqual(target.read_bytes(), b'user data')
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder); (p/c['candidate_filename']).symlink_to(p/'absent')
            with self.assertRaises(ValueError): pending_cases([c], p)

    def test_success_is_bound_to_image_and_metadata_bytes_and_not_regenerated(self):
        c = execution_case()
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            model = Mock(); model.generate_image.return_value.image = Image.new('RGB', (768,768), 'white')
            summary=generate_cases([c], p, model, lambda: None)
            self.assertEqual(summary['generated'], 1)
            self.assertEqual(model.generate_image.call_count, 1)
            self.assertEqual(pending_cases([c],p), [])
            events=[json.loads(l) for l in (p/'events.jsonl').read_text().splitlines()]
            self.assertEqual([r['status'] for r in events], ['attempt_started','generated'])
            metadata=json.loads((p/(c['candidate_filename']+'.json')).read_text())
            self.assertEqual(metadata['visual_acceptance'], 'pending')
            self.assertIn('Synthetic', metadata['required_disclosure'])
            (p/c['candidate_filename']).write_bytes(b'changed')
            with self.assertRaises(ValueError): pending_cases([c],p)

    def test_model_failure_consumes_one_attempt_and_stops_the_run(self):
        first=execution_case(); second={**execution_case(), 'root_sku':'WANDS-000002','candidate_filename':'second.webp'}
        model=Mock(); model.generate_image.side_effect=RuntimeError('GPU failed')
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder); summary=generate_cases([first,second],p,model,lambda:None)
            self.assertEqual(summary['failed'],1)
            self.assertEqual(model.generate_image.call_count,1)
            with self.assertRaisesRegex(ValueError,'already attempted'):pending_cases([first,second],p)

    def test_input_change_stops_before_spending_an_attempt(self):
        model=Mock()
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            with self.assertRaises(ValueError):
                generate_cases([execution_case()],p,model,Mock(side_effect=ValueError('changed input')))
            model.generate_image.assert_not_called()
            self.assertFalse((p/'events.jsonl').exists())

    def test_plan_authorization_is_bound_to_exact_manifest_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder); (p/'manifest.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'approved plan'):
                verify_plan(p,'a'*64)

    def test_atomic_publication_never_replaces_existing_data(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'candidate.webp'; target.write_bytes(b'original')
            with self.assertRaises(FileExistsError): publish_exclusive(target,b'replacement')
            self.assertEqual(target.read_bytes(),b'original')
            self.assertEqual(list(Path(folder).iterdir()),[target])

    def test_cli_bad_approval_is_quiet_and_does_not_create_a_run(self):
        with tempfile.TemporaryDirectory() as folder:
            plan=Path(folder)/'plan'; plan.mkdir(); (plan/'manifest.json').write_text('{}')
            output=Path(folder)/'run'
            result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'run_catalog_media_pilot.py'),
                '--plan',str(plan),'--approved-plan-sha256','a'*64,'--output-dir',str(output),'--run'],capture_output=True,text=True)
            self.assertEqual(result.returncode,1)
            self.assertEqual(result.stdout+result.stderr,'')
            self.assertFalse(output.exists())
            self.assertIn('approved plan',output.with_suffix('.log').read_text())


if __name__ == '__main__': unittest.main()
