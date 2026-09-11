from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_valance_reference import geometry, render


class ValanceReferenceTest(unittest.TestCase):
    def test_four_equal_drops_and_derived_envelope(self):
        result = geometry(133, 71, 30)
        self.assertEqual(result['envelope_cm'], [193, 131])
        parts = result['panels']
        self.assertEqual(parts['deck'], [30, 30, 133, 71])
        self.assertEqual(parts['top'], [30, 0, 133, 30])
        self.assertEqual(parts['bottom'], [30, 101, 133, 30])
        self.assertEqual(parts['left'], [0, 30, 30, 71])
        self.assertEqual(parts['right'], [163, 30, 30, 71])
        self.assertEqual(sum(w*h for x,y,w,h in parts.values()), 133*71+2*30*(133+71))

    def test_invalid_dimensions_rejected(self):
        for values in ((0,71,30), (133,-1,30), (133,71,float('nan')), (True,71,30)):
            with self.assertRaises(ValueError): geometry(*values)

    def test_reference_has_five_panels_and_no_dimension_text(self):
        svg = render(geometry(133, 71, 30))
        self.assertEqual(svg.count('data-panel='), 5)
        self.assertNotIn('<text', svg)
        self.assertIn('viewBox="-16 -16 225 163"', svg)


if __name__ == '__main__': unittest.main()
