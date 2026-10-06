import sys,json,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from media_tail_reconciliation import completed_media
from prepare_catalog import sha256
class MediaTailTest(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.r=Path(self.t.name);self.p=self.r/'plan';self.p.mkdir();self.e=self.r/'receipts';self.e.mkdir()
        names=['0001-new-simple.csv','0002-media.csv','0003-media.csv']
        for n in names:(self.p/n).write_text('sku\nSKU\n')
        plan={'actions':[{'action':'native-import','file':n,'rows':1} for n in names],'files':{n:sha256(self.p/n) for n in names}};(self.p/'deployment.json').write_text(json.dumps(plan));self.pin=sha256(self.p/'deployment.json')
        for i in range(4):(self.e/f'{i:04d}-completed.json').write_text(json.dumps({'exit_code':0,'plan_sha256':self.pin,'action':{'kind':'import' if i%2 else 'validate'}}))
        (self.e/'state.json').write_text(json.dumps({'state':'failed; reconcile partial state before retry','index':4,'plan_sha256':self.pin}))
    def test_only_completed_media_is_skipped(self):
        count,pins=completed_media(self.p,self.e);self.assertEqual(count,1);self.assertIn(str(self.p/'0003-media.csv'),pins)
    def test_changed_prior_inputs_are_rejected(self):
        (self.p/'0002-media.csv').write_text('changed')
        with self.assertRaisesRegex(ValueError,'inputs changed'):completed_media(self.p,self.e)
    def test_partial_failed_import_cannot_be_blindly_skipped(self):
        s=json.loads((self.e/'state.json').read_text());s['index']=5;(self.e/'state.json').write_text(json.dumps(s))
        with self.assertRaisesRegex(ValueError,'validation evidence'):completed_media(self.p,self.e)
    def test_reconciled_deadlock_replays_the_uncertain_media_batch(self):
        s=json.loads((self.e/'state.json').read_text());s['index']=5;s['exit_code']=1;(self.e/'state.json').write_text(json.dumps(s))
        (self.e/'0004-completed.json').write_text(json.dumps({'exit_code':0,'plan_sha256':self.pin,'action':{'kind':'validate'}}))
        (self.e/'0005-import.log').write_text('SQLSTATE[40001]: Serialization failure: 1213 Deadlock found when trying to get lock')
        count,pins=completed_media(self.p,self.e,reconcile_import_deadlock=True)
        self.assertEqual(count,1)
        self.assertIn(str(self.e/'0005-import.log'),pins)
    def test_other_failed_import_is_never_replayed(self):
        s=json.loads((self.e/'state.json').read_text());s['index']=5;s['exit_code']=1;(self.e/'state.json').write_text(json.dumps(s))
        (self.e/'0005-import.log').write_text('Invalid image')
        with self.assertRaisesRegex(ValueError,'deadlock evidence'):completed_media(self.p,self.e,reconcile_import_deadlock=True)
