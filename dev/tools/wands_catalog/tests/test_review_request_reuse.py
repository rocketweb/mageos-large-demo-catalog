"""Shared pixels may reuse unprimed counts, never a different product check."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from image_review import Reviewer, SCHEMA
from build_expanded_catalog import digest
from prepare_catalog import sha256


class ReviewRequestReuseTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'candidate.jpg'
        self.path.write_bytes(b'candidate-pixels')
        self.ocr = MagicMock()
        self.ocr.inspect.return_value = {'status': 'ok', 'observations': []}
        with patch('image_review.api_key', return_value='private'), patch('image_review.OCR', return_value=self.ocr):
            self.reviewer = Reviewer('model', '/ocr')
        self.design = {'subject': 'cart', 'construction': 'two open shelves', 'color': 'Blue',
                       'material': 'Metal', 'product_class': 'Work carts', 'profile': 'work-cart'}
        self.vision = {'verdict': 'pass', 'acceptable': True, 'confidence': .98, 'issues': [],
                       'geometry_defects': False, 'visible_text': False, 'visible_measurements': False,
                       'product_matches': True, 'piece_count_matches': True, 'observed_product': 'Cart.'}
        self.counts = {'shelf_levels': 2, 'drawer_fronts': None, 'cupboard_doors': None,
                       'confidence': .98, 'evidence': 'Two shelf levels.'}
    def response(self, payload, key, parser=None):
        return copy.deepcopy(self.counts if parser else self.vision), [{'attempt': 1}]

    def test_different_briefs_share_only_identical_ocr_and_unprimed_counts(self):
        with patch('image_review.request_vision', side_effect=self.response) as calls:
            first = self.reviewer.inspect(self.path, self.design)
            second = self.reviewer.inspect(self.path, {**self.design, 'color': 'Red'})
            self.assertEqual(calls.call_count, 3)
            self.assertEqual(self.ocr.inspect.call_count, 1)
            self.assertEqual(second['component_review']['evidence'], first['component_review']['evidence'])
            self.assertEqual(second['request_reuse']['stages'], ['ocr', 'components'])
            self.assertNotIn('exact_input_review_reuse', second)
            self.assertEqual(second['design_sha256'], digest({**self.design, 'color': 'Red'}))

    def test_reused_observation_is_rebound_to_new_requirement_and_can_reject(self):
        with patch('image_review.request_vision', side_effect=self.response) as calls:
            self.reviewer.inspect(self.path, self.design)
            wrong = self.reviewer.inspect(self.path, {**self.design, 'construction': 'three open shelves'})
            self.assertEqual(calls.call_count, 3)
            self.assertEqual(wrong['component_review']['expected'], {'shelf_levels': 3})
            self.assertEqual(wrong['component_review']['shelf_levels'], 2)
            self.assertEqual(wrong['decision'], 'rejected')

    def test_scope_pixels_and_policy_changes_invalidate_relevant_requests(self):
        with patch('image_review.request_vision', side_effect=self.response) as calls:
            self.reviewer.inspect(self.path, self.design)
            scoped = self.reviewer.inspect(self.path, {**self.design, 'profile': 'desktop-shelf'})
            self.assertEqual(calls.call_count, 3)
            self.assertNotIn('components', scoped['request_reuse']['stages'])
            self.path.write_bytes(b'changed-pixels')
            self.reviewer.inspect(self.path, {**self.design, 'profile': 'desktop-shelf'})
            self.assertEqual(calls.call_count, 5)
            self.assertEqual(self.ocr.inspect.call_count, 2)
            with patch.dict(SCHEMA, {'description': 'Changed policy'}):
                self.reviewer.inspect(self.path, {**self.design, 'profile': 'desktop-shelf', 'color': 'Green'})
            self.assertEqual(calls.call_count, 6)

    def test_source_changes_require_new_general_check_and_caller_cannot_poison_count_cache(self):
        reference = Path(self.directory.name) / 'source.jpg'
        reference.write_bytes(b'source-one')
        with patch('image_review.request_vision', side_effect=self.response) as calls:
            first = self.reviewer.inspect(self.path, self.design, reference)
            first['component_review']['shelf_levels'] = 99
            reference.write_bytes(b'source-two')
            second = self.reviewer.inspect(self.path, self.design, reference)
            self.assertEqual(calls.call_count, 3)
            self.assertEqual(second['component_review']['shelf_levels'], 2)
            self.assertNotIn('general', second['request_reuse']['stages'])

    def test_visible_text_and_failed_requests_are_never_bypassed(self):
        self.ocr.inspect.return_value = {'status': 'ok', 'observations': [{'text': '12 cm', 'confidence': .99}]}
        with patch('image_review.request_vision', side_effect=self.response):
            self.reviewer.inspect(self.path, self.design)
            result = self.reviewer.inspect(self.path, {**self.design, 'color': 'Red'})
            self.assertNotEqual(result['decision'], 'accepted')
            self.assertEqual(result['ocr_flags'][0]['text'], '12 cm')
        with patch('image_review.request_vision', side_effect=ValueError('Unavailable')) as calls:
            for _ in range(2):
                with self.assertRaises(ValueError):
                    self.reviewer.inspect(self.path, {**self.design, 'color': 'Black'})
            self.assertEqual(calls.call_count, 2)

    def test_synthetic_name_context_changes_requests_without_losing_visible_features(self):
        from image_review import SYNTHETIC_CONTEXT
        self.reviewer.synthetic_names=False
        design={**self.design,'subject':'All-Clad 2 Shelf Organizer'}
        with patch('image_review.request_vision',side_effect=self.response) as calls:
            self.reviewer.inspect(self.path,design)
            self.reviewer.synthetic_names=True
            result=self.reviewer.inspect(self.path,design)
        general=[c.args[0] for c in calls.call_args_list if not c.kwargs.get('parser') and len(c.args)==2]
        self.assertEqual(len(general),2,'A changed review context must invalidate general evidence reuse')
        payload=json.loads(general[-1]['messages'][1]['content'][0]['text'])
        self.assertEqual(payload['intended_product']['subject'],design['subject'])
        self.assertEqual(payload['synthetic_illustration_context'],SYNTHETIC_CONTEXT)
        self.assertEqual(result['synthetic_illustration_context']['directives'],SYNTHETIC_CONTEXT)
        self.assertEqual(result['image_sha256'],sha256(self.path))

    def test_complete_table_count_reuse_still_rejects_the_wrong_sale_unit(self):
        design = {'subject': '2-piece coffee table set', 'product_class': 'Living Room Table Sets', 'color': 'Black'}
        observed = {'complete_tables': 2, 'confidence': .98, 'evidence': 'Two complete tables.'}
        def respond(payload, key, parser=None):
            return copy.deepcopy(observed if parser else self.vision), [{'attempt': 1}]
        with patch('image_review.request_vision', side_effect=respond) as calls:
            first = self.reviewer.inspect(self.path, design)
            wrong = self.reviewer.inspect(self.path, {**design, 'subject': '3-piece coffee table set'})
            self.assertEqual(calls.call_count, 3)
            self.assertEqual(first['decision'], 'accepted')
            self.assertEqual(wrong['table_component_review']['expected'], 3)
            self.assertEqual(wrong['table_component_review']['complete_tables'], 2)
            self.assertEqual(wrong['decision'], 'rejected')
            self.assertEqual(wrong['request_reuse']['stages'], ['ocr', 'tables'])

    def test_pixels_changing_during_ocr_fail_without_poisoning_the_cache(self):
        def mutate(_):
            self.path.write_bytes(b'changed-during-ocr')
            return {'status': 'ok', 'observations': []}
        self.ocr.inspect.side_effect = mutate
        with patch('image_review.request_vision', side_effect=self.response) as calls:
            with self.assertRaisesRegex(ValueError, 'changed during OCR'):
                self.reviewer.inspect(self.path, self.design)
            calls.assert_not_called()
            self.path.write_bytes(b'candidate-pixels')
            self.ocr.inspect.side_effect = None
            self.reviewer.inspect(self.path, self.design)
            self.assertEqual(self.ocr.inspect.call_count, 2)
