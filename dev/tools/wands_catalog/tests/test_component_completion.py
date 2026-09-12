import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from component_completion import plan_cases, finalize_cases, render
from test_run_catalog_component_pilot import brief, runtime_case


def choice():
    return {'asset_requirement_id':brief()['asset_requirement_id'],'batch':'lamps','canvas':[832,704],
            'visual_instruction':'One complete lamp.','preserve_previous_prompt':False}


class CompletionTest(unittest.TestCase):
    def test_planning_preserves_brief_and_separates_batch_and_attempt_identity(self):
        cases=plan_cases([brief()],[choice()],{brief()['asset_requirement_id']:'uncertain'}, {})
        self.assertEqual(len(cases),1); self.assertEqual(cases[0]['source_case']['brief'],brief())
        final=finalize_cases(cases,[180])
        self.assertIn('completion',final[0]['trial_id'])
        self.assertEqual(final[0]['source_case']['token_count'],180)
        self.assertEqual(final[0]['settings']['width'],832)
        self.assertFalse(final[0]['publication_approved']); self.assertEqual(final[0]['reference_inputs'],[])

    def test_passed_unknown_duplicate_and_overlimit_selections_rejected(self):
        c=choice(); key=brief()['asset_requirement_id']
        for choices,status in (([c],'initial_visual_pass'),([c,c],'uncertain'),([c]*26,'uncertain')):
            with self.assertRaises(ValueError):plan_cases([brief()],choices,{key:status},{})
        c['asset_requirement_id']='unknown'
        with self.assertRaises(ValueError):plan_cases([brief()],[c],{key:'uncertain'},{})

    def test_bad_canvas_and_token_counts_rejected(self):
        for size in ([1,2],[768,3000],[True,768],[512,512]):
            c=choice();c['canvas']=size
            with self.assertRaises(ValueError):plan_cases([brief()],[c],{brief()['asset_requirement_id']:'uncertain'},{})
        raw=plan_cases([brief()],[choice()],{brief()['asset_requirement_id']:'uncertain'},{})
        for counts in ([0],[513],[True],[]):
            with self.assertRaises(ValueError):finalize_cases(raw,counts)

    def test_table_lamp_can_retain_exact_prior_prompt_and_seed(self):
        c=choice(); c['preserve_previous_prompt']=True; previous=runtime_case(); key=brief()['asset_requirement_id']
        cases=plan_cases([brief()],[c],{key:'uncertain'},{key:previous})
        self.assertEqual(cases[0]['source_case'],previous)
        bad=copy.deepcopy(previous);bad['brief']['required_instances']=99
        with self.assertRaises(ValueError):plan_cases([brief()],[c],{key:'uncertain'},{key:bad})

    def test_render_escapes_text_and_does_not_approve_assembly(self):
        c=finalize_cases(plan_cases([brief()],[choice()],{brief()['asset_requirement_id']:'uncertain'},{}),[180])[0]
        row={'case':c,'verdict':'fail','image_path':'/tmp/image.webp','finding':'<script>bad</script>',
             'next_direction':'Hold','target_ratio':1.73,'estimated_ratio':3,'image_sha256':'abc'}
        html=render([row]);self.assertIn('&lt;script&gt;',html);self.assertNotIn('<script>',html)
        self.assertIn('not assembly acceptance',html)

    def test_bad_input_is_quiet_and_creates_no_run(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'component_completion.py')]
            for flag in ('layouts','readiness','selection'):cmd+=['--'+flag,str(root/'missing')]
            cmd+=['--selection-sha256','bad','--batch','lamps','--output-dir',str(root/'run')]
            p=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(p.returncode,1);self.assertEqual(p.stdout+p.stderr,'');self.assertFalse((root/'run').exists())


if __name__=='__main__':unittest.main()
