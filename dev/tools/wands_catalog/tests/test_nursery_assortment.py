import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_nursery_assortment import plan


class NurseryAssortmentTest(unittest.TestCase):
    def setUp(self):
        self.parts = {
            'quilt': {'component_id':'quilt', 'quantity':1, 'dimensions_cm':{'lab_spec_width_cm':85,'lab_spec_length_cm':110}},
            'sheets': {'component_id':'sheets', 'quantity':1, 'dimensions_cm':{'lab_spec_width_cm':71,'lab_spec_length_cm':133,'lab_spec_height_cm':15}},
            'skirt': {'component_id':'skirt', 'quantity':1, 'dimensions_cm':{'lab_spec_width_cm':71,'lab_spec_length_cm':133,'lab_spec_height_cm':30}}}
        self.bounds = {'quilt':[0,0,850,1100], 'sheets':[0,0,710,1330], 'skirt':[0,0,1930,1310]}

    def test_unfolded_envelope_uses_same_scale_not_old_platform_slot(self):
        rows = plan(self.parts, self.bounds)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2]['presentation_envelope_cm'], [193,131])
        self.assertEqual(rows[2]['width'], 579)
        self.assertEqual(rows[2]['height'], 393)
        self.assertTrue(all(r['uniform_scale']==.3 for r in rows))
        self.assertEqual(rows[2]['instance_id'], 'skirt-01')

    def test_incomplete_or_extra_assortment_rejected(self):
        for name in self.bounds:
            incomplete = dict(self.bounds); del incomplete[name]
            with self.assertRaises(ValueError): plan(self.parts, incomplete)
        with self.assertRaises(ValueError): plan({**self.parts,'pillow':{}},self.bounds)
        parts = copy.deepcopy(self.parts); parts['sheets']['quantity']=2
        with self.assertRaises(ValueError): plan(parts,self.bounds)

    def test_uniform_fit_preserves_candidate_ratio(self):
        self.bounds['skirt']=[10,10,1910,1310]
        rows=plan(self.parts,self.bounds)
        self.assertAlmostEqual(rows[2]['width']/rows[2]['height'],1900/1300)
        self.assertLessEqual(rows[2]['width'],579+1e-9)
        self.assertLessEqual(rows[2]['height'],393+1e-9)

    def test_layout_rejects_outside_canvas_or_overlapping_slots(self):
        parts=copy.deepcopy(self.parts)
        parts['quilt']['dimensions_cm']['lab_spec_width_cm']=500
        with self.assertRaises(ValueError): plan(parts,self.bounds)
        parts=copy.deepcopy(self.parts)
        parts['quilt']['dimensions_cm']['lab_spec_length_cm']=180
        with self.assertRaises(ValueError): plan(parts,self.bounds)


if __name__ == '__main__': unittest.main()
