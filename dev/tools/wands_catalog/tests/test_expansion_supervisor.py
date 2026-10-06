"""Completing new images must not abandon unfinished retained-media review."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_expansion_batches as worker


class SupervisorCompletionTest(unittest.TestCase):
    def test_retained_remote_repairs_keep_studio_waiting_for_images_instead_of_stopping(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);db=worker.connect(run)
            db.execute('CREATE TABLE remote_batches(state)');db.execute("INSERT INTO remote_batches VALUES('reserved')");db.commit();db.close()
            counts={'jobs':[{'state':'accepted','n':4}]};states=[]
            def stop(_):
                states.append(json.loads((run/'worker-state.json').read_text())['state']);(run/'STOP').touch()
            with patch.object(worker,'descriptor',return_value={}),patch.object(worker,'counts',return_value=counts), \
                    patch.object(worker.time,'sleep',side_effect=stop), \
                    patch.object(worker.subprocess,'run',return_value=SimpleNamespace(returncode=0)), \
                    patch('export_expanded_catalog.inspect',return_value=({}, {'ready':False}, [], {})):
                worker.supervise(run,Path('/ocr'),Path('/private-settings'),pilot=False)
            self.assertEqual(states,['waiting_for_remote_images'])

    def test_completed_local_work_waits_for_reserved_remote_images(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);counts={'jobs':[{'state':'accepted','n':4},{'state':'remote_reserved','n':2}]}
            states=[]
            def stop(_):
                states.append(json.loads((run/'worker-state.json').read_text())['state']);(run/'STOP').touch()
            with patch.object(worker,'descriptor',return_value={}),patch.object(worker,'counts',return_value=counts), \
                    patch.object(worker.time,'sleep',side_effect=stop), \
                    patch.object(worker.subprocess,'run',return_value=SimpleNamespace(returncode=0)):
                worker.supervise(run,Path('/ocr'),Path('/private-settings'),pilot=False)
            self.assertEqual(states,['waiting_for_remote_images'])
            self.assertEqual(json.loads((run/'worker-state.json').read_text())['state'],'stopped_by_request')

    def test_remote_review_backlog_is_drained_in_bounded_batches(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)
            self.assertEqual(worker.review_batch_limit(run,64),64)
            (run/'remote-batches').mkdir();db=worker.connect(run)
            db.execute('CREATE TABLE jobs(state)');db.executemany('INSERT INTO jobs VALUES(?)',[('generated',)]*300)
            db.commit();db.close()
            self.assertEqual(worker.review_batch_limit(run,64),256)

    def test_remote_transfer_lock_contention_waits_and_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);states=[]
            def observe(_):states.append(json.loads((run/'worker-state.json').read_text())['state'])
            with patch.object(worker.subprocess,'run',side_effect=[SimpleNamespace(returncode=73),SimpleNamespace(returncode=0)]) as calls, \
                    patch.object(worker.time,'sleep',side_effect=observe):
                self.assertTrue(worker.run_phase(run,run/'worker-state.json',['python'],'generate',0,False))
            self.assertEqual(calls.call_count,2)
            self.assertEqual(states,['waiting_for_catalog_worker'])

    def test_generation_does_not_inherit_metal_debug_wrapper(self):
        for command in ('generate','generate-admitted','repair-references'):
            with self.subTest(command=command),tempfile.TemporaryDirectory() as directory:
                run=Path(directory)
                with patch.dict(worker.os.environ,{'METAL_DEVICE_WRAPPER_TYPE':'1','MLX_METAL_MEM_LIMIT':'180000000000'},clear=True), \
                        patch.object(worker.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as call:
                    self.assertTrue(worker.run_phase(run,run/'worker-state.json',['python','worker.py'],command,0,False))
                env=call.call_args.kwargs.get('env',{'METAL_DEVICE_WRAPPER_TYPE':'1'})
                self.assertNotIn('METAL_DEVICE_WRAPPER_TYPE',env)
                self.assertEqual(env['MLX_METAL_MEM_LIMIT'],'180000000000')

    def test_service_outage_waits_then_retries_same_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)
            before={'jobs':[{'state':'pending','n':2}]}
            after={'jobs':[{'state':'accepted','n':1},{'state':'pending','n':1}]}
            observed=[]
            def record_wait(seconds):
                observed.append(json.loads((run/'worker-state.json').read_text())['state'])
            with patch.object(worker,'descriptor',return_value={}), \
                    patch.object(worker,'counts',side_effect=[before,after]), \
                    patch.object(worker.time,'sleep',side_effect=record_wait), \
                    patch.object(worker.subprocess,'run',side_effect=[SimpleNamespace(returncode=c) for c in [75,0,0,0,0,0]]) as calls:
                worker.supervise(run,Path('/ocr'),Path('/private-settings'),max_cycles=1)
            self.assertEqual(calls.call_count,6)
            self.assertEqual(calls.call_args_list[0].args[0],calls.call_args_list[1].args[0])
            self.assertIn('waiting_for_review_service',observed)
            self.assertEqual(json.loads((run/'worker-state.json').read_text())['state'],'cycle_limit_reached')

    def test_stop_interrupts_service_wait_without_more_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)
            with patch.object(worker,'descriptor',return_value={}), \
                    patch.object(worker,'counts',return_value={}), \
                    patch.object(worker.time,'sleep',side_effect=lambda _: (run/'STOP').touch()), \
                    patch.object(worker.subprocess,'run',return_value=SimpleNamespace(returncode=75)) as calls:
                worker.supervise(run,Path('/ocr'),Path('/private-settings'))
            self.assertEqual(calls.call_count,1)
            self.assertEqual(json.loads((run/'worker-state.json').read_text())['state'],'stopped_by_request')

    def test_non_service_failure_still_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)
            with patch.object(worker,'descriptor',return_value={}), \
                    patch.object(worker,'counts',return_value={}), \
                    patch.object(worker.subprocess,'run',return_value=SimpleNamespace(returncode=1)) as calls:
                worker.supervise(run,Path('/ocr'),Path('/private-settings'))
            self.assertEqual(calls.call_count,1)
            self.assertEqual(json.loads((run/'worker-state.json').read_text())['state'],'needs_attention')

    def test_full_run_continues_until_retained_images_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            before = {'jobs': [{'state': 'accepted', 'n': 48844}], 'reviewed_references': 100}
            after = {'jobs': [{'state': 'accepted', 'n': 48844}], 'reviewed_references': 164}
            with patch.object(worker, 'descriptor', return_value={}), \
                    patch.object(worker, 'counts', side_effect=[before, after]), \
                    patch.object(worker.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                    patch('export_expanded_catalog.inspect', return_value=({}, {'ready': False, 'unresolved_retained_briefs': 47612}, [], {})), \
                    patch('export_expanded_catalog.export') as export:
                worker.supervise(run, Path('/ocr'), Path('/private-settings'), pilot=False, batch=64,
                                 max_cycles=1, export_output=run / 'export')
                export.assert_not_called()
            state = json.loads((run / 'worker-state.json').read_text())
            self.assertEqual(state['state'], 'cycle_limit_reached')
            self.assertNotEqual(state['state'], 'ready_for_final_audit')

    def test_accepted_export_remains_distinct_from_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            counts = {'jobs': [{'state': 'accepted', 'n': 48844}], 'reviewed_references': 47776}
            output = run / 'export'
            def create_export(actual_run, actual_output):
                self.assertEqual(actual_run, run)
                self.assertEqual(actual_output, output)
                output.mkdir()
                (output / 'manifest.json').write_text('{"products":107688}')
            with patch.object(worker, 'descriptor', return_value={}), \
                    patch.object(worker, 'counts', return_value=counts), \
                    patch.object(worker.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                    patch('export_expanded_catalog.inspect', return_value=({}, {'ready': True}, [], {})), \
                    patch('export_expanded_catalog.export', side_effect=create_export) as export:
                worker.supervise(run, Path('/ocr'), Path('/private-settings'), pilot=False,
                                 batch=64, max_cycles=1, export_output=output)
                export.assert_called_once()
            state = json.loads((run / 'worker-state.json').read_text())
            self.assertEqual(state['state'], 'accepted_catalog_exported; installation_pending')
            self.assertEqual(state['output'], str(output))
            self.assertEqual(len(state['manifest_sha256']), 64)


if __name__ == '__main__':
    unittest.main()
