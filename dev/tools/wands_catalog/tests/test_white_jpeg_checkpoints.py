import fcntl
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import white_jpeg_checkpoints as checkpoints


class CheckpointTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.job = Path(self.temp.name)
        self.audit = self.job / 'audit'
        self.here = self.audit / 'glass'
        self.here.mkdir(parents=True)
        self.write(self.audit / 'config.json', {'python': sys.executable})
        self.write(self.audit / 'latest.json', {'slot': 'old', 'verified_at': 1000,
                   'verification': str(self.audit / 'selections/old/verification.json')})
        self.write(self.audit / 'selections/old/snapshot.json', {'created_at': 950})
        with sqlite3.connect(self.audit / 'audit.sqlite3') as db:
            db.executescript('CREATE TABLE category_evidence(decided_at REAL);'
                             'INSERT INTO category_evidence VALUES(2000);'
                             'CREATE TABLE glass_outline_checks(file TEXT,verdict TEXT,updated_at REAL);'
                             "INSERT INTO glass_outline_checks VALUES('glass.jpg','pending_review',2000);"
                             'CREATE TABLE images(file TEXT,decision TEXT,reason TEXT);'
                             "INSERT INTO images VALUES('glass.jpg','original','hold');"
                             "INSERT INTO images VALUES('room.jpg','original','room_bundle_preserve_scene');")
        self.launch = patch.object(checkpoints.subprocess, 'Popen')
        self.popen = self.launch.start()
        self.popen.return_value.pid = 99999999
        self.addCleanup(self.launch.stop)
        self.disk = patch.object(checkpoints.shutil, 'disk_usage')
        self.disk_mock = self.disk.start()
        self.disk_mock.return_value.free = 50 * 1024**3
        self.addCleanup(self.disk.stop)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def maybe(self, now=5000):
        return checkpoints.maybe_checkpoint(self.job, self.audit, self.here, self, now=now)

    def test_changed_reviews_start_an_hourly_export_and_record_receipt(self):
        self.assertEqual(self.maybe(), 'started')
        receipt = checkpoints.read(self.here / 'checkpoint-process.json')
        self.assertEqual(receipt['pid'], 99999999)
        self.assertTrue(receipt['slot'].startswith('overnight-'))
        command = self.popen.call_args.args[0]
        self.assertEqual(command[0], '/usr/bin/caffeinate')
        self.assertIn(receipt['slot'], command)

    def test_recent_export_and_unchanged_review_state_do_not_launch(self):
        self.assertEqual(self.maybe(now=1500), 'current')
        self.write(self.audit / 'selections/old/snapshot.json', {'created_at': 3000})
        self.assertEqual(self.maybe(), 'unchanged')
        self.popen.assert_not_called()

    def test_live_export_and_shared_export_lock_prevent_duplicate_work(self):
        self.write(self.here / 'checkpoint-process.json', {'pid': __import__('os').getpid()})
        self.assertEqual(self.maybe(), 'building')
        self.write(self.here / 'checkpoint-process.json', {})
        with (self.audit / 'export.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertEqual(self.maybe(), 'building')
        self.popen.assert_not_called()

    def test_interrupted_export_resumes_its_immutable_snapshot(self):
        self.write(self.here / 'checkpoint-process.json', {'pid': 99999998, 'slot': 'overnight-interrupted'})
        self.assertEqual(self.maybe(now=1500), 'started')
        self.assertEqual(checkpoints.read(self.here / 'checkpoint-process.json')['slot'], 'overnight-interrupted')

    def test_integrity_failure_and_low_disk_keep_previous_selection(self):
        self.write(self.audit / 'export-status.json', {'state': 'needs_attention'})
        self.assertEqual(self.maybe(), 'needs_attention')
        self.write(self.audit / 'export-status.json', {})
        self.disk_mock.return_value.free = 1024
        self.assertEqual(self.maybe(), 'needs_attention')
        self.assertEqual(checkpoints.read(self.audit / 'latest.json')['slot'], 'old')
        self.popen.assert_not_called()

    def test_safety_gate_rejects_a_missing_glass_outline_selected_white(self):
        self.assertEqual(checkpoints.safety(self.audit / 'audit.sqlite3', total=2, rooms=1)['held_glass_selected_white'], 0)
        with sqlite3.connect(self.audit / 'audit.sqlite3') as db:
            db.execute("UPDATE images SET decision='white' WHERE file='glass.jpg'")
        with self.assertRaisesRegex(ValueError, 'unresolved glass outlines'):
            checkpoints.safety(self.audit / 'audit.sqlite3', total=2, rooms=1)

    def test_failed_export_rolls_back_latest_and_requires_attention(self):
        def fail(*args):
            self.write(self.audit / 'latest.json', {'slot': 'overnight-failure'})
            raise ValueError('fixture integrity failure')
        with patch.object(checkpoints, 'safety', return_value={}), patch.object(self, 'export_selection', fail):
            with self.assertRaisesRegex(ValueError, 'fixture integrity failure'):
                checkpoints.run_checkpoint(self.job, self.audit, self.here, 'overnight-failure', self)
        self.assertEqual(checkpoints.read(self.audit / 'latest.json')['slot'], 'old')
        self.assertEqual(checkpoints.read(self.audit / 'export-status.json')['state'], 'needs_attention')

    def export_selection(self, *args):
        raise AssertionError('Unexpected export')


if __name__ == '__main__':
    unittest.main()
