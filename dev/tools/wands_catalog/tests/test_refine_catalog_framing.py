import copy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from refine_catalog_framing import choose_canvas, refine_cases, render
from run_catalog_framing_pilot import make_cases
from test_run_catalog_framing_pilot import source_rows


def reviewed():
    rows=[]
    for c in make_cases(source_rows()):
        rows.append({'case':c,'verdict':'fail','checks':{'proportions':'fail','identity_and_construction':'pass'},
                     'target_ratio':5.5 if 'floor-lamp' in c['trial_id'] else 25/6,
                     'estimated_ratio':1355/314 if 'floor-lamp' in c['trial_id'] else 1359/259,
                     'image_sha256':'a'*64,'image_path':'/tmp/prior.webp'})
    return rows


class FramingRefinementTest(unittest.TestCase):
    def test_canvas_is_deterministic_bounded_and_nearly_equal_area(self):
        for aspect in (5.098,3.177):
            w,h=choose_canvas(aspect)
            self.assertEqual((w,h),choose_canvas(aspect))
            self.assertEqual(w%16,0); self.assertEqual(h%16,0)
            self.assertLessEqual(abs(w*h/(768**2)-1),.01)
            self.assertGreaterEqual(w,256); self.assertLessEqual(h,2048)
            self.assertLess(abs(math.log(h/w/aspect)),.04)

    def test_invalid_or_unreachable_aspect_fails(self):
        for aspect in (0,-1,True,float('nan'),float('inf'),100):
            with self.assertRaises(ValueError):choose_canvas(aspect)

    def test_refinement_is_exactly_two_trials_with_unchanged_prompt_seed_and_no_approvals(self):
        rows=reviewed(); cases=refine_cases(rows)
        self.assertEqual(len(cases),2)
        for c in cases:
            before=next(r['case'] for r in rows if r['case']['asset_requirement_id']==c['asset_requirement_id'])
            self.assertEqual(c['source_case'],before['source_case'])
            self.assertEqual(c['max_attempts'],1)
            self.assertFalse(c['publication_approved'])
            self.assertEqual(c['reference_inputs'],[])
            self.assertEqual(c['calibration']['status'],'hypothesis_not_acceptance')

    def test_unknown_missing_duplicate_or_other_visual_failure_blocks_refinement(self):
        rows=reviewed()
        for bad in (rows[:-1],rows+[rows[0]]):
            with self.assertRaises(ValueError):refine_cases(bad)
        bad=copy.deepcopy(rows); bad[1]['checks']['identity_and_construction']='fail'
        with self.assertRaises(ValueError):refine_cases(bad)

    def test_review_escapes_text_and_does_not_claim_equal_pixels_or_automatic_approval(self):
        prior=reviewed(); c=refine_cases(prior)[0]
        row={'case':c,'image_path':'/tmp/new.webp','verdict':'uncertain','finding':'<script>bad</script>',
             'target_ratio':5.5,'estimated_ratio':5.1,'next_direction':'Hold','relative_ratio_error':5.1/5.5-1,
             'image_sha256':'a'*64}
        html=render([row],prior)
        self.assertIn('&lt;script&gt;',html); self.assertNotIn('<script>',html)
        self.assertIn('within 1%',html); self.assertIn('not a new acceptance threshold',html)
        self.assertEqual(html.count('<img '),2)


if __name__=='__main__':
    unittest.main()
