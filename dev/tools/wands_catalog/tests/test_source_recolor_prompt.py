import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bulk_expansion_images import connect, generation_input
from image_policy import product_prompt, validate_prompt


class SourceRecolorPromptTest(unittest.TestCase):
    def plan(self, color='Oak', material='Solid Wood', state='rejected', subject='table'):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        run = Path(directory.name)
        source = run/'source.jpg'
        source.write_bytes(b'approved clean source')
        job = {'job_id': 'table', 'seed': 11,
               'reference': {'job_id': 'source', 'axis': 'color', 'value': color},
               'design': {'color': color, 'material': material, 'subject': subject},
               'prompt': product_prompt('Edit the reference photograph. Change only color to '+color+'.')}
        record = {'request': json.dumps(job), 'attempts': 1, 'state': state,
                  'image_path': str(run/'rejected.jpg'), 'image_sha256': 'rejected-hash'}
        db = connect(run)
        self.addCleanup(db.close)
        with patch('bulk_expansion_images.accepted_reference', return_value=source):
            planned = generation_input(run, db, record, {'review_identity': 'identity'})
        self.assertEqual(planned['reference'], source)
        self.assertEqual(planned['attempt'], 2)
        validate_prompt(planned['prompt'])
        return planned['prompt']

    def test_furniture_prompt_does_not_invent_hardware_or_fabric(self):
        prompt = self.plan().lower()
        for phrase in ('hanging chain', 'ring in full view', 'fabric texture', 'seams'):
            self.assertNotIn(phrase, prompt)

    def test_source_variant_retry_does_not_describe_clean_source_as_defective(self):
        self.assertNotIn('Correct this candidate image', self.plan())

    def test_oak_finish_is_not_opaque_paint(self):
        prompt = self.plan()
        self.assertNotIn('opaque painted Oak', prompt)
        self.assertIn('Oak', prompt)

    def test_white_variant_keeps_the_source_background(self):
        prompt = self.plan('White', 'Metal', 'pending')
        self.assertNotIn('neutral gray backdrop', prompt)

    def test_upholstery_recolor_preserves_the_exposed_frame_and_feet(self):
        prompt = self.plan('White', 'Velvet', subject='upholstered armchair')
        self.assertIn('only the upholstered surfaces', prompt)
        self.assertIn('original colors and materials', prompt)
        self.assertNotIn('only the upholstered surfaces', self.plan('White', 'Solid Wood'))
        self.assertNotIn('only the upholstered surfaces', self.plan('White', 'Velvet', subject='curtain panel'))
        self.assertIn('only the upholstered surfaces', self.plan('White', '', subject='tufted fabric ottoman'))


if __name__ == '__main__':
    unittest.main()
