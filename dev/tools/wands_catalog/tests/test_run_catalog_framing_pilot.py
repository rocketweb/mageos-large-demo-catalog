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
from run_catalog_framing_pilot import TARGETS, make_cases, generate, pending, validate_directory
from test_run_catalog_component_pilot import runtime_case


def source_rows():
    rows = []
    for key in TARGETS:
        c = runtime_case(); c['asset_requirement_id'] = key
        rows.append({'verdict':'fail', 'case':c, 'image_sha256':'a'*64})
    return rows


class FramingPilotTest(unittest.TestCase):
    def test_only_canvas_shape_changes_within_each_pair(self):
        cases = make_cases(source_rows())
        self.assertEqual(len(cases), 4)
        self.assertEqual(len({c['trial_id'] for c in cases}), 4)
        for a,b in (cases[:2], cases[2:]):
            self.assertEqual(a['source_case'], b['source_case'])
            self.assertEqual(a['settings']['width']*a['settings']['height'], 768**2)
            self.assertEqual(b['settings']['width']*b['settings']['height'], 768**2)
            self.assertEqual({k:v for k,v in a['settings'].items() if k not in ('width','height')},
                             {k:v for k,v in b['settings'].items() if k not in ('width','height')})
            self.assertEqual(b['settings']['height']/b['settings']['width'], 4)

    def test_duplicate_missing_or_nonfailed_sources_rejected(self):
        rows = source_rows()
        for bad in (rows[:1], rows+[rows[0]], [{**rows[0],'verdict':'pass'}, rows[1]]):
            with self.assertRaises(ValueError): make_cases(bad)

    def test_generation_uses_exact_pair_settings_and_resumes_without_retries(self):
        cases = make_cases(source_rows()); model = Mock()
        model.generate_image.side_effect = lambda **kw: Mock(image=Image.new('RGB',(kw['width'],kw['height']),'white'))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(generate(cases,root,model,lambda:None), {'generated':4,'failed':0})
            self.assertEqual(pending(cases,root), [])
            self.assertEqual([c.kwargs['width'] for c in model.generate_image.call_args_list], [768,384,768,384])
            metadata = json.loads((root/(cases[1]['candidate_filename']+'.json')).read_text())
            self.assertFalse(metadata['publication_approved'])
            self.assertEqual(metadata['visual_acceptance'],'pending')
            self.assertFalse(metadata['has_alpha'])
            (root/cases[1]['candidate_filename']).write_bytes(b'changed')
            with self.assertRaises(ValueError): pending(cases,root)

    def test_failure_consumes_attempt_and_stops_remaining_trials(self):
        cases = make_cases(source_rows()); model = Mock()
        model.generate_image.side_effect = RuntimeError('GPU failed')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertEqual(generate(cases,root,model,lambda:None), {'generated':0,'failed':1})
            self.assertEqual(model.generate_image.call_count,1)
            with self.assertRaisesRegex(ValueError,'already attempted'): pending(cases,root)

    def test_changed_inputs_prevent_model_call_or_ledger_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); model=Mock()
            with self.assertRaises(ValueError):
                generate(make_cases(source_rows()),root,model,Mock(side_effect=ValueError('changed input')))
            model.generate_image.assert_not_called()
            self.assertEqual(list(root.iterdir()),[])

    def test_untracked_file_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); cases=make_cases(source_rows())
            (root/'unknown').write_text('keep')
            with self.assertRaises(ValueError): validate_directory(root,cases)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); cases=make_cases(source_rows())
            (root/'events.jsonl').symlink_to(root/'missing')
            with self.assertRaises(ValueError): pending(cases,root)

    def test_duplicate_or_interrupted_ledger_rejected(self):
        cases=make_cases(source_rows()); e={'trial_id':cases[0]['trial_id'],'status':'attempt_started'}
        for events in ([e], [e,e], [{'trial_id':'unknown','status':'attempt_started'}]):
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                (root/'events.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in events))
                with self.assertRaises(ValueError): pending(cases,root)

    def test_bad_approval_is_quiet_without_output_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'run_catalog_framing_pilot.py'),
                 '--source-review',str(root/'missing'),'--approved-source-sha256','bad','--output-dir',str(root/'run')]
            result=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(result.returncode,1)
            self.assertEqual(result.stdout+result.stderr,'')
            self.assertFalse((root/'run').exists())


if __name__ == '__main__':
    unittest.main()
