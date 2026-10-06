import copy
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from image_review import Reviewer
import component_review

class LightingReviewTest(unittest.TestCase):
    def test_positive_general_review_cannot_accept_two_lights_for_a_three_light_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'image.jpg';p.write_bytes(b'pixels')
            ocr=MagicMock();ocr.inspect.return_value={'status':'ok','observations':[]}
            vision={'acceptable':True,'verdict':'pass','issues':[],'confidence':.99}
            count={'emitting_lights':2,'confidence':.99,'evidence':'Two bulbs; center tube is structural.'}
            with patch('image_review.api_key',return_value='private'),patch('image_review.OCR',return_value=ocr):r=Reviewer('model','ocr')
            with patch('image_review.request_vision',side_effect=lambda payload,key,parser=None:(copy.deepcopy(count if parser else vision),[])):
                q=r.inspect(p,{'subject':'Lyra 3 Lights Chandelier','product_class':'Chandeliers'})
            self.assertEqual(q['decision'],'rejected')
            self.assertTrue(q['vision']['acceptable'])
            self.assertEqual(q['lighting_review']['expected'],3)
            self.assertEqual(q['lighting_review']['emitting_lights'],2)

    def test_light_count_evidence_is_checked_when_present_without_invalidating_legacy_reviews(self):
        design={'subject':'Lyra 3 Lights Chandelier','product_class':'Chandeliers'}
        q={'model':'model','component_review':None,'table_component_review':None}
        self.assertTrue(component_review.accepted(q,design))
        q['lighting_review']={'identity':'stale','expected':3,'emitting_lights':2,'confidence':.99}
        self.assertFalse(component_review.accepted(q,design))
