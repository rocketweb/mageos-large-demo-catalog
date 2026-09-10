import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from completion_review import bind_observations
from reconcile_catalog_media import digest
from test_review_catalog_framing_pilot import fixture


class CompletionReviewTest(unittest.TestCase):
    def test_nonpaired_cases_preserve_original_digest_and_reject_stale_notes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); cases, notes = fixture(root)
            for c, n in zip(cases, notes):
                c.pop('arm'); n['case_sha256'] = digest(c)
            original = copy.deepcopy(cases)
            rows = bind_observations(cases, notes, root)
            self.assertEqual(cases, original)
            self.assertEqual([r['case'] for r in rows], original)
            self.assertTrue(all(r['case_sha256'] == digest(r['case']) for r in rows))
            self.assertTrue(all(not r['assembly_ready'] and not r['mask_ready'] and not r['publication_approved'] for r in rows))
            notes[0]['case_sha256'] = '0' * 64
            with self.assertRaises(ValueError): bind_observations(cases, notes, root)


if __name__ == '__main__': unittest.main()
