import pathlib
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from white_jpeg_review_queue import ReviewQueue


class ReviewQueueTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.audit = pathlib.Path(self.directory.name)
        self.path = self.audit / 'review-priority/features.sqlite3'
        self.path.parent.mkdir()
        self.db = sqlite3.connect(self.path)
        self.db.execute('CREATE TABLE features(file TEXT PRIMARY KEY,source_sha256 TEXT,output_sha256 TEXT,identity TEXT,screen TEXT,region_count INTEGER)')
        self.rows = [{'file': str(n), 'source_sha256': 'src' + str(n), 'output_sha256': 'out' + str(n)} for n in range(4)]

    def tearDown(self):
        self.db.close()
        self.directory.cleanup()

    def add(self, n, regions=0, screen=None):
        self.db.execute('INSERT INTO features VALUES(?,?,?,?,?,?)', (str(n), 'src' + str(n), 'out' + str(n), 'policy', screen, regions))
        self.db.commit()

    def test_measured_easy_pairs_before_difficult_and_unmeasured(self):
        self.add(2, 5)
        self.add(3, 0)
        queue = ReviewQueue(self.audit, self.rows, 'policy')
        self.assertEqual([row['file'] for row in queue], ['3', '2', '0', '1'])

    def test_new_measurements_can_change_order_without_duplicates(self):
        queue = ReviewQueue(self.audit, self.rows, 'policy', refresh_seconds=0)
        self.assertEqual(next(queue)['file'], '0')
        self.add(0)
        self.add(3)
        self.assertEqual([row['file'] for row in queue], ['3', '1', '2'])

    def test_mismatched_measurement_cannot_change_order(self):
        self.add(2)
        self.db.execute("UPDATE features SET output_sha256='different'")
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            next(ReviewQueue(self.audit, self.rows, 'policy'))

    def test_no_measurements_preserves_all_rows(self):
        self.assertEqual(list(ReviewQueue(self.audit, self.rows, 'policy')), self.rows)


if __name__ == '__main__':
    unittest.main()
