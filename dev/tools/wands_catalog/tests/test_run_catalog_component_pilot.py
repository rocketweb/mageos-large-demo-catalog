import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_catalog_component_pilot import compile_prompt, select_cases, pending_assets, generate_assets
from generate_images import append_event
from prepare_catalog import sha256


def brief(cid='table-lamps'):
    return {'asset_requirement_id':'WANDS-000001-'+cid+'-abc', 'root_sku':'WANDS-000001',
            'component_id':cid, 'definition_sha256':'a'*64, 'layout_sha256':'b'*64,
            'component':{'label':'Table lamp', 'dimensions_cm':{'lab_spec_width_cm':30,'lab_spec_height_cm':52}},
            'parent_product_name':'Three-piece lamp set', 'selected_options':{'wands_finish':'Bronze','wands_piece_count':'3 Pieces'},
            'parent_specifications':{'lab_spec_style':{'value':'Traditional'},'lab_spec_care':{'value':'wipe clean'}},
            'view':'front elevation', 'required_instances':2, 'construction_checks':['Place it twice.'],
            'required_disclosure':'Synthetic lab design, not manufacturer measurements.'}


def choice(cid='table-lamps'):
    return {'asset_requirement_id':brief(cid)['asset_requirement_id'],'visual_instruction':'One complete lamp with a supported shade.',
            'purpose':'Test one complete object.','max_attempts':1}


def runtime_case(cid='table-lamps'):
    c = select_cases([brief(cid)], [choice(cid)])[0]
    return {**c, 'token_count':120, 'candidate_filename':cid+'.webp'}


class ComponentPilotTest(unittest.TestCase):
    def test_model_prompt_has_one_object_and_no_family_quantities_or_legacy_instructions(self):
        text = compile_prompt(brief(), choice())
        self.assertIn('exactly ONE complete Table lamp', text)
        self.assertIn('Bronze', text)
        self.assertIn('Traditional', text)
        for forbidden in ('Three-piece', '3 Pieces', 'Place it twice', 'wipe clean', 'WANDS-', '52cm'):
            self.assertNotIn(forbidden, text)
        self.assertIn('1.73', text)

    def test_exact_selection_is_bounded_and_preserves_root_and_component_identity(self):
        cases = select_cases([brief(), brief('floor-lamp')], [choice(), choice('floor-lamp')])
        self.assertEqual(len(cases), 2)
        self.assertEqual(len({c['asset_requirement_id'] for c in cases}), 2)
        self.assertEqual({c['root_sku'] for c in cases}, {'WANDS-000001'})
        self.assertEqual(cases[0]['brief'], brief())

    def test_unknown_duplicate_empty_and_over_limit_selections_rejected(self):
        for choices in ([], [choice(),choice()], [choice(str(i)) for i in range(5)], [choice('unknown')]):
            with self.assertRaises(ValueError):
                select_cases([brief()], choices)

    def test_multiple_attempts_and_invalid_geometry_rejected(self):
        c = choice(); c['max_attempts'] = 2
        with self.assertRaises(ValueError): select_cases([brief()], [c])
        b = brief(); del b['component']['dimensions_cm']['lab_spec_width_cm']
        with self.assertRaises(ValueError): compile_prompt(b, choice())

    def test_interruption_or_failure_consumes_attempt_without_retry(self):
        for terminal in (None, 'failed'):
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder); c=runtime_case()
                append_event(root/'events.jsonl', {'asset_requirement_id':c['asset_requirement_id'],'status':'attempt_started'})
                if terminal:
                    append_event(root/'events.jsonl', {'asset_requirement_id':c['asset_requirement_id'],'status':terminal})
                with self.assertRaisesRegex(ValueError, 'already attempted'):
                    pending_assets([c], root)

    def test_unknown_duplicate_and_orphan_events_rejected(self):
        c=runtime_case(); key=c['asset_requirement_id']
        for events in ([{'asset_requirement_id':'unknown','status':'attempt_started'}],
                       [{'asset_requirement_id':key,'status':'attempt_started'}]*2,
                       [{'asset_requirement_id':key,'status':'generated'}]):
            with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
                root=Path(folder)
                for e in events: append_event(root/'events.jsonl',e)
                pending_assets([c],root)

    def test_success_records_bytes_and_does_not_repeat_same_root_components(self):
        cases=[runtime_case(),runtime_case('floor-lamp')]
        model=Mock(); model.generate_image.return_value.image=Image.new('RGB',(768,768),'white')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertEqual(generate_assets(cases,root,model,lambda:None)['generated'],2)
            self.assertEqual(model.generate_image.call_count,2)
            self.assertEqual(pending_assets(cases,root),[])
            meta=json.loads((root/(cases[0]['candidate_filename']+'.json')).read_text())
            self.assertEqual(meta['root_sku'],'WANDS-000001')
            self.assertEqual(meta['component_id'],'table-lamps')
            self.assertEqual(meta['visual_acceptance'],'pending')
            self.assertEqual(meta['mask_acceptance'],'pending')
            self.assertFalse(meta['has_alpha'])
            (root/cases[0]['candidate_filename']).write_bytes(b'changed')
            with self.assertRaises(ValueError):pending_assets(cases,root)

    def test_generation_error_stops_at_one_attempt(self):
        model=Mock(); model.generate_image.side_effect=RuntimeError('model failure')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertEqual(generate_assets([runtime_case(),runtime_case('floor-lamp')],root,model,lambda:None)['failed'],1)
            self.assertEqual(model.generate_image.call_count,1)
            with self.assertRaises(ValueError):pending_assets([runtime_case()],root)

    def test_changed_inputs_prevent_any_generation(self):
        model=Mock()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(ValueError):
                generate_assets([runtime_case()],root,model,Mock(side_effect=ValueError('changed input')))
            model.generate_image.assert_not_called()
            self.assertFalse((root/'events.jsonl').exists())

    def test_untracked_candidate_or_symlink_never_overwritten(self):
        c=runtime_case()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); target=root/c['candidate_filename']; target.write_bytes(b'keep')
            with self.assertRaises(ValueError):pending_assets([c],root)
            self.assertEqual(target.read_bytes(),b'keep')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/c['candidate_filename']).symlink_to(root/'missing')
            with self.assertRaises(ValueError):pending_assets([c],root)

    def test_cli_bad_approval_is_quiet_and_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); selected=root/'selection.json'; selected.write_text('[]')
            output=root/'run'
            cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'run_catalog_component_pilot.py'),
                 '--layouts',str(root/'missing'),'--selection',str(selected),'--approved-selection-sha256','a'*64,
                 '--output-dir',str(output),'--run']
            result=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(result.returncode,1)
            self.assertEqual(result.stdout+result.stderr,'')
            self.assertFalse(output.exists())
            self.assertIn('approval fingerprint',output.with_suffix('.log').read_text())


if __name__=='__main__':
    unittest.main()
