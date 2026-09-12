from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from export_storefront_media import verify_master, derivatives


class ExportTest(unittest.TestCase):
    def test_blank_or_wrong_canvas_rejected(self):
        with self.assertRaises(ValueError):verify_master(Image.new('RGB',(2000,2000),'white'))
        with self.assertRaises(ValueError):verify_master(Image.new('RGB',(20,20),'blue'))

    def test_formats_sizes_and_content_addressed_names(self):
        im=Image.new('RGB',(2000,2000),'white');ImageDraw.Draw(im).rectangle((300,300,1600,1600),fill='blue')
        verify_master(im)
        with tempfile.TemporaryDirectory() as d:
            rows=derivatives(im,'WANDS-000001',Path(d))
            self.assertEqual(len(rows),4)
            self.assertEqual([r['size'] for r in rows],[[2000,2000],[2000,2000],[1200,1200],[400,400]])
            for r in rows:
                self.assertIn(r['sha256'][:12],r['file'])
                with Image.open(Path(d)/r['file']) as actual:self.assertEqual(list(actual.size),r['size'])


if __name__=='__main__':unittest.main()
