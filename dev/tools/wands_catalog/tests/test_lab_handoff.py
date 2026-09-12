import hashlib
import json
import os
from pathlib import Path
import subprocess
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'distribution'))
from build_handoff import build_handoff
from release import digest, write_archive, verify_release


class HandoffTest(unittest.TestCase):
    def profiles(self, root):
        paths, pins = {}, {}
        for profile in ['starter', 'full']:
            path = root / profile
            path.mkdir()
            artifact = write_archive(path / 'catalog.tar', {'data/item.csv': b'sku\nexample\n'})
            data = json.dumps({'schema': 1, 'profile': profile, 'release': '2026.09.11-rc2',
                               'counts': {'products': 1}, 'artifacts': [artifact]}).encode()
            (path / 'manifest.json').write_bytes(data)
            (path / 'private.env').write_text('DO_NOT_PACKAGE_THIS')
            paths[profile], pins[profile] = path, hashlib.sha256(data).hexdigest()
        return paths, pins

    def test_reproducible_self_contained_handoff_and_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, pins = self.profiles(root)
            with patch('build_handoff.PROFILE_PINS', pins):
                first = build_handoff(paths, root / 'one')
                second = build_handoff(paths, root / 'two')
            self.assertEqual(first, second)
            self.assertEqual(digest(root / 'one/handoff.tar'), digest(root / 'two/handoff.tar'))
            extracted = root / 'recipient'
            verify_release(root / 'one', first['manifest_sha256'], extracted)
            self.assertFalse(list(extracted.rglob('private.env')))
            self.assertNotIn(b'DO_NOT_PACKAGE_THIS', (root / 'one/handoff.tar').read_bytes())
            for profile, pin in pins.items():
                result = subprocess.run([sys.executable, str(extracted / 'tools/release.py'),
                    str(extracted / 'profiles' / profile), '--manifest-sha256', pin,
                    '--extract', str(root / (profile + '-staging'))], cwd=root, capture_output=True)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout + result.stderr, b'')
                self.assertEqual((root / (profile + '-staging/data/item.csv')).read_bytes(), b'sku\nexample\n')
            help_result = subprocess.run([sys.executable, str(extracted / 'tools/download.py'), '--help'],
                                         cwd=root, capture_output=True)
            self.assertEqual(help_result.returncode, 0)
            self.assertIn(b'--base-url', help_result.stdout)
            inventory = json.loads((root / 'one/manifest.json').read_text())['artifacts'][0]['files']
            self.assertIn('docs/CITATION.bib', inventory)
            self.assertIn('docs/CC0-1.0.txt', inventory)
            self.assertNotIn('acceptance/compose.yaml', inventory)
            for path in extracted.rglob('*.md'):
                self.assertNotIn('dev/tools/wands_catalog/', path.read_text())

    def test_corrupt_profile_refused_before_output_created(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, pins = self.profiles(root)
            (paths['full'] / 'catalog.tar').write_bytes(b'broken')
            with patch('build_handoff.PROFILE_PINS', pins), self.assertRaises(ValueError):
                build_handoff(paths, root / 'output')
            self.assertFalse((root / 'output').exists())

    def test_wrong_profile_and_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, pins = self.profiles(root)
            with patch('build_handoff.PROFILE_PINS', pins):
                with self.assertRaises(FileExistsError):
                    build_handoff(paths, root)
                with self.assertRaises(ValueError):
                    build_handoff({'starter': paths['full'], 'full': paths['starter']}, root / 'output')

    def test_documented_bootstrap_rejects_tampering_even_with_python_optimization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, pins = self.profiles(root)
            output = root / 'output'
            with patch('build_handoff.PROFILE_PINS', pins):
                result = build_handoff(paths, output)
            command = next(line for line in (output / 'START_HERE.md').read_text().splitlines()
                           if line.startswith('python3 -c '))
            args = shlex.split(command)
            args[0] = sys.executable
            for pin, tamper in [('0' * 64, False), (result['manifest_sha256'], False),
                                (result['manifest_sha256'], True)]:
                if tamper:
                    (output / 'release.py').write_text('print("do not execute")')
                args[-1] = pin
                check = subprocess.run(args, cwd=output, env={**os.environ, 'PYTHONOPTIMIZE': '1'},
                                       capture_output=True)
                with self.subTest(pin=pin, tamper=tamper):
                    self.assertEqual(check.returncode == 0, pin == result['manifest_sha256'] and not tamper)


if __name__ == '__main__':
    unittest.main()
