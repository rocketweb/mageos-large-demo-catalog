import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from review_rejected_images import Conflict, ReviewStore, make_server, summarize_feedback


class HumanImageReviewTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run = self.root / 'run'
        self.baseline = self.root / 'baseline'
        self.candidate = self.root / 'candidate'
        for path in (self.run, self.baseline / 'data', self.candidate / 'data'):
            path.mkdir(parents=True)
        source = self.baseline / 'source.jpg'
        source.write_bytes(b'fixture-source-image')
        self.source = source
        self.source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        for path, rows in [(self.baseline, [{'sku': 'SOURCE', 'name': 'Source chair'}]),
                           (self.candidate, [{'sku': 'BLUE', 'name': 'Blue Chair', 'price': '99.99',
                                              'short_description': '<p>A chair with an open back.</p>'},
                                             {'sku': 'WHITE', 'name': 'White Chair'}])]:
            with (path / 'data' / '1-simple.csv').open('w', newline='') as stream:
                fields = ['sku', 'name', 'price', 'short_description']
                writer = csv.DictWriter(stream, fields)
                writer.writeheader()
                writer.writerows(rows)
        (self.run / 'run.json').write_text(json.dumps({'baseline': str(self.baseline), 'candidate': str(self.candidate)}))
        with sqlite3.connect(self.run / 'ledger.sqlite') as db:
            db.executescript('''
                CREATE TABLE jobs(job_id TEXT PRIMARY KEY, request TEXT, state TEXT,
                                  image_path TEXT, image_sha256 TEXT, review TEXT, attempts INTEGER, updated REAL);
                CREATE TABLE references_to_review(image_sha256 TEXT, path TEXT);
                CREATE TABLE reference_repairs(image_sha256 TEXT, image_path TEXT);
            ''')
            db.execute('INSERT INTO references_to_review VALUES(?,?)', (self.source_hash, str(source)))
            for index, color in enumerate(('BLUE', 'WHITE')):
                image = self.run / color / 'attempt-03.jpg'
                image.parent.mkdir()
                image.write_bytes(('candidate-' + color).encode())
                pin = hashlib.sha256(image.read_bytes()).hexdigest()
                image.with_suffix('.json').write_text(json.dumps({'reference_sha256': self.source_hash,
                                                                  'image_sha256': pin, 'actual_prompt': 'Pinned fixture prompt',
                                                                  'config': {'steps': 4}, 'seed': index}))
                job = {'sku': color, 'job_id': color, 'department': 'Furniture', 'profile': 'Chairs',
                       'reference': {'sku': 'SOURCE'},
                       'design': {'subject': color + ' chair', 'color': color.title(),
                                  'material': 'Wood', 'options': {'color': color.title()},
                                  'dimensions_cm': {'lab_spec_width_cm': '50'}}}
                db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)',
                           (color, json.dumps(job), 'rejected', str(image), pin,
                            json.dumps({'reference_sha256': self.source_hash, 'decision': 'rejected'}), 3, index))
        self.store = ReviewStore(self.run, self.root / 'reviews')
        self.items = self.store.listing()['items']
        self.item = self.items[0]

    def choose(self, choice, note='', revision=0, item=None):
        return self.store.save({'id': (item or self.item)['id'], 'choice': choice, 'note': note, 'revision': revision})

    def test_source_group_details_and_no_automated_reasons_in_ui_payload(self):
        self.assertEqual(self.items[0]['group'], self.items[1]['group'])
        self.assertEqual(self.item['source_name'], 'Source chair')
        self.assertEqual(self.item['description'], 'A chair with an open back.')
        self.assertNotIn('automated_review', self.item)
        self.assertEqual(self.store.image(self.item['id'], 'source'), self.source.read_bytes())

    def test_keep_and_redo_persist_with_prompt_context_and_leave_worker_ledger_unchanged(self):
        self.choose('keep')
        self.choose('redo', 'Keep the back open.', item=self.items[1])
        restarted = ReviewStore(self.run, self.root / 'reviews')
        self.assertEqual(restarted.summary()['keep'], 1)
        self.assertEqual(restarted.summary()['redo'], 1)
        feedback = restarted.feedback()
        self.assertEqual(feedback[1]['human_review']['note'], 'Keep the back open.')
        self.assertEqual(feedback[1]['generation']['actual_prompt'], 'Pinned fixture prompt')
        self.assertEqual(feedback[1]['source_sha256'], self.source_hash)
        exported = [json.loads(line) for line in (self.root / 'reviews' / 'feedback.jsonl').read_text().splitlines()]
        self.assertEqual(len(exported), 2)
        with self.store.ledger() as db:
            self.assertEqual([row['state'] for row in db.execute('SELECT state FROM jobs')], ['rejected', 'rejected'])

    def test_redo_requires_correction_note(self):
        with self.assertRaisesRegex(ValueError, 'note'):
            self.choose('redo', '  ')
        self.assertEqual(self.store.summary()['redo'], 0)

    def test_undo_keeps_history_and_rejects_stale_tabs(self):
        self.choose('keep')
        with self.assertRaises(Conflict):
            self.choose('redo', 'Wrong frame.', revision=0)
        result = self.choose(None, revision=1)
        self.assertEqual(result['decision']['revision'], 2)
        self.assertEqual(self.store.summary()['unreviewed'], 2)
        self.assertEqual(self.store.feedback(), [])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0], 2)

    def test_image_hash_change_blocks_decision(self):
        self.store.payload(self.item['id'])
        image = Path(self.store.payload(self.item['id'])['image_path'])
        image.write_bytes(b'changed')
        with self.assertRaisesRegex(Conflict, 'displayed image changed'):
            self.choose('keep')
        with self.assertRaises(Conflict):
            self.store.image(self.item['id'], 'candidate')

    def test_source_hash_change_blocks_decision(self):
        self.source.write_bytes(b'changed source')
        with self.assertRaisesRegex(Conflict, 'source image changed'):
            self.choose('keep')

    def test_worker_state_change_blocks_decision(self):
        with sqlite3.connect(self.run / 'ledger.sqlite') as db:
            db.execute("UPDATE jobs SET state='accepted' WHERE job_id=?", (self.item['job_id'],))
        with self.assertRaisesRegex(Conflict, 'changed during review'):
            self.choose('keep')

    def test_refresh_retains_decision_and_original_context(self):
        self.choose('redo', 'Preserve wood grain.')
        self.store.refresh()
        self.assertEqual(self.store.feedback()[0]['human_review']['note'], 'Preserve wood grain.')
        self.assertEqual(self.store.summary()['redo'], 1)

    def test_feedback_summary_preserves_notes_and_cohort_outcomes(self):
        self.choose('keep')
        self.choose('redo', 'Preserve the open back.', item=self.items[1])
        report = summarize_feedback(self.root / 'reviews')
        self.assertEqual(report['outcomes'], {'keep': 1, 'redo': 1})
        self.assertEqual(report['cohorts']['material']['Wood'], {'keep': 1, 'redo': 1})
        self.assertEqual(report['human_keep_automated_hold'], 1)
        self.assertEqual(report['redo_notes'][0]['note'], 'Preserve the open back.')
        self.assertEqual(report['redo_notes'][0]['source_sha256'], self.source_hash)
        saved = json.loads((self.root / 'reviews' / 'feedback-summary.json').read_text())
        self.assertEqual(saved, report)

    def test_serving_is_whitelisted_to_catalog_images(self):
        with self.assertRaises(ValueError):
            self.store.safe_path(self.root / 'private.jpg')
        with self.assertRaises(ValueError):
            self.store.image('../../secret', 'candidate')
        with self.assertRaises(ValueError):
            self.store.image(self.item['id'], '../run.json')

    def test_http_roundtrip_and_cross_origin_write_rejection(self):
        server = make_server(self.store, 0)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        origin = f'http://127.0.0.1:{server.server_address[1]}'
        with urllib.request.urlopen(origin + '/api/items') as response:
            self.assertEqual(len(json.load(response)['items']), 2)
        body = json.dumps({'id': self.item['id'], 'choice': 'keep', 'note': '', 'revision': 0}).encode()
        for other_origin, token in [('http://evil.invalid', server.token), (origin, 'invalid')]:
            request = urllib.request.Request(origin + '/api/decision', data=body,
                                             headers={'Origin': other_origin, 'X-Review-Token': token})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request)
            self.assertEqual(caught.exception.code, 403)
        request = urllib.request.Request(origin + '/api/decision', data=body,
                                         headers={'Origin': origin, 'X-Review-Token': server.token})
        with urllib.request.urlopen(request) as response:
            self.assertEqual(json.load(response)['decision']['choice'], 'keep')
        request = urllib.request.Request(origin + '/', headers={'Host': 'evil.invalid'})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 403)


if __name__ == '__main__':
    unittest.main()
