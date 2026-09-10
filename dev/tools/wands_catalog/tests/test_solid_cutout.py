import sys
from pathlib import Path
import unittest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from repair_solid_cutout import fill_solid_interior


class SolidCutoutTest(unittest.TestCase):
    def test_fills_only_enclosed_alpha_holes_preserving_rgb_and_outer_edge(self):
        image=Image.new('RGBA',(20,20),(120,130,140,0));a=Image.new('L',(20,20),0)
        a.paste(128,(3,3,17,17));a.paste(255,(4,4,16,16));a.paste(0,(7,7,13,13));image.putalpha(a)
        fixed,count=fill_solid_interior(image,True)
        self.assertEqual(count,36);self.assertEqual(fixed.convert('RGB').tobytes(),image.convert('RGB').tobytes())
        self.assertEqual(fixed.getpixel((3,3))[3],128);self.assertEqual(fixed.getpixel((0,0))[3],0)
        self.assertEqual(fixed.getpixel((9,9))[3],255)
        with self.assertRaises(ValueError):fill_solid_interior(image,False)

    def test_open_gap_remains_open(self):
        image=Image.new('RGBA',(20,20),(100,100,100,255));a=Image.new('L',(20,20),255)
        a.paste(0,(8,0,12,14));image.putalpha(a)
        fixed,count=fill_solid_interior(image,True)
        self.assertEqual(count,0);self.assertEqual(fixed.tobytes(),image.tobytes())

    def test_soft_foreground_barrier_still_encloses_a_false_hole(self):
        image=Image.new('RGBA',(20,20),(100,110,120,0));a=Image.new('L',(20,20),0)
        a.paste(220,(4,4,16,16));a.paste(0,(7,7,13,13));image.putalpha(a)
        fixed,count=fill_solid_interior(image,True)
        self.assertEqual(count,36);self.assertEqual(fixed.getpixel((9,9))[3],255)
        self.assertEqual(fixed.getpixel((4,4))[3],220)


if __name__=='__main__':unittest.main()
