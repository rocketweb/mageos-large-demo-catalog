import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from image_policy import product_prompt, visual_text, NO_MEASUREMENTS

class HyphenatedPromptMeasurementTest(unittest.TestCase):
    def test_hyphenated_sizes_are_removed_from_new_prompts_and_component_counts_survive(self):
        for size in ('16-In','24-inch','120-cm','16 - inches','24\u2011inch'):
            with self.subTest(size=size):
                prompt=product_prompt(f'Lyra {size} chandelier with 3 lights and 4 drawers')
                self.assertNotIn(size,prompt)
                self.assertIn('3 lights',prompt);self.assertIn('4 drawers',prompt)
                self.assertIn(NO_MEASUREMENTS,prompt)

    def test_frozen_catalog_brief_normalization_does_not_change(self):
        self.assertEqual(visual_text('Lyra 16-In Integrated Led Chandelier - 3 Lights'),
                         'Lyra 16-In Integrated Led Chandelier - 3 Lights')
