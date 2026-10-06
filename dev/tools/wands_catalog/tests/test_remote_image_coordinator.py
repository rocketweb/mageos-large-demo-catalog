import json
import fcntl
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run_remote_image_batches as coordinator
import remote_image_batch


class CoordinatorTest(unittest.TestCase):
    def test_pending_retained_review_keeps_remote_worker_available_when_new_products_are_done(self):
        from bulk_expansion_images import connect
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);db=connect(run)
            db.execute('CREATE TABLE jobs(state,pilot)')
            db.execute("INSERT INTO jobs VALUES('accepted',0)")
            db.execute('CREATE TABLE references_to_review(review)')
            db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,NULL)',('source','design',1,'path','image'))
            db.commit();db.close()
            self.assertTrue(coordinator.has_future_work(run))

    def test_linux_worker_has_independent_reservations_state_and_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);manifest=run/'manifest.json'
            manifest.write_text(json.dumps({'batch_id':'a'*32,'jobs':[{}]}))
            (run/'REMOTE_STOP').touch()
            with patch.object(coordinator,'reserve',return_value=manifest) as reserve, patch.object(coordinator,'remote_command') as remote, patch.object(coordinator,'sync'), patch.object(coordinator,'import_results'):
                coordinator.coordinate(run,'root@192.168.1.7',Path('/root/wands-image-worker'),4,1,worker_id='laptop')
            self.assertEqual(reserve.call_args.kwargs['worker_id'],'laptop')
            args=[str(x) for x in remote.call_args.args[1]]
            self.assertIn('/root/wands-image-worker/code/cuda_image_batch.py',args)
            self.assertNotIn('caffeinate',args)
            self.assertEqual(json.loads((run/'remote-laptop-state.json').read_text())['state'],'imported_for_review')
            self.assertFalse((run/'remote-worker-state.json').exists())

    def test_cuda_transport_retry_updates_only_laptop_state(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);log=run/'remote-laptop-console.log'
            def stop(_):(run/'REMOTE_STOP-laptop').touch()
            with patch.object(coordinator.subprocess,'run',return_value=SimpleNamespace(returncode=73)), patch.object(coordinator.time,'sleep',side_effect=stop):
                with self.assertRaises(coordinator.RemoteRetryStopped):
                    coordinator.checked(['ssh','host','cuda_image_batch.py render'],log)
            self.assertTrue((run/'remote-laptop-state.json').exists())
            self.assertFalse((run/'remote-worker-state.json').exists())

    def test_reference_files_are_transferred_before_rendering(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);manifest=run/'manifest.json';(run/'references').mkdir()
            manifest.write_text(json.dumps({'batch_id':'a'*32,'jobs':[{'job_id':'b'*64}]}))
            with patch.object(coordinator,'reserve',return_value=manifest), patch.object(coordinator,'remote_command'), patch.object(coordinator,'sync') as sync, patch.object(coordinator,'import_results'):
                coordinator.coordinate(run,'matt@192.168.1.115',Path('/Users/matt/wands-image-worker'),4,1)
            self.assertEqual(sync.call_count,3)
            self.assertEqual(str(sync.call_args_list[1].args[0]),str(run/'references')+'/')

    def test_empty_ready_queue_waits_for_studio_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)
            def stop(_):(run/'REMOTE_STOP').touch()
            with patch.object(coordinator,'reserve',return_value=None), patch.object(coordinator,'has_future_work',return_value=True), patch.object(coordinator.time,'sleep',side_effect=stop):
                coordinator.coordinate(run,'matt@192.168.1.115',Path('/Users/matt/wands-image-worker'))
            self.assertEqual(json.loads((run/'remote-worker-state.json').read_text())['state'],'stopped_by_request')

    def test_busy_renderer_exits_without_loading_model(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            with (output/'worker.lock').open('a') as lock, patch.object(remote_image_batch,'_render') as render:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaises(SystemExit) as error:
                    remote_image_batch.render(output/'manifest.json','unused',output/'model',output)
                self.assertEqual(error.exception.code,73)
                render.assert_not_called()

    def test_transport_failure_retries_same_command(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);log=run/'remote-worker-console.log'
            state=run/'remote-worker-state.json'
            state.write_text(json.dumps({'state':'generating','batch_id':'a'*32}))
            args=['ssh','host','remote_image_batch.py render']
            with patch.object(coordinator.subprocess,'run',side_effect=[SimpleNamespace(returncode=255),SimpleNamespace(returncode=73),SimpleNamespace(returncode=0)]) as call, patch.object(coordinator.time,'sleep'):
                coordinator.checked(args,log)
            self.assertEqual(call.call_count,3)
            self.assertTrue(all(c.args[0]==args for c in call.call_args_list))
            self.assertEqual(json.loads(state.read_text())['state'],'generating')
            self.assertEqual(json.loads(state.read_text())['batch_id'],'a'*32)

    def test_stop_interrupts_transport_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);log=run/'remote-worker-console.log'
            def stop(_):(run/'REMOTE_STOP').touch()
            with patch.object(coordinator.subprocess,'run',return_value=SimpleNamespace(returncode=255)) as call, patch.object(coordinator.time,'sleep',side_effect=stop):
                with self.assertRaises(coordinator.RemoteRetryStopped):coordinator.checked(['ssh','host','cmd'],log)
            self.assertEqual(call.call_count,1)

    def test_render_failure_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(coordinator.subprocess,'run',return_value=SimpleNamespace(returncode=1)) as call:
                with self.assertRaises(RuntimeError):coordinator.checked(['ssh','host','remote_image_batch.py render'],Path(directory)/'log')
            self.assertEqual(call.call_count,1)

    def test_transport_retries_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(coordinator.subprocess,'run',return_value=SimpleNamespace(returncode=255)) as call, patch.object(coordinator.time,'sleep'):
                with self.assertRaises(RuntimeError):coordinator.checked(['ssh','host','cmd'],Path(directory)/'log')
            self.assertEqual(call.call_count,31)

    def test_completed_transfer_is_imported_for_review(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);manifest=run/'manifest.json'
            manifest.write_text(json.dumps({'batch_id':'a'*32,'jobs':[{'job_id':'b'*64}]}))
            with patch.object(coordinator,'reserve',return_value=manifest), \
                    patch.object(coordinator,'remote_command') as remote, \
                    patch.object(coordinator,'sync') as sync, \
                    patch.object(coordinator,'import_results',side_effect=[BlockingIOError(),{}]) as imported, \
                    patch.object(coordinator.time,'sleep'):
                coordinator.coordinate(run,'matt@192.168.1.115',Path('/Users/matt/wands-image-worker'),4,1)
            self.assertEqual(imported.call_count,2)
            self.assertEqual(sync.call_count,2)
            args=[str(x) for x in remote.call_args.args[1]]
            self.assertIn('--manifest-sha256',args)
            self.assertIn(coordinator.sha256(manifest),args)
            state=json.loads((run/'remote-worker-state.json').read_text())
            self.assertEqual(state['state'],'imported_for_review')

    def test_remote_failure_never_imports_or_releases_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);manifest=run/'manifest.json'
            manifest.write_text(json.dumps({'batch_id':'a'*32,'jobs':[{}]}))
            with patch.object(coordinator,'reserve',return_value=manifest), \
                    patch.object(coordinator,'remote_command',side_effect=RuntimeError('transfer failed')), \
                    patch.object(coordinator,'import_results') as imported:
                with self.assertRaises(RuntimeError):
                    coordinator.coordinate(run,'matt@192.168.1.115',Path('/Users/matt/wands-image-worker'),4,1)
            imported.assert_not_called()
            self.assertEqual(json.loads((run/'remote-worker-state.json').read_text())['state'],'needs_attention')

    def test_remote_stop_prevents_new_reservations(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);(run/'REMOTE_STOP').touch()
            with patch.object(coordinator,'reserve') as reserve:
                coordinator.coordinate(run,'matt@192.168.1.115',Path('/Users/matt/wands-image-worker'))
            reserve.assert_not_called()

    def test_destination_arguments_cannot_inject_remote_shell_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                coordinator.coordinate(Path(directory),'matt@host; touch /tmp/wrong',Path('/Users/matt/wands-image-worker'))
            with self.assertRaises(ValueError):
                coordinator.coordinate(Path(directory),'matt@host',Path('/etc'))


if __name__=='__main__':unittest.main()
