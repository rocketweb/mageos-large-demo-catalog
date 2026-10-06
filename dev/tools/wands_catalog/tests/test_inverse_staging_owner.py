import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from finish_expansion_project import Destination,REMOTE
class InverseOwnerTest(unittest.TestCase):
 def test_private_inverse_is_readable_by_remote_restore_service(self):
  with tempfile.TemporaryDirectory() as d:
   t=Destination(REMOTE,Path(d),'fixture')
   inverse=Path(d)/'catalog-inverse.jsonl.gz';side=Path(d)/'catalog-inverse.jsonl.gz.json'
   with patch.object(t,'sync') as sync,patch.object(t,'command') as command:
    t.stage_inverse(inverse,side)
    self.assertEqual(sync.call_count,2)
    command.assert_called_once_with(['chown','33:33',t.stage/inverse.name,t.stage/side.name])
