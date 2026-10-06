import io
import json
from pathlib import Path
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import image_review
from image_review import request_vision


class VisionTransportTest(unittest.TestCase):
    @mock.patch('image_review.time.sleep')
    def test_connection_outage_is_distinct_from_invalid_review(self,sleep):
        with mock.patch('image_review.urllib.request.urlopen',side_effect=urllib.error.URLError(ConnectionRefusedError(61,'refused'))):
            with self.assertRaises(image_review.ReviewUnavailable) as caught:
                request_vision({'model':'local-test'},'test-only')
        self.assertEqual(type(caught.exception).__name__,'ReviewServiceUnavailable')
        self.assertTrue(all(a.get('service_unavailable') for a in caught.exception.attempts))
        self.assertEqual(caught.exception.attempts[0]['errno'],61)

    @mock.patch('image_review.time.sleep')
    def test_bad_credentials_are_not_treated_as_temporary_outage(self,sleep):
        with mock.patch('image_review.urllib.request.urlopen',side_effect=urllib.error.HTTPError('http://local',401,'unauthorized',{},None)) as call:
            with self.assertRaises(urllib.error.HTTPError):
                request_vision({'model':'local-test'},'test-only')
        self.assertEqual(call.call_count,1)

    @mock.patch('image_review.time.sleep')
    def test_busy_service_waits_but_mixed_invalid_output_keeps_bounded_budget(self,sleep):
        busy=urllib.error.HTTPError('http://local',503,'unavailable',{},None)
        with mock.patch('image_review.urllib.request.urlopen',side_effect=busy):
            with self.assertRaises(image_review.ReviewServiceUnavailable):
                request_vision({'model':'local-test'},'test-only')
        with mock.patch('image_review.urllib.request.urlopen',side_effect=[busy,self.response(finish='length'),busy]):
            with self.assertRaises(image_review.ReviewUnavailable) as caught:
                request_vision({'model':'local-test'},'test-only')
        self.assertEqual(type(caught.exception).__name__,'ReviewUnavailable')

    def response(self,verdict='pass',finish='stop'):
        value={'verdict':verdict,'confidence':.99,'visible_measurements':verdict=='fail',
               'visible_text':False,'geometry_defects':False,'product_matches':True,
               'piece_count_matches':True,'observed_product':'One coherent unmarked table.',
               'issues':['Visible measurement'] if verdict=='fail' else []}
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':finish,
                         'message':{'content':json.dumps(value)}}]}).encode())

    @mock.patch('image_review.time.sleep')
    def test_incomplete_output_retries_with_room_to_complete(self,sleep):
        with mock.patch('image_review.urllib.request.urlopen',side_effect=[self.response(finish='length'),self.response()]) as call:
            verdict,attempts=request_vision({'model':'local-test'},'test-only')
        self.assertTrue(verdict['acceptable']);self.assertEqual(call.call_count,2)
        self.assertEqual(json.loads(call.call_args_list[1].args[0].data)['max_tokens'],1800)
        self.assertEqual(attempts[0]['finish_reason'],'length')

    def test_complete_failure_is_never_retried_for_a_better_score(self):
        with mock.patch('image_review.urllib.request.urlopen',return_value=self.response(verdict='fail')) as call:
            verdict,_=request_vision({'model':'local-test'},'test-only')
        self.assertFalse(verdict['acceptable']);self.assertEqual(call.call_count,1)

    @mock.patch('image_review.time.sleep')
    def test_three_incomplete_responses_remain_unaccepted(self,sleep):
        with mock.patch('image_review.urllib.request.urlopen',side_effect=[self.response(finish='length') for _ in range(3)]) as call:
            with self.assertRaises(ValueError) as error:request_vision({'model':'local-test'},'test-only')
        self.assertEqual(call.call_count,3)
        self.assertEqual(len(error.exception.attempts),3)
        self.assertTrue(all(a['finish_reason']=='length' for a in error.exception.attempts))
        self.assertEqual(type(error.exception).__name__,'ReviewUnavailable')


if __name__=='__main__':unittest.main()
