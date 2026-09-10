from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from completion_readiness import consolidate, merge_pins
from test_build_component_readiness import observation
from test_run_catalog_component_pilot import runtime_case


class CompletionReadinessTest(unittest.TestCase):
    def test_all_remaining_components_are_reviewed_without_losing_prior_history(self):
        a = runtime_case(); b = runtime_case('floor-lamp'); c = runtime_case('third')
        base = [observation(a, 'pass'), observation(b, 'uncertain')]
        new = [observation(b, 'fail'), observation(c, 'pass')]
        assets, families, counts = consolidate([x['brief'] for x in (a, b, c)], base, new)
        self.assertEqual(counts['reviewed_attempts'], 4)
        self.assertEqual(counts['initial_visual_pass'], 2)
        self.assertEqual(counts['uncertain'], 1)
        self.assertEqual(counts['unattempted'], 0)
        self.assertFalse(any(f['assembly_ready'] for f in families))
        self.assertEqual(sum(len(a['history']) for a in assets), 4)

    def test_duplicate_missing_and_already_passed_components_rejected(self):
        a = runtime_case(); b = runtime_case('floor-lamp')
        base = [observation(a, 'pass')]
        for new in ([], [observation(b, 'pass')] * 2, [observation(a, 'pass')]):
            with self.assertRaises(ValueError): consolidate([a['brief'], b['brief']], base, new)

    def test_pin_conflicts_fail_before_overwriting_evidence(self):
        pins = {'file': 'old'}
        with self.assertRaises(ValueError): merge_pins(pins, {'file': 'new'})
        self.assertEqual(pins, {'file': 'old'})


if __name__ == '__main__': unittest.main()
