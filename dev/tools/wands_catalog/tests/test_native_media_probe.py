import json
from pathlib import Path
import subprocess
import tempfile
import unittest

PHP = Path('/opt/homebrew/Cellar/php@8.4/8.4.24/bin/php')
PROBE = Path(__file__).resolve().parents[1] / 'probe_native_media_import.php'


@unittest.skipUnless(PHP.is_file(), 'Local PHP unavailable')
class NativeMediaProbeTest(unittest.TestCase):
    def test_invalid_action_is_quiet_and_records_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'result.json'
            result = subprocess.run([str(PHP), str(PROBE), '--action=invalid', '--output=' + str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout + result.stderr, '')
            self.assertFalse(output.exists())
            self.assertIn('Unsupported action', Path(str(output) + '.log').read_text())

    def test_import_requires_successful_matching_validation_before_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'result.json'
            failed = Path(directory) / 'validation.json'
            failed.write_text(json.dumps({'action': 'validate', 'result': {'errors': 1}}))
            result = subprocess.run([str(PHP), str(PROBE), '--action=import', '--validation=' + str(failed), '--output=' + str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout + result.stderr, '')
            self.assertIn('Successful native validation is required', Path(str(output) + '.log').read_text())

    def test_incomplete_cli_is_quiet(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'result.json'
            result = subprocess.run([str(PHP), str(PROBE), '--action=validate', '--output=' + str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout + result.stderr, '')
            self.assertIn('Missing required argument', Path(str(output) + '.log').read_text())
