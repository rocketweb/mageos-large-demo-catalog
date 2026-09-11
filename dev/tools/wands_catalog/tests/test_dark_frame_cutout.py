from pathlib import Path
import sys
import unittest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repair_dark_frame_cutout import recover_frame


class DarkFrameTest(unittest.TestCase):
    def test_missing_dark_frame_is_restored_without_repainting(self):
        source = Image.new('RGB', (60, 50), 'white')
        d = ImageDraw.Draw(source)
        d.rectangle((10, 10, 49, 39), fill=(60, 65, 70))
        d.rectangle((16, 16, 43, 33), fill=(190, 190, 190))
        alpha = Image.new('L', source.size, 0)
        ImageDraw.Draw(alpha).rectangle((16, 16, 43, 33), fill=255)
        old = source.copy(); old.putalpha(alpha)
        result, count = recover_frame(source, old, True)
        self.assertGreater(count, 0)
        self.assertEqual(result.getpixel((12, 12))[3], 255)
        self.assertEqual(result.getpixel((20, 20))[3], 255)
        self.assertEqual(result.getpixel((2, 2))[3], 0)
        self.assertEqual(result.convert('RGB').tobytes(), source.tobytes())
        self.assertEqual(old.getpixel((12, 12))[3], 0)

    def test_scope_confirmation_and_white_backdrop_required(self):
        source = Image.new('RGB', (60, 50), 'black')
        mask = source.convert('RGBA')
        with self.assertRaises(ValueError): recover_frame(source, mask, True)
        source = Image.new('RGB', (60, 50), 'white')
        with self.assertRaises(ValueError): recover_frame(source, source.convert('RGBA'), False)
        with self.assertRaises(ValueError): recover_frame(source, mask, True)


if __name__ == '__main__': unittest.main()
