import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'distribution'))
from build_github_assets import build_assets
from release import write_archive, digest, verify_release


class GitHubAssetsTest(unittest.TestCase):
    def test_preserves_profile_pins_and_exports_only_release_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, pins = {}, {}
            for profile in ['starter', 'full']:
                path = root / profile
                path.mkdir()
                artifact = write_archive(path / 'catalog.tar', {'data/example.csv': b'sku\nexample\n'})
                (path / 'manifest.json').write_text(json.dumps({'schema': 1, 'profile': profile,
                    'release': '2026.09.11-rc2', 'counts': {'products': 1}, 'artifacts': [artifact]}))
                (path / 'private.env').write_text('NOT_FOR_RELEASE')
                paths[profile], pins[profile] = path, digest(path / 'manifest.json')
            with patch('build_github_assets.PROFILE_PINS', pins):
                first = build_assets(paths, root / 'out')
                second = build_assets(paths, root / 'again')
            self.assertEqual(first, second)
            for profile in pins:
                self.assertEqual(digest(root / 'out' / (profile + '-manifest.json')), pins[profile])
                self.assertEqual(digest(root / 'out' / (profile + '-catalog.tar')), digest(paths[profile] / 'catalog.tar'))
            self.assertNotIn('private.env', json.dumps(first))
            self.assertTrue(all(row['bytes'] < 2 ** 31 for row in first['assets'].values()))
            self.assertEqual(set(p.name for p in (root / 'out').iterdir()),
                             set(first['assets']) | {'release-inventory.json', 'SHA256SUMS'})
            toolkit = root / 'toolkit-cache'
            toolkit.mkdir()
            (toolkit / 'manifest.json').write_bytes((root / 'out/toolkit-manifest.json').read_bytes())
            (toolkit / 'tools.tar').write_bytes((root / 'out/toolkit-tools.tar').read_bytes())
            verified = verify_release(toolkit, first['toolkit_pin'], root / 'toolkit-staged')
            self.assertGreater(verified['files'], 0)
            self.assertTrue((root / 'toolkit-staged/tools/github_download.py').is_file())
            self.assertTrue((root / 'toolkit-staged/docs/WANDS-LICENSE.txt').is_file())
            with self.assertRaises(FileExistsError):
                build_assets(paths, root / 'out')


if __name__ == '__main__':
    unittest.main()
