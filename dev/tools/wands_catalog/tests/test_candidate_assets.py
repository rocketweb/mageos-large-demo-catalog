import json
import re
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'distribution'))
from build_candidate_assets import build_assets
from release import digest, verify_release, write_archive


class CandidateAssetsTest(unittest.TestCase):
    def profiles(self, root):
        paths, pins = {}, {}
        for profile in ('medium', 'full'):
            path = root / profile
            path.mkdir()
            artifact = write_archive(path / 'catalog.tar', {'data/example.csv': b'sku\nexample\n'})
            (path / 'manifest.json').write_text(json.dumps({'schema': 1, 'profile': profile,
                'release': 'test-enriched-' + profile, 'counts': {'products': 1}, 'artifacts': [artifact]}))
            (path / 'private.env').write_text('NEVER_PACKAGE_THIS')
            paths[profile], pins[profile] = path, digest(path / 'manifest.json')
        return paths, pins

    def test_deterministic_offline_package_preserves_profiles_and_qualifies_docs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, pins = self.profiles(root)
            first = build_assets(paths, pins, root / 'out', tag='catalog-enriched-test')
            second = build_assets(paths, pins, root / 'again', tag='catalog-enriched-test')
            self.assertEqual(first, second)
            self.assertEqual(first['profile_pins'], pins)
            self.assertFalse(first['magento_runtime_verified'])
            self.assertEqual(first['status'], 'local candidate; not published')
            for profile in pins:
                self.assertEqual(digest(root / 'out' / (profile + '-manifest.json')), pins[profile])
                self.assertEqual(digest(root / 'out' / (profile + '-catalog.tar')), digest(paths[profile] / 'catalog.tar'))
            self.assertNotIn('private.env', json.dumps(first))
            toolkit = root / 'toolkit-cache'
            toolkit.mkdir()
            for source, target in [('toolkit-manifest.json', 'manifest.json'), ('toolkit-tools.tar', 'tools.tar')]:
                (toolkit / target).write_bytes((root / 'out' / source).read_bytes())
            verify_release(toolkit, first['toolkit_pin'], root / 'staged')
            instructions = (root / 'staged/README.md').read_text()
            self.assertIn('Packaging does not establish Magento runtime acceptance', instructions)
            self.assertIn('Compare the exact pins', instructions)
            self.assertTrue((root / 'staged/docs/ENRICHED_ACCEPTANCE.md').is_file())
            self.assertIn('5,000', (root / 'staged/docs/BULK_ENRICHMENT.md').read_text())
            self.assertIn('medium', (root / 'staged/tools/github_download.py').read_text())
            self.assertTrue((root / 'staged/docs/WANDS-LICENSE.txt').is_file())
            self.assertTrue((root / 'staged/docs/ROCKET-WEB-LICENSE.txt').is_file())
            self.assertTrue((root / 'staged/docs/CC0-1.0.txt').is_file())
            for document in (root / 'staged').rglob('*.md'):
                for target in re.findall(r'\]\(([^)]+)\)', document.read_text()):
                    if '://' not in target and not target.startswith('#'):
                        self.assertTrue((document.parent / target.split('#')[0]).exists(),
                                        f'Broken packaged link in {document.name}: {target}')
            self.assertNotIn('catalog-2026.09.12-rc2', (root / 'out/README.md').read_text())
            with self.assertRaises(FileExistsError):
                build_assets(paths, pins, root / 'out', tag='catalog-enriched-test')

    def test_invalid_pin_identity_or_tag_fails_before_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, pins = self.profiles(root)
            for tag in ('../bad', 'catalog-2026.09.12-rc2', ''):
                with self.subTest(tag=tag), self.assertRaises(ValueError):
                    build_assets(paths, pins, root / 'out', tag=tag)
            with self.assertRaises(ValueError):
                build_assets(paths, {**pins, 'medium': '0' * 64}, root / 'out', tag='enriched-v1')
            with self.assertRaises(ValueError):
                build_assets({'medium': paths['full'], 'full': paths['full']},
                             {'medium': pins['full'], 'full': pins['full']}, root / 'out', tag='enriched-v1')
            self.assertFalse((root / 'out').exists())


if __name__ == '__main__':
    unittest.main()
