import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from review_builtin_components import convert_native, verdict, validate_records, restore_history
from reconcile_catalog_media import digest


class BuiltinReviewTest(unittest.TestCase):
    def test_baseline_history_restores_all_packets_not_only_latest_repairs(self):
        old = {'case': {'id': 'old'}, 'image_sha256': 'a', 'finding': 'Old pass', 'verdict': 'pass'}
        new = {'case': {'id': 'new'}, 'image_sha256': 'b', 'finding': 'New fail', 'verdict': 'fail'}
        history = [{**r, 'execution_case_sha256': digest(r['case']), 'review_source': source}
                   for source, r in [('old-packet', old), ('repair-packet', new)]]
        actual = restore_history([{'history': history}], {'old-packet': [old], 'repair-packet': [new]})
        self.assertEqual([r['finding'] for r in actual], ['Old pass', 'New fail'])
        self.assertEqual(actual[0]['review_source'], 'old-packet')
        with self.assertRaises(ValueError):
            restore_history([{'history': history}], {'old-packet': [], 'repair-packet': [new]})

    def test_lossless_conversion_preserves_native_rgb_and_canvas(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, target = root / 'source.png', root / 'target.webp'
            image = Image.new('RGB', (21, 34), (13, 127, 239))
            image.putpixel((9, 11), (253, 17, 89))
            image.save(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            convert_native(source, digest, target)
            with Image.open(target) as actual:
                self.assertEqual(actual.size, image.size)
                self.assertEqual(actual.tobytes(), image.tobytes())
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)
            with self.assertRaises(ValueError):
                convert_native(source, '0' * 64, root / 'wrong.webp')
            with self.assertRaises(ValueError):
                convert_native(source, digest, target)

    def test_alpha_is_never_silently_discarded(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'rgba.png'
            Image.new('RGBA', (20, 20), (4, 6, 8, 0)).save(source)
            with self.assertRaises(ValueError):
                convert_native(source, hashlib.sha256(source.read_bytes()).hexdigest(), source.with_suffix('.webp'))

    def test_visual_uncertainty_cannot_be_promoted(self):
        checks = dict.fromkeys(('appearance_and_view', 'identity_and_construction', 'no_text_or_extras',
                                'proportions', 'single_complete_component', 'synthetic_provenance'), 'pass')
        self.assertEqual(verdict(checks), 'pass')
        checks['proportions'] = 'uncertain'
        self.assertEqual(verdict(checks), 'uncertain')
        checks['identity_and_construction'] = 'fail'
        self.assertEqual(verdict(checks), 'fail')
        with self.assertRaises(ValueError):
            verdict({'identity_and_construction': 'pass'})

    def test_duplicate_attempts_and_invented_runtime_are_rejected(self):
        row = {'asset_requirement_id': 'A', 'attempt': 1, 'generator': 'built-in image_gen',
               'prompt': 'One object', 'finding': 'Inspected', 'review_method': 'direct_image_inspection',
               'seed': None, 'model_version': None}
        validate_records([row], {'A'})
        with self.assertRaises(ValueError):
            validate_records([row, row], {'A'})
        with self.assertRaises(ValueError):
            validate_records([{**row, 'seed': 42}], {'A'})
        with self.assertRaises(ValueError):
            validate_records([row], {'B'})


if __name__ == '__main__':
    unittest.main()
