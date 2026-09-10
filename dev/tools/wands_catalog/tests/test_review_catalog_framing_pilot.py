import copy
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from review_catalog_component_pilot import CHECKS
from review_catalog_framing_pilot import measure_envelope, bind_observations, render
from run_catalog_framing_pilot import make_cases
from test_run_catalog_framing_pilot import source_rows


def fixture(folder):
    cases=make_cases(source_rows()); notes=[]
    for c in cases:
        s=c['settings']; path=folder/c['candidate_filename']
        Image.new('RGB',(s['width'],s['height']),'white').save(path,'WEBP')
        notes.append({'trial_id':c['trial_id'],'image_sha256':sha256(path),'case_sha256':digest(c),
                      'review_method':'direct_image_inspection','review_date':'2026-09-10',
                      'checks':{k:'pass' for k in CHECKS},'estimated_subject_bbox':[10,10,100,500],
                      'finding':'One complete component.','next_direction':'Keep local; assembly untested.'})
    return cases,notes


class FramingReviewTest(unittest.TestCase):
    def test_envelope_is_read_only_diagnostic_not_automatic_acceptance(self):
        im=Image.new('RGB',(200,400),'white'); ImageDraw.Draw(im).rectangle((60,30,139,369),fill='black')
        before=im.tobytes(); result=measure_envelope(im)
        self.assertEqual(im.tobytes(),before)
        self.assertEqual(result['status'],'diagnostic_only')
        self.assertFalse(result['is_mask'])
        for row in result['thresholds']:
            self.assertEqual(row['bbox'],[60,30,140,370])
            self.assertAlmostEqual(row['height_width_ratio'],4.25)

    def test_blank_and_edge_touching_images_are_not_accepted_by_measurement(self):
        self.assertTrue(all(r['bbox'] is None for r in measure_envelope(Image.new('RGB',(200,400),'white'))['thresholds']))
        self.assertTrue(all(r['touches_edge'] for r in measure_envelope(Image.new('RGB',(200,400),'black'))['thresholds']))

    def test_hash_bound_visual_review_keeps_mask_assembly_and_publication_pending(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); cases,notes=fixture(root)
            notes[0].update(publication_approved=True,mask_ready=True,assembly_ready=True)
            rows=bind_observations(cases,notes,root)
            for r in rows:
                self.assertFalse(r['publication_approved']); self.assertFalse(r['mask_ready']); self.assertFalse(r['assembly_ready'])
                self.assertEqual(r['verdict'],'pass')

    def test_stale_missing_duplicate_and_invalid_bounds_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); cases,notes=fixture(root)
            variants=[notes[:-1],notes+[notes[0]]]
            for key,value in [('image_sha256','f'*64),('case_sha256','f'*64),('estimated_subject_bbox',[0,0,800,800]),
                              ('estimated_subject_bbox',[0,0,float('nan'),100])]:
                bad=copy.deepcopy(notes); bad[0][key]=value; variants.append(bad)
            for bad in variants:
                with self.assertRaises(ValueError): bind_observations(cases,bad,root)

    def test_any_failed_check_prevents_visual_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); cases,notes=fixture(root)
            notes[0]['checks']['proportions']='fail'; notes[1]['checks']['identity_and_construction']='uncertain'
            rows=bind_observations(cases,notes,root)
            self.assertEqual([r['verdict'] for r in rows[:2]],['fail','uncertain'])

    def test_render_preserves_canvas_shapes_and_escapes_findings(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); cases,notes=fixture(root); notes[0]['finding']='<script>bad</script>'
            html=render(bind_observations(cases,notes,root))
            self.assertIn('&lt;script&gt;',html); self.assertNotIn('<script>',html)
            self.assertEqual(html.count('<img '),4)
            self.assertIn('object-fit:contain',html)
            self.assertIn('one seed per product',html)
            self.assertIn('No masks or composites',html)


if __name__=='__main__':
    unittest.main()
