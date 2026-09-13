import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_gallery_expansion import build, SUBJECTS


class GalleryExpansionTest(unittest.TestCase):
    def test_different_bytes_cannot_inherit_visual_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for sku in SUBJECTS:
                (root / (sku+'.jpg')).write_bytes(b'not the inspected image')
            with self.assertRaisesRegex(ValueError, 'inspected'):
                build(root, root/'queue')
            self.assertFalse((root/'queue').exists())

    def test_bound_references_produce_unique_jobs_and_no_live_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('prepare_gallery_expansion.sha256', return_value='f'*64), patch(
                    'prepare_gallery_expansion.APPROVED_HASHES', {s:'f'*64 for s in SUBJECTS}, create=True):
                build(root, root/'queue')
            jobs = [json.loads(line) for line in (root/'queue/jobs.jsonl').read_text().splitlines()]
            self.assertEqual(len(jobs), 21)
            self.assertEqual(len({j['output_file'] for j in jobs}), 21)
            self.assertEqual({j['view'] for j in jobs}, {'angle','detail','room'})
            self.assertTrue(all('reference_images' in j for j in jobs))
            with self.assertRaises(ValueError):
                build(root, root/'queue')


if __name__ == '__main__':
    unittest.main()
