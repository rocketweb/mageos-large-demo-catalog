from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_catalog import sha256
from validate_component_cutout import inspect_cutout


class CutoutTest(unittest.TestCase):
    def fixture(self, root):
        source = root / 'source.webp'; cutout = root / 'cutout.png'
        Image.new('RGB', (32, 32), (100, 120, 140)).save(source, 'WEBP')
        with Image.open(source) as image: rgba = image.convert('RGBA')
        alpha = Image.new('L', (32, 32), 0)
        alpha.paste(255, (8, 8, 24, 24)); rgba.putalpha(alpha); rgba.save(cutout)
        return source, cutout

    def test_contract_pass_never_approves_visual_mask_or_assembly(self):
        with tempfile.TemporaryDirectory() as folder:
            source, cutout = self.fixture(Path(folder)); before = [sha256(source), sha256(cutout)]
            result = inspect_cutout(source, before[0], cutout)
            self.assertEqual(result['contract_status'], 'pass')
            self.assertFalse(result['mask_ready']); self.assertFalse(result['assembly_ready'])
            self.assertFalse(result['publication_approved'])
            self.assertEqual(before, [sha256(source), sha256(cutout)])

    def test_opaque_empty_altered_and_edge_touching_candidates_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for variant in ('opaque', 'empty', 'altered', 'edge'):
                source, cutout = self.fixture(root)
                with Image.open(cutout) as im: image = im.copy()
                if variant == 'opaque': image.putalpha(255)
                if variant == 'empty': image.putalpha(0)
                if variant == 'altered': image.putpixel((12, 12), (255, 0, 0, 255))
                if variant == 'edge':
                    with Image.open(source) as im: image.putpixel((0, 0), (*im.getpixel((0, 0)), 255))
                image.save(cutout)
                self.assertEqual(inspect_cutout(source, sha256(source), cutout)['contract_status'], 'fail', variant)

    def test_stale_source_and_wrong_canvas_or_format_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source, cutout = self.fixture(Path(folder))
            with self.assertRaises(ValueError): inspect_cutout(source, '0' * 64, cutout)
            Image.new('RGBA', (16, 16)).save(cutout)
            self.assertEqual(inspect_cutout(source, sha256(source), cutout)['contract_status'], 'fail')

    def test_cli_is_quiet_and_refuses_logging_into_source_image(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source, cutout = self.fixture(root); source_hash = sha256(source)
            cmd = [sys.executable, str(Path(__file__).resolve().parents[1] / 'validate_component_cutout.py'),
                   '--source', str(source), '--source-sha256', source_hash, '--cutout', str(cutout), '--log-file']
            good = subprocess.run(cmd + [str(root / 'check.log')], capture_output=True, text=True)
            self.assertEqual(good.returncode, 0); self.assertEqual(good.stdout + good.stderr, '')
            bad = subprocess.run(cmd + [str(source)], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1); self.assertEqual(bad.stdout + bad.stderr, '')
            self.assertEqual(sha256(source), source_hash)
            Image.new('RGB', (32, 32)).save(cutout)
            self.assertEqual(inspect_cutout(source, sha256(source), cutout)['contract_status'], 'fail')


if __name__ == '__main__': unittest.main()
