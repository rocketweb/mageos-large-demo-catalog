import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bulk_expansion_images import connect,accepted_reference
from export_expanded_catalog import accepted_retained
from prepare_catalog import sha256

class ReferenceHoldTest(unittest.TestCase):
 def test_direct_rejection_blocks_generation_and_export_despite_vision_pass(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);db=connect(root);image=root/'image.jpg';image.write_bytes(b'image');pin=sha256(image)
   db.executescript('CREATE TABLE references_to_review(image_sha256,design_sha256,path,design,review); CREATE TABLE job_references(job_id,image_sha256,design_sha256); CREATE TABLE IF NOT EXISTS manual_reference_reviews(image_sha256 PRIMARY KEY,observations);')
   db.execute('INSERT INTO references_to_review VALUES(?,?,?,?,?)',('original','design',str(image),'{}',json.dumps({'decision':'rejected'})))
   db.execute('INSERT INTO job_references VALUES(?,?,?)',('job','original','design'))
   db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,?)',('original','design',1,str(image),pin,json.dumps({'decision':'accepted','review_identity':'policy','design_sha256':'design','image_sha256':pin})))
   self.assertEqual(accepted_reference(db,{'job_id':'job','reference':{'sku':'test'}},'policy'),image)
   db.execute('INSERT INTO manual_reference_reviews VALUES(?,?)',(pin,'Nine handles but only five drawer fronts'))
   self.assertFalse(accepted_reference(db,{'job_id':'job','reference':{'sku':'test'}},'policy'))
   # The original must be intact for the export assertion.
   db.execute('UPDATE references_to_review SET image_sha256=?',(pin,))
   db.execute('UPDATE reference_repairs SET original_sha256=?',(pin,))
   row=db.execute('SELECT * FROM references_to_review').fetchone()
   self.assertIsNone(accepted_retained(db,row,'policy'));db.close()
