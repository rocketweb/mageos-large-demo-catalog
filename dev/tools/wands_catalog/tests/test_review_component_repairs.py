from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from review_component_repairs import classify_events


class RepairEventsTest(unittest.TestCase):
    def test_interruption_is_retained_not_converted_to_success(self):
        states=classify_events([{'trial_id':'a'},{'trial_id':'b'},{'trial_id':'c'}],
            [{'trial_id':'a','status':'attempt_started'},{'trial_id':'a','status':'generated'},
             {'trial_id':'b','status':'attempt_started'}])
        self.assertEqual(states,{'a':'generated','b':'attempt_started','c':'unattempted'})
        for events in ([{'trial_id':'a','status':'generated'}],
                       [{'trial_id':'a','status':'attempt_started'}]*2,
                       [{'trial_id':'unknown','status':'attempt_started'}]):
            with self.assertRaises(ValueError):classify_events([{'trial_id':'a'}],events)


if __name__=='__main__':unittest.main()
