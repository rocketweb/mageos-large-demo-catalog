import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_catalog import sha256
from review_catalog_component_pilot import CHECKS, bind_observations, render
from test_run_catalog_component_pilot import runtime_case


def note(c,path):
    return {'asset_requirement_id':c['asset_requirement_id'],'image_sha256':sha256(path),
            'brief_sha256':c['brief_sha256'],'runtime_prompt_sha256':c['runtime_prompt_sha256'],
            'review_method':'direct_image_inspection','review_date':'2026-09-10',
            'checks':{k:'pass' for k in CHECKS},'estimated_subject_bbox':[100,100,400,620],
            'bbox_note':'Approximate visual bounds, not a mask.','finding':'One plausible object.',
            'next_direction':'Keep local; mask and assembly are pending.'}


class ComponentReviewTest(unittest.TestCase):
    def test_visual_verdict_cannot_grant_mask_or_assembly_approval(self):
        c=runtime_case()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); path=root/c['candidate_filename']; path.write_bytes(b'candidate')
            n=note(c,path); n.update(mask_ready=True,assembly_ready=True,publication_approved=True,reference_use_approved=True,verdict='fail')
            row=bind_observations([c],[n],root)[0]
            self.assertEqual(row['verdict'],'pass')
            for key in ('mask_ready','assembly_ready','publication_approved','reference_use_approved'):
                self.assertIs(row[key],False)
            self.assertAlmostEqual(row['diagnostic_ratio']['estimated_image'],520/300)

    def test_fail_and_uncertain_checks_override_a_declared_pass(self):
        c=runtime_case()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); path=root/c['candidate_filename']; path.write_bytes(b'candidate')
            for status in ('fail','uncertain'):
                n=note(c,path); n['verdict']='pass'; n['checks']['proportions']=status
                self.assertEqual(bind_observations([c],[n],root)[0]['verdict'],status)

    def test_stale_binding_duplicate_and_missing_observations_rejected(self):
        c=runtime_case()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); path=root/c['candidate_filename']; path.write_bytes(b'candidate')
            n=note(c,path)
            for key in ('image_sha256','brief_sha256','runtime_prompt_sha256'):
                bad=copy.deepcopy(n); bad[key]='f'*64
                with self.assertRaisesRegex(ValueError,'Stale'):bind_observations([c],[bad],root)
            for observations in ([],[n,n]):
                with self.assertRaises(ValueError):bind_observations([c],observations,root)

    def test_incomplete_checks_and_invalid_pixel_bounds_cannot_pass(self):
        c=runtime_case()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); path=root/c['candidate_filename']; path.write_bytes(b'candidate')
            for box in ([0,0,900,100],[10,10,10,100],[True,0,30,40],[0,float('nan'),30,40]):
                bad=note(c,path); bad['estimated_subject_bbox']=box
                with self.assertRaises(ValueError):bind_observations([c],[bad],root)
            bad=note(c,path); bad['checks']['proportions']='pending'
            with self.assertRaises(ValueError):bind_observations([c],[bad],root)

    def test_html_escapes_evidence_and_keeps_composition_limits_visible(self):
        c=runtime_case()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); path=root/c['candidate_filename']; path.write_bytes(b'candidate')
            n=note(c,path); n['finding']='<script>unsafe</script>'
            row=bind_observations([c],[n],root)[0]; row['earlier_image']='/tmp/earlier.webp'
            html=render([row],{'reviewed':1,'pass':1,'uncertain':0,'fail':0,'assembly_ready':0})
            self.assertIn('&lt;script&gt;',html); self.assertNotIn('<script>',html)
            self.assertEqual(html.count('<img '),2)
            self.assertIn('not an equal-condition model benchmark',html)
            self.assertIn('No transparent mask or composite has been produced',html)

    def test_cli_error_is_quiet_and_creates_no_packet(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); output=root/'review'
            cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'review_catalog_component_pilot.py')]
            for flag in ('layouts','selection','run-dir','observations'):
                cmd+=['--'+flag,str(root/'missing')]
            cmd+=['--output-dir',str(output)]
            result=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(result.returncode,1); self.assertEqual(result.stdout+result.stderr,'')
            self.assertFalse(output.exists())
            self.assertIn('no images, masks or approvals changed',output.with_suffix('.log').read_text())


if __name__=='__main__':
    unittest.main()
