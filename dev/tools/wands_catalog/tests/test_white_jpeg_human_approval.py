import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import white_jpeg_human_approval as human
import white_jpeg_category_run as catalog


class HumanApprovalTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=catalog.connect(self.root);self.addCleanup(self.db.close)
        self.db.executescript('CREATE TABLE images(file TEXT PRIMARY KEY,row_json TEXT,decision TEXT,reason TEXT);'
                             'CREATE TABLE glass_outline_checks(file TEXT PRIMARY KEY,verdict TEXT);')
        self.rows={};self.meta={};items=[]
        for n in range(1,5):
            src=self.root/f'{n}.jpg';out=self.root/f'{n}-white.jpg'
            src.write_bytes(f'original {n}'.encode());out.write_bytes(f'candidate {n}'.encode())
            row={'file':src.name,'source_sha256':human.sha(src),'output_sha256':human.sha(out),'output_file':out.name}
            self.rows[src.name]=row;self.meta[src.name]={'classes':['Tables'],'categories':['WANDS Catalog/Furniture/Tables']}
            self.db.execute('INSERT INTO images VALUES(?,?,NULL,?)',(src.name,json.dumps(row),'pending'))
            items.append({'id':f'F{1 if n<4 else 2:03d}-{n:02d}','batch':f'F{1 if n<4 else 2:03d}',**row,
                'original_path':str(src),'candidate_path':str(out),'name':f'Table {n}','skus':[f'SKU-{n}']})
        self.db.commit()
        self.manifest={'run_id':'fixture','items':items,'batches':[
            {'id':'F001','items':[i['id']for i in items[:3]]},{'id':'F002','items':[items[3]['id']]}]}
        self.path=self.root/'manifest.json';self.path.write_text(json.dumps(self.manifest))
        self.scope={'run_id':'fixture','manifest_sha256':human.sha(self.path),'deploy':False,
                    'approved_batches_with_exceptions':{'F001':['F001-02']}}
        self.plan=human.make_plan(self.path,human.sha(self.path),self.scope)

    def apply(self):
        return human.apply(self.db,self.plan,self.meta)

    def test_exact_scope_exception_idempotence_and_guarded_inverse(self):
        receipt=self.apply()
        self.assertEqual(human.verify(self.db,self.plan),{'white':2,'original':1})
        self.assertEqual(tuple(self.db.execute("SELECT decision,reason FROM images WHERE file='4.jpg'").fetchone()),(None,'pending'))
        self.assertTrue(self.apply()['idempotent'])
        human.rollback(self.db,self.plan,receipt['before'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM human_selections').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM images WHERE decision IS NULL').fetchone()[0],4)

    def test_controller_exports_valid_human_white_and_rejects_exception_or_changed_bytes(self):
        self.apply()
        catalog.validate_white(self.db,self.rows['1.jpg'],self.meta['1.jpg'],None)
        with self.assertRaisesRegex(ValueError,'exception'):
            catalog.validate_white(self.db,self.rows['2.jpg'],self.meta['2.jpg'],None)
        with self.assertRaisesRegex(ValueError,'different image bytes'):
            catalog.validate_white(self.db,{**self.rows['1.jpg'],'output_sha256':'wrong'},self.meta['1.jpg'],None)

    def test_late_automatic_reviews_cannot_overwrite_human_decisions_or_add_evidence(self):
        self.apply()
        catalog.save(self.db,self.rows['1.jpg'],'original','machine_reject','context_review')
        catalog.save(self.db,self.rows['2.jpg'],'white','machine_accept','fast')
        self.assertEqual(human.verify(self.db,self.plan),{'white':2,'original':1})
        self.assertEqual(self.db.execute('SELECT count(*) FROM category_evidence').fetchone()[0],0)

    def test_database_trigger_preserves_exceptions_even_with_an_old_worker(self):
        self.apply()
        self.db.execute("UPDATE images SET decision='white',reason='old_worker' WHERE file='2.jpg'")
        self.db.execute("UPDATE images SET decision='original',reason='old_worker' WHERE file='1.jpg'")
        self.db.commit()
        human.verify(self.db,self.plan)

    def test_bad_exception_and_manifest_hash_are_rejected_before_writes(self):
        with self.assertRaisesRegex(ValueError,'manifest hash'):
            human.make_plan(self.path,'wrong',self.scope)
        self.scope['approved_batches_with_exceptions']['F001'].append('F002-04')
        with self.assertRaisesRegex(ValueError,'Exception'):
            human.make_plan(self.path,human.sha(self.path),self.scope)

    def test_actual_candidate_drift_aborts_whole_approval(self):
        (self.root/'3-white.jpg').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'bytes changed'):
            self.apply()
        self.assertEqual(self.db.execute('SELECT count(*) FROM human_selections').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM images WHERE decision IS NULL').fetchone()[0],4)

    def test_glass_hold_and_room_bundle_cannot_be_overridden(self):
        self.db.execute("INSERT INTO glass_outline_checks VALUES('3.jpg','lost')");self.db.commit()
        with self.assertRaisesRegex(ValueError,'glass outline'):
            self.apply()
        self.assertEqual(self.db.execute('SELECT count(*) FROM human_selections').fetchone()[0],0)
        self.db.execute('DELETE FROM glass_outline_checks');self.db.commit()
        self.meta['3.jpg']['classes']=['Room Bundle']
        with self.assertRaisesRegex(ValueError,'Room Bundle'):
            self.apply()

    def test_later_glass_hold_and_byte_drift_fall_back_to_original(self):
        self.apply()
        self.db.execute("INSERT INTO glass_outline_checks VALUES('1.jpg','lost')")
        self.db.execute("UPDATE images SET decision='white' WHERE file='1.jpg'")
        self.db.commit()
        self.assertEqual(self.db.execute("SELECT decision FROM images WHERE file='1.jpg'").fetchone()[0],'original')
        with self.assertRaisesRegex(ValueError,'held glass'):
            human.validate_white(self.db,self.rows['1.jpg'],self.meta['1.jpg'])
        changed={**self.rows['3.jpg'],'output_sha256':'changed'}
        self.db.execute("UPDATE images SET row_json=? WHERE file='3.jpg'",(json.dumps(changed),));self.db.commit()
        self.assertEqual(self.db.execute("SELECT decision FROM images WHERE file='3.jpg'").fetchone()[0],'original')


if __name__=='__main__':unittest.main()
