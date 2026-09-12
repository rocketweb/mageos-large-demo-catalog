from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_assortment_preview import fit


class AssortmentPreviewTest(unittest.TestCase):
    def test_fit_is_uniform_contained_and_baseline_aligned(self):
        b={'x':10,'y':20,'width':100,'height':200}
        x,y,w,h,s=fit([20,30,70,130],b,True)
        self.assertEqual((x,y,w,h,s),(10,20,100,200,2))
        x,y,w,h,s=fit([0,0,200,100],b,True)
        self.assertEqual((x,y,w,h,s),(10,170,100,50,.5))
        self.assertEqual(w/200,h/100)
        with self.assertRaises(ValueError):fit([0,0,0,100],b,True)


if __name__=='__main__':unittest.main()
