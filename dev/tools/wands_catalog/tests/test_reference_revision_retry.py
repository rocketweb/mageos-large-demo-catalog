from pathlib import Path
import json,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bulk_expansion_images import retry_allowed
from prepare_catalog import sha256

class RevisionRetryTest(unittest.TestCase):
 def test_new_accepted_source_gets_bounded_budget_without_erasing_attempts(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.jpg';source.write_bytes(b'new source');directory=root/'candidates'/'job';directory.mkdir(parents=True)
   job={'job_id':'job','reference':{'sku':'source'}};row={'attempts':3}
   for i in range(1,4):(directory/f'attempt-{i:02d}.json').write_text(json.dumps({'reference_sha256':'old'}))
   self.assertTrue(retry_allowed(root,row,job,source))
   for i in range(4,7):(directory/f'attempt-{i:02d}.json').write_text(json.dumps({'reference_sha256':sha256(source)}))
   self.assertFalse(retry_allowed(root,{'attempts':6},job,source))
   self.assertFalse(retry_allowed(root,row,{**job,'reference':None},None))

class StaleVariantTest(unittest.TestCase):
 def test_unchanged_sources_do_not_scan_human_feedback_for_each_variant(self):
  import sqlite3
  from unittest.mock import patch
  from bulk_expansion_images import requeue_changed_sources
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.jpg';source.write_bytes(b'unchanged source')
   db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
   db.execute('CREATE TABLE jobs(job_id,state,image_path,request,review,updated,pilot)')
   for i in range(100):
    db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',(str(i),'accepted',str(root/'old.jpg'),json.dumps({'reference':{'job_id':'source'}}),json.dumps({'reference_sha256':sha256(source)}),0,1))
   with patch('bulk_expansion_images.accepted_reference',return_value=source),patch('human_keep_acceptance.is_kept') as kept:
    self.assertEqual(requeue_changed_sources(root,db,'identity',True),0)
   kept.assert_not_called();db.close()

 def test_live_unreconciled_keep_still_prevents_a_changed_source_requeue(self):
  import sqlite3
  from unittest.mock import patch
  from bulk_expansion_images import requeue_changed_sources
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.jpg';source.write_bytes(b'corrected source')
   db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
   db.execute('CREATE TABLE jobs(job_id,state,image_path,request,review,updated,pilot)')
   db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',('variant','accepted',str(root/'old.jpg'),json.dumps({'reference':{'job_id':'source'}}),json.dumps({'reference_sha256':'prior-source'}),0,1))
   with patch('bulk_expansion_images.accepted_reference',return_value=source),patch('human_keep_acceptance.is_kept',return_value=True) as kept:
    self.assertEqual(requeue_changed_sources(root,db,'identity',True),0)
   kept.assert_called_once();self.assertEqual(db.execute('SELECT state FROM jobs').fetchone()[0],'accepted');db.close()

 def test_changed_source_requeues_a_previously_accepted_variant(self):
  import sqlite3
  from unittest.mock import patch
  from bulk_expansion_images import requeue_changed_sources
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.jpg';source.write_bytes(b'corrected source')
   db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
   db.execute('CREATE TABLE jobs(job_id,state,image_path,request,review,updated,pilot)')
   db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',('variant','accepted',str(root/'old.jpg'),json.dumps({'reference':{'job_id':'source'}}),json.dumps({'reference_sha256':'prior-source'}),0,1))
   with patch('bulk_expansion_images.accepted_reference',return_value=source):
    self.assertEqual(requeue_changed_sources(root,db,'identity',True),1)
   self.assertEqual(db.execute('SELECT state FROM jobs').fetchone()[0],'rejected')
   db.close()

 def test_disproved_source_queues_its_variant_for_repair_without_claiming_acceptance(self):
  import sqlite3
  from unittest.mock import patch
  from bulk_expansion_images import requeue_changed_sources
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
   db.execute('CREATE TABLE jobs(job_id,state,image_path,request,review,updated,pilot)')
   evidence=json.dumps({'reference_sha256':'disproved-source'})
   db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',('variant','accepted',str(root/'old.jpg'),json.dumps({'reference':{'job_id':'source'}}),evidence,0,0))
   with patch('bulk_expansion_images.accepted_reference',return_value=False),patch('human_keep_acceptance.is_kept',return_value=False):
    self.assertEqual(requeue_changed_sources(root,db,'identity'),1)
   row=db.execute('SELECT state,review FROM jobs').fetchone();self.assertEqual(row['state'],'rejected');self.assertEqual(row['review'],evidence)
   event=json.loads((root/'reference-revisions.jsonl').read_text())
   self.assertIsNone(event['current_reference_sha256']);self.assertEqual(event['previous_reference_sha256'],'disproved-source')
   db.close()

 def test_live_keep_survives_a_disproved_source(self):
  import sqlite3
  from unittest.mock import patch
  from bulk_expansion_images import requeue_changed_sources
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
   db.execute('CREATE TABLE jobs(job_id,state,image_path,request,review,updated,pilot)')
   db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',('variant','accepted',str(root/'old.jpg'),json.dumps({'reference':{'job_id':'source'}}),json.dumps({'reference_sha256':'disproved-source'}),0,0))
   with patch('bulk_expansion_images.accepted_reference',return_value=False),patch('human_keep_acceptance.is_kept',return_value=True):
    self.assertEqual(requeue_changed_sources(root,db,'identity'),0)
   self.assertEqual(db.execute('SELECT state FROM jobs').fetchone()[0],'accepted');db.close()
