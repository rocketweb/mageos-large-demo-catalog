from pathlib import Path
import sys
import unittest
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_component_cutouts import attach_alpha


class LocalCutoutTest(unittest.TestCase):
    def test_mask_changes_only_alpha(self):
        image=Image.new('RGB',(24,24),(120,130,140));mask=Image.new('L',(24,24),0)
        mask.paste(255,(5,5,19,19));before=image.tobytes()
        cutout=attach_alpha(image,mask)
        self.assertEqual(cutout.convert('RGB').tobytes(),before)
        self.assertEqual(image.tobytes(),before)
        self.assertEqual(cutout.getchannel('A').tobytes(),mask.tobytes())
        with self.assertRaises(ValueError):attach_alpha(image,Image.new('L',(12,12)))


if __name__=='__main__':unittest.main()
