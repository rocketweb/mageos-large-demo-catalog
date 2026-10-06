"""Returned remote batches get the generation lock at the next image boundary."""
import sqlite3
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bulk_expansion_images as images


class RemoteImportCheckpointTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.run = Path(self.directory.name)
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)

    def test_no_remote_table_or_no_returned_packet_keeps_local_generation_running(self):
        self.assertFalse(images.remote_import_pending(self.run, self.db))
        self.db.execute('CREATE TABLE remote_batches(batch_id, state)')
        self.db.execute("INSERT INTO remote_batches VALUES('abc', 'reserved')")
        self.assertFalse(images.remote_import_pending(self.run, self.db))

    def test_only_an_outstanding_received_packet_yields_the_lock(self):
        self.db.execute('CREATE TABLE remote_batches(batch_id, state)')
        self.db.execute("INSERT INTO remote_batches VALUES('abc', 'reserved')")
        returned = self.run / 'remote-batches/abc/returned'
        returned.mkdir(parents=True)
        (returned / 'results.json').write_text('{}')
        self.assertTrue(images.remote_import_pending(self.run, self.db))
        self.db.execute("UPDATE remote_batches SET state='imported'")
        self.assertFalse(images.remote_import_pending(self.run, self.db))

    def test_operator_stop_yields_at_image_boundary(self):
        self.assertFalse(images.generation_checkpoint_requested(self.run, self.db))
        (self.run / 'STOP').touch()
        self.assertTrue(images.generation_checkpoint_requested(self.run, self.db))

    def test_active_remote_waiting_to_reserve_gets_priority_but_stale_state_does_not(self):
        state=self.run/'remote-laptop-state.json'
        state.write_text(json.dumps({'state':'waiting_for_catalog_worker','updated':time.time()}))
        with images.lock(self.run,'remote-coordinator-laptop'):
            self.assertTrue(images.generation_checkpoint_requested(self.run,self.db))
            state.write_text(json.dumps({'state':'waiting_for_catalog_worker','updated':time.time()-60}))
            self.assertFalse(images.generation_checkpoint_requested(self.run,self.db))
            state.write_text(json.dumps({'state':'waiting_for_catalog_worker','updated':time.time()}))
        self.assertFalse(images.generation_checkpoint_requested(self.run,self.db))

    def test_received_packet_prevents_model_loading_and_preserves_reserved_job(self):
        self.db.execute('CREATE TABLE remote_batches(batch_id, state)')
        self.db.execute("INSERT INTO remote_batches VALUES('abc', 'reserved')")
        self.db.execute('CREATE TABLE jobs(state, attempts)')
        self.db.execute("INSERT INTO jobs VALUES('remote_reserved', 2)")
        returned = self.run / 'remote-batches/abc/returned'
        returned.mkdir(parents=True)
        (returned / 'results.json').write_text('{}')
        # Use a second connection: generate closes its own connection on yield.
        self.db.commit()
        local = sqlite3.connect(':memory:')
        self.db.backup(local)
        with patch.object(images, 'descriptor', return_value={}), \
                patch.object(images, 'connect', return_value=local), \
                patch.object(images, 'require_bulk_gate') as gate, \
                patch.object(images, 'status', return_value={'checkpoint': True}), \
                patch.object(images, 'GuardedImageModel') as model:
            result = images.generate(self.run, limit=64)
        gate.assert_called_once()
        model.assert_not_called()
        self.assertEqual(result, {'checkpoint': True})
        self.assertEqual(self.db.execute('SELECT state, attempts FROM jobs').fetchone(), ('remote_reserved', 2))

    def test_remote_return_during_an_image_finishes_that_image_and_leaves_next_attempt_untouched(self):
        database = self.run / 'fixture.sqlite'
        db = sqlite3.connect(database)
        db.execute('CREATE TABLE remote_batches(batch_id, state)')
        db.execute("INSERT INTO remote_batches VALUES('abc', 'reserved')")
        db.execute('CREATE TABLE jobs(job_id, request, ordinal, state, attempts, updated, image_path, image_sha256, review, error)')
        for i in range(2):
            job = {'job_id': str(i), 'prompt': 'fixture prompt', 'design': {}}
            db.execute('INSERT INTO jobs VALUES(?,?,?, ?,0,NULL,NULL,NULL,NULL,NULL)',
                       (str(i), json.dumps(job), i, 'pending'))
        db.commit(); db.close()
        def connect(_):
            result = sqlite3.connect(database)
            result.row_factory = sqlite3.Row
            return result
        class Image:
            def convert(self, _):return self
            def save(self, path, **_):Path(path).write_bytes(b'completed-image')
        model = SimpleNamespace(generate_image=lambda **_: SimpleNamespace(image=Image()))
        # The remote packet arrives during the first image's rendering.
        def rendered(**_):
            returned = self.run / 'remote-batches/abc/returned'
            returned.mkdir(parents=True, exist_ok=True)
            (returned / 'results.json').write_text('{}')
            return SimpleNamespace(image=Image())
        model.generate_image = rendered
        modules = {'transformers': SimpleNamespace(Qwen2TokenizerFast=SimpleNamespace(from_pretrained=lambda *a, **k: None)),
                   'mflux.models.common.config.model_config': SimpleNamespace(ModelConfig=SimpleNamespace(from_name=lambda _: None)),
                   'mflux.models.flux2.variants': SimpleNamespace(Flux2Klein=lambda **_: model, Flux2KleinEdit=lambda **_: model)}
        desc = {'model_snapshot': str(self.run), 'model_files': {}, 'review_identity': 'fixture'}
        with patch.dict(sys.modules, modules), patch.object(images, 'descriptor', return_value=desc), \
                patch.object(images, 'connect', side_effect=connect), patch.object(images, 'require_bulk_gate'), \
                patch.object(images, 'requeue_changed_sources'), patch.object(images, 'validate_prompt'), \
                patch.object(images, 'check_token_budget'), patch.object(images, 'GuardedImageModel', return_value=model), \
                patch.object(images, 'generation_input', return_value={'reference': None, 'prompt': 'fixture', 'attempt': 1, 'seed': 1}), \
                patch.object(images, 'status', return_value={}):
            images.generate(self.run, limit=64)
        check = sqlite3.connect(database)
        self.addCleanup(check.close)
        self.assertEqual(check.execute('SELECT state, attempts FROM jobs ORDER BY ordinal').fetchall(),
                         [('generated', 1), ('pending', 0)])
        self.assertTrue((self.run / 'candidates/0/attempt-01.jpg').is_file())
        self.assertFalse((self.run / 'candidates/1').exists())
