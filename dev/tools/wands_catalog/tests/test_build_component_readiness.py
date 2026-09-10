import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_component_readiness import inventory, render
from test_run_catalog_component_pilot import runtime_case


def observation(c,verdict):
    return {'case':c,'verdict':verdict,'image_path':'/tmp/'+verdict+'.webp','image_sha256':verdict,
            'finding':'Visual evidence','review_source':'/tmp/review'}


class ComponentReadinessTest(unittest.TestCase):
    def test_best_visual_candidate_preserves_history_and_does_not_approve_masks(self):
        c=runtime_case(); rows=[observation(c,'fail'),observation(c,'pass'),observation(c,'fail')]
        assets,families,counts=inventory([c['brief']],rows)
        self.assertEqual(assets[0]['status'],'initial_visual_pass')
        self.assertEqual(assets[0]['proposed_candidate']['image_sha256'],'pass')
        self.assertEqual(len(assets[0]['history']),3)
        self.assertEqual(counts['mask_evaluation_candidates'],1)
        self.assertEqual(counts['mask_ready'],0)
        self.assertFalse(assets[0]['mask_execution_approved']); self.assertFalse(families[0]['assembly_ready'])

    def test_unattempted_and_uncertain_components_keep_full_set_blocked(self):
        a=runtime_case(); b=runtime_case('floor-lamp')
        assets,families,counts=inventory([a['brief'],b['brief']],[observation(a,'uncertain')])
        self.assertEqual(counts['unattempted'],1); self.assertEqual(counts['uncertain'],1)
        self.assertEqual(families[0]['missing_visual_pass_types'],2)
        self.assertEqual(counts['required_instances'],4)

    def test_changed_brief_and_unknown_component_fail(self):
        c=runtime_case(); bad=copy.deepcopy(c); bad['brief']['required_instances']=100
        with self.assertRaises(ValueError):inventory([c['brief']],[observation(bad,'pass')])
        with self.assertRaises(ValueError):inventory([c['brief']],[observation(runtime_case('unknown'),'pass')])

    def test_framing_trial_maps_back_to_original_component_not_a_new_product(self):
        c=runtime_case(); r=observation(c,'pass'); r['case']={'source_case':c,'trial_id':'new-canvas'}
        assets,_,counts=inventory([c['brief']],[r])
        self.assertEqual(counts['component_types'],1)
        self.assertEqual(assets[0]['asset_requirement_id'],c['asset_requirement_id'])

    def test_repeated_image_bytes_remain_separate_attempt_evidence(self):
        c=runtime_case(); r=observation(c,'fail')
        _,_,counts=inventory([c['brief']],[r,r])
        self.assertEqual(counts['reviewed_attempts'],2); self.assertEqual(counts['unique_image_hashes'],1)

    def test_review_escapes_content_and_shows_nonpublication_boundary(self):
        c=runtime_case(); r=observation(c,'pass'); r['finding']='<script>bad</script>'
        assets,families,counts=inventory([c['brief']],[r])
        html=render(assets,families,counts)
        self.assertNotIn('<script>',html); self.assertIn('&lt;script&gt;',html)
        self.assertIn('No publication or mask execution is approved',html)


if __name__=='__main__':
    unittest.main()
