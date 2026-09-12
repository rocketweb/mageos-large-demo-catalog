from pathlib import Path
import sys
import unittest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repair_cutout_handle import repair_handle


class HandleRepairTest(unittest.TestCase):
    def test_only_reviewed_handle_alpha_changes(self):
        image = Image.new('RGBA', (24, 44), (19, 77, 149, 0))
        for y in range(2, 42):
            for x in range(5, 19):
                image.putpixel((x, y), (19, 77, 149, 220))
        image.putpixel((12, 8), (19, 77, 149, 0))  # Real slot in head.
        image.putpixel((12, 28), (19, 77, 149, 0))  # False handle hole.
        original = image.tobytes()
        repaired, changed = repair_handle(image, [0, 20, 24, 44], True)
        self.assertGreater(changed, 0)
        self.assertEqual(repaired.getpixel((12, 28))[3], 255)
        self.assertEqual(repaired.getpixel((12, 8))[3], 0)
        self.assertEqual(repaired.crop((0, 0, 24, 20)).tobytes(), image.crop((0, 0, 24, 20)).tobytes())
        self.assertEqual(repaired.getpixel((0, 30))[3], 0)
        self.assertEqual(repaired.getpixel((5, 30))[3], 220)
        self.assertEqual(repaired.convert('RGB').tobytes(), image.convert('RGB').tobytes())
        self.assertEqual(image.tobytes(), original)

    def test_unconfirmed_or_invalid_region_is_rejected(self):
        image = Image.new('RGBA', (24, 44))
        for box, confirmed in [([0, 20, 24, 44], False), ([-1, 0, 24, 44], True),
                               ([0, 0, 25, 44], True), ([4, 3, 2, 10], True)]:
            with self.assertRaises(ValueError):
                repair_handle(image, box, confirmed)


if __name__ == '__main__':
    unittest.main()
