import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from profile_admission import admitted_profiles, profile_key

class AdmissionTest(unittest.TestCase):
 def test_every_profile_pilot_requires_current_direct_and_automated_acceptance(self):
  rows=[{'job_id':str(i),'request':json.dumps({'lane':'expanded-categories','profile':'bench'}),'image_sha256':str(i)} for i in range(2)]
  class DB:
   def execute(self,*args):return rows
  with tempfile.TemporaryDirectory() as d:
   receipt=Path(d)/'review.json';items=[{'job_id':r['job_id'],'image_sha256':r['image_sha256'],'decision':'no_blocking_defect_seen','observations':'Directly inspected'} for r in rows]
   receipt.write_text(json.dumps({'images':items}))
   with patch('bulk_expansion_images.current_job_accepted',return_value=True):
    self.assertEqual(admitted_profiles(DB(),{'review_identity':'id'},receipt),{('expanded-categories','bench')})
    items[1]['image_sha256']='stale';receipt.write_text(json.dumps({'images':items}))
    self.assertEqual(admitted_profiles(DB(),{'review_identity':'id'},receipt),set())
    items[1]['image_sha256']='1';items[1]['decision']='repair_required';receipt.write_text(json.dumps({'images':items}))
    self.assertEqual(admitted_profiles(DB(),{'review_identity':'id'},receipt),set())
    receipt.write_text(json.dumps({'images':items[:1]}))
    self.assertEqual(admitted_profiles(DB(),{'review_identity':'id'},receipt),set())
   receipt.write_text(json.dumps({'images':[dict(x,decision='no_blocking_defect_seen') for x in items]}))
   with patch('bulk_expansion_images.current_job_accepted',return_value=False):
    self.assertEqual(admitted_profiles(DB(),{'review_identity':'id'},receipt),set())
 def test_legacy_and_unknown_lanes_never_admitted(self):
  self.assertIsNone(profile_key({'lane':'existing-family-variants','profile':'bench'}))
  self.assertIsNone(profile_key({'lane':'unknown','profile':'bench'}))
