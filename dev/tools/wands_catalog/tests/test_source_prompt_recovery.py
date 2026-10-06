import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest
import types
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bulk_expansion_images import retry_allowed, source_recolor_prompt
from build_expanded_catalog import digest
from prepare_catalog import sha256


class SourcePromptRecoveryTest(unittest.TestCase):
    def test_prompt_pin_survives_unrelated_source_line_moves(self):
        from source_prompt_recovery import prompt_pin
        expected=prompt_pin()
        old_function=types.FunctionType(source_recolor_prompt.__code__.replace(co_firstlineno=1),
                                        source_recolor_prompt.__globals__,source_recolor_prompt.__name__)
        with mock.patch('bulk_expansion_images.source_recolor_prompt',old_function):
            self.assertEqual(prompt_pin(),expected)

    def test_prompt_pin_rejects_a_different_loaded_implementation(self):
        from source_prompt_recovery import prompt_pin
        with mock.patch('bulk_expansion_images.source_recolor_prompt',lambda job: 'different prompt'):
            with self.assertRaises(ValueError):prompt_pin()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.run = Path(tmp.name)
        self.source = self.run/'source.jpg'
        self.source.write_bytes(b'accepted source')
        self.job = {'job_id': 'job', 'reference': {'job_id': 'source', 'value': 'Oak'},
                    'design': {'color': 'Oak'}}
        self.directory = self.run/'candidates/job'
        self.directory.mkdir(parents=True)
        for attempt in range(1, 4):
            self.attempt(attempt, 'Preserve every mounting part, hanging chain and ring in full view inside the frame.')
        self.row = {'attempts': 3, 'state': 'rejected', 'image_sha256': sha256(self.directory/'attempt-03.jpg'),
                    'image_path': str(self.directory/'attempt-03.jpg')}
        (self.run/'run.json').write_text(json.dumps({'candidate_sha256': 'catalog', 'review_identity': 'review'}))
        self.benchmark = self.run/'benchmark.json'
        self.benchmark.write_text(json.dumps({'passed': True, 'strategy': 'source-recolor-v2',
            'prompt_implementation_sha256': digest(inspect.getsource(source_recolor_prompt)),
            'candidate_sha256': 'catalog', 'review_identity': 'review',
            'direct_visual_review_complete': True}))
        self.entry = {'request_sha256': digest(self.job), 'baseline_attempts': 3,
                      'baseline_image_sha256': self.row['image_sha256'],
                      'baseline_metadata_sha256': sha256(self.directory/'attempt-03.json'),
                      'reference_sha256': sha256(self.source),
                      'prompt_sha256': digest(source_recolor_prompt(self.job))}

    def attempt(self, number, prompt):
        path = self.directory/f'attempt-{number:02d}.jpg'
        path.write_bytes(('image '+str(number)).encode())
        path.with_suffix('.json').write_text(json.dumps({'attempt': number, 'actual_prompt': prompt,
            'image_sha256': sha256(path), 'reference_sha256': sha256(self.source)}))

    def admit(self):
        (self.run/'source-recolor-recovery.json').write_text(json.dumps({
            'schema': 1, 'strategy': 'source-recolor-v2', 'max_extra_attempts': 2,
            'run_sha256': sha256(self.run/'run.json'), 'benchmark_path': str(self.benchmark),
            'benchmark_sha256': sha256(self.benchmark),
            'prompt_implementation_sha256': digest(inspect.getsource(source_recolor_prompt)),
            'jobs': {'job': self.entry}}))

    def test_exhausted_job_gets_two_bounded_attempts_after_pinned_admission(self):
        self.assertFalse(retry_allowed(self.run, self.row, self.job, self.source))
        self.admit()
        self.assertTrue(retry_allowed(self.run, self.row, self.job, self.source))
        for number in (4, 5):
            self.attempt(number, source_recolor_prompt(self.job))
            path = self.directory/f'attempt-{number:02d}.jpg'
            row = {**self.row, 'attempts': number, 'image_path': str(path), 'image_sha256': sha256(path)}
            self.assertEqual(retry_allowed(self.run, row, self.job, self.source), number < 5)

    def test_unlisted_jobs_and_standalones_do_not_get_extra_attempts(self):
        self.admit()
        self.assertFalse(retry_allowed(self.run, self.row, {**self.job, 'job_id': 'other'}, self.source))
        self.assertFalse(retry_allowed(self.run, self.row, {**self.job, 'reference': None}, None))

    def test_changed_request_or_old_image_cannot_use_the_admission(self):
        self.admit()
        self.assertFalse(retry_allowed(self.run, self.row, {**self.job, 'design': {'color': 'White'}}, self.source))
        (self.directory/'attempt-03.jpg').write_bytes(b'changed')
        self.assertFalse(retry_allowed(self.run, self.row, self.job, self.source))

    def test_missing_or_changed_history_cannot_reset_the_budget(self):
        self.admit()
        metadata = self.directory/'attempt-03.json'
        data = json.loads(metadata.read_text());data['actual_prompt'] = 'unrelated recipe'
        metadata.write_text(json.dumps(data))
        self.assertFalse(retry_allowed(self.run, self.row, self.job, self.source))
        metadata.unlink()
        self.assertFalse(retry_allowed(self.run, self.row, self.job, self.source))

    def test_changed_benchmark_fails_closed(self):
        self.admit()
        self.benchmark.write_text('{}')
        with self.assertRaises(ValueError):
            retry_allowed(self.run, self.row, self.job, self.source)

    def test_accepted_images_cannot_use_recovery(self):
        self.admit()
        self.assertFalse(retry_allowed(self.run, {**self.row, 'state': 'accepted'}, self.job, self.source))

    def test_receipt_changes_are_rechecked_after_a_successful_cached_read(self):
        self.admit()
        self.assertTrue(retry_allowed(self.run, self.row, self.job, self.source))
        self.benchmark.write_text('{}')
        with self.assertRaises(ValueError):
            retry_allowed(self.run, self.row, self.job, self.source)

    def test_an_unrelated_later_correction_does_not_reopen_this_recovery(self):
        self.admit()
        self.attempt(4, 'A separately diagnosed manual correction')
        path = self.directory/'attempt-04.jpg'
        row = {**self.row, 'attempts': 4, 'image_path': str(path), 'image_sha256': sha256(path)}
        self.assertFalse(retry_allowed(self.run, row, self.job, self.source))


if __name__ == '__main__':
    unittest.main()
