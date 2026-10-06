from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from image_review import review_brief


class ReviewBriefTest(unittest.TestCase):
    def test_source_dimensions_cannot_bias_pixel_review(self):
        brief=review_brief({'subject':'Hand-Knotted Area Rug - Black, 5 ft x 7 ft',
                            'profile':'Area Rugs','lane':'existing-family-children',
                            'color':'Black','options':{'color':'Black','wands_size':'5 ft x 7 ft'}},True)
        self.assertNotIn('ft',str(brief))
        self.assertNotIn('wands_size',str(brief))
        self.assertEqual(brief['requested_change'],{'color_or_finish':'Black'})
        self.assertEqual(brief['intended_product']['product_class'],'Area Rugs')

    def test_structural_counts_and_single_sale_unit_survive(self):
        brief=review_brief({'subject':'4 Door Cabinet','product_class':'Accent Cabinets',
                           'construction':'four front doors','color':'Cream'},False)
        self.assertIn('4 Door',brief['intended_product']['subject'])
        self.assertNotIn('requested_change',brief)


if __name__=='__main__':unittest.main()
