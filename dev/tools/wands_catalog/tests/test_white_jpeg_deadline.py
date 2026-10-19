import json
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import white_jpeg_calibrated_audit as checks
import white_jpeg_deadline as deadline


class DeadlineSelectionTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript('''CREATE TABLE images(n INTEGER PRIMARY KEY,file TEXT,row_json TEXT,decision TEXT,reason TEXT);
            CREATE TABLE calibrated_features(file TEXT,features TEXT);
            CREATE TABLE calibrated_reviews(file TEXT,kind TEXT,identity TEXT,source_sha256 TEXT,output_sha256 TEXT,review TEXT,details TEXT);''')
        self.row = {'file': 'source.jpg', 'source_sha256': 'source', 'output_file': 'output.jpg', 'output_sha256': 'output'}
        self.features = {'border_edge_fraction': 0, 'backdrop_fit_p90': 0, 'white_border': 1, 'risk_regions': []}
        self.review = {'background': 'studio', 'product_preserved': True, 'white_background': True, 'confidence': .95, 'reason': 'Product intact'}
        self.details = {'model': checks.MODEL, 'review_identity': checks.review_identity(checks.MODEL)}

    def tearDown(self):
        self.db.close()

    def add(self, decision='white', evidence=True):
        self.db.execute('INSERT INTO images VALUES(1,?,?,?,?)', ('source.jpg', json.dumps(self.row), decision, 'prior_reason'))
        if evidence:
            self.db.execute('INSERT INTO calibrated_features VALUES(?,?)', ('source.jpg', json.dumps(self.features)))
            self.db.execute('INSERT INTO calibrated_reviews VALUES(?,?,?,?,?,?,?)', (
                'source.jpg', 'pair', checks.decision_identity(), 'source', 'output', json.dumps(self.review), json.dumps(self.details)))
        self.db.commit()

    def test_qualified_positive_is_reused(self):
        self.add()
        result = deadline.prepare_decisions(self.db, checks)
        self.assertEqual(result['reviewed_white'], 1)
        self.assertEqual(self.db.execute('SELECT decision FROM images').fetchone()[0], 'white')

    def test_missing_evidence_never_selects_white(self):
        self.add(evidence=False)
        with self.assertRaisesRegex(ValueError, 'lacks individual evidence'):
            deadline.prepare_decisions(self.db, checks)

    def test_negative_primary_cannot_be_promoted(self):
        self.review['product_preserved'] = False
        self.add()
        with self.assertRaisesRegex(ValueError, 'no longer passes'):
            deadline.prepare_decisions(self.db, checks)

    def test_changed_candidate_hash_invalidates_positive(self):
        self.add()
        self.db.execute("UPDATE calibrated_reviews SET output_sha256='other'")
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            deadline.prepare_decisions(self.db, checks)

    def test_unreviewed_and_source_only_use_original(self):
        for decision in (None, 'eligible', 'pending'):
            with self.subTest(decision=decision):
                self.db.execute('DELETE FROM images')
                self.add(decision, evidence=False)
                counts = deadline.prepare_decisions(self.db, checks)
                self.assertEqual(counts['unfinished_original'], 1)
                self.assertEqual(self.db.execute('SELECT decision,reason FROM images').fetchone(),
                                 ('original', 'launch_deadline_unfinished_review_keep_original'))

    def test_existing_rejection_stays_original(self):
        self.add('original', evidence=False)
        self.assertEqual(deadline.prepare_decisions(self.db, checks)['resolved_original'], 1)
        self.assertEqual(self.db.execute('SELECT reason FROM images').fetchone()[0], 'prior_reason')

    def test_unreviewed_risk_region_cannot_select_white(self):
        self.features['risk_regions'] = [{'crop': [0, 0, 100, 100]}]
        self.add()
        with self.assertRaisesRegex(ValueError, 'no longer passes'):
            deadline.prepare_decisions(self.db, checks)

    def test_final_export_runs_once_and_overdue_export_takes_precedence(self):
        config = {'freeze_at': 100}
        self.assertEqual(deadline.due_slot(config, None, 10), 'baseline')
        self.assertIsNone(deadline.due_slot(config, {'slot': 'baseline'}, 10))
        self.assertEqual(deadline.due_slot(config, None, 110), 'deadline')
        self.assertEqual(deadline.due_slot(config, {'slot': 'baseline'}, 110), 'deadline')
        self.assertIsNone(deadline.due_slot(config, {'slot': 'deadline'}, 110))

    def test_easy_first_review_rate_is_not_presented_as_full_audit_eta(self):
        html = '<h2>Launch</h2><p>Current review pass: 54 / 92,554; estimate: Sun Oct 18, 04:08 PM EDT.</p><p>Estimated full selection ready: <strong>Sun Oct 18, 05:00 PM EDT</strong>. Current rate.</p>'
        updated, _ = deadline.qualify_progress(html, '')
        self.assertNotIn('04:08 PM', updated)
        self.assertNotIn('05:00 PM', updated)
        self.assertIn('54 / 92,554', updated)
        self.assertIn('complexity', updated)

    def test_manual_progress_does_not_claim_biased_eta(self):
        _, console = deadline.qualify_progress('', 'Audit: running\nCurrent review: 54 / 92,554; ETA Sun Oct 18, 04:08 PM EDT\nSelection: {}\n')
        self.assertNotIn('04:08 PM', console)
        self.assertIn('Current review: 54 / 92,554', console)


if __name__ == '__main__':
    unittest.main()
