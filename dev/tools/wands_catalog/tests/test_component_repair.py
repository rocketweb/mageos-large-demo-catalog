import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from component_repair import plan
from test_run_catalog_component_pilot import brief


class RepairTest(unittest.TestCase):
    def test_repair_preserves_definition_and_does_not_force_top_view_upright(self):
        b = brief(); s = {'root_sku': b['root_sku'], 'component_id': b['component_id'], 'canvas': [768,768], 'instruction': 'One wide object, directly overhead.'}
        a = {'asset_requirement_id': b['asset_requirement_id'], 'status': 'failed'}
        c = plan([b], [a], [s], 'repair-v1')[0]
        self.assertEqual(c['source_case']['brief'], b)
        self.assertNotIn('upright', c['source_case']['runtime_prompt'])
        self.assertFalse(c['publication_approved']); self.assertEqual(c['max_attempts'], 1)
        for bad in ([s,s], []):
            with self.assertRaises(ValueError): plan([b], [a], bad, 'repair-v1')
        a['status'] = 'initial_visual_pass'
        with self.assertRaises(ValueError): plan([b], [a], [s], 'repair-v1')


if __name__ == '__main__': unittest.main()
