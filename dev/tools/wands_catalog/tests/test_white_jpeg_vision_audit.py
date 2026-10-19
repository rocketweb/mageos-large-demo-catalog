import csv
import contextlib
import hashlib
import json
import io
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import white_jpeg_audit as audit
import white_jpeg_audit_run as runner
from white_jpeg_vision_audit import apply_review
from white_jpeg_monitor import check_audit


class ProductReviewTest(unittest.TestCase):
    def test_read_only_ssh_check_retries_a_transient_connection_timeout(self):
        failed=subprocess.CompletedProcess([],255,stdout='',stderr='ssh: connect to host 192.168.1.115 port 22: Operation timed out')
        good=subprocess.CompletedProcess([],0,stdout='{"state":"running"}',stderr='')
        with patch.object(runner.subprocess,'run',side_effect=[failed,good]) as command,patch.object(runner.time,'sleep'):
            result=runner.remote(['status'],retries=3)
        self.assertEqual(result.stdout,'{"state":"running"}')
        self.assertEqual(command.call_count,2)

    def monitor_fixture(self,root,updated_at):
        folder=root/'audit';folder.mkdir()
        state={'phase':'reviewing_product_cutouts','updated_at':updated_at,'pid':os.getpid(),
               'metrics_complete':10,'total':10,'classified':3,'decisions':{'original':8,'white':2},'error':None}
        (folder/'status.json').write_text(json.dumps(state))
        return folder

    def test_monitor_rearms_alert_after_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();audit_dir=self.monitor_fixture(root,time.time())
            marker=audit_dir/'notification-state.json';marker.write_text(json.dumps({'alert':'needs_attention'}))
            with contextlib.redirect_stdout(io.StringIO()):
                result=check_audit(root,{'audit_path':str(audit_dir)},do_notify=False)
            self.assertEqual(result['issues'],[])
            self.assertIsNone(json.loads(marker.read_text())['alert'])

    def test_monitor_reports_stale_audit_even_if_pid_is_alive(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();audit_dir=self.monitor_fixture(root,time.time()-601)
            with contextlib.redirect_stdout(io.StringIO()):
                result=check_audit(root,{'audit_path':str(audit_dir)},do_notify=False)
            self.assertIn('Audit progress has not updated for 10 minutes',result['issues'])

    def test_verified_mini_handoff_needs_no_more_ssh(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();audit_dir=self.monitor_fixture(root,time.time())
            (audit_dir/'mini-config.json').write_text(json.dumps({'manifest_sha256':'pinned',
                'remote_python':'python','remote_worker':'worker','remote_job':'job','target':'mini'}))
            (audit_dir/'mini-imported.json').write_text(json.dumps({'state':'complete','manifest_sha256':'pinned'}))
            (audit_dir/'mini-status.json').write_text(json.dumps({'state':'complete','manifest_sha256':'pinned','done':430,'total':430}))
            with patch('white_jpeg_monitor.subprocess.run',side_effect=AssertionError('Completed handoff must be local')),contextlib.redirect_stdout(io.StringIO()):
                result=check_audit(root,{'audit_path':str(audit_dir)},do_notify=False)
            self.assertEqual(result['issues'],[])

    def test_vision_cannot_promote_a_scene_or_uncertain_original(self):
        with tempfile.TemporaryDirectory() as folder:
            db=audit.connect(Path(folder))
            db.execute('CREATE TABLE product_reviews(file TEXT,source_sha256 TEXT,output_sha256 TEXT,accepted INTEGER,reviewed_at REAL,details TEXT)')
            row={'file':'scene.jpg','source_sha256':'original','output_sha256':'candidate'}
            db.execute("INSERT INTO images(n,file,row_json,decision,reason) VALUES(1,?,?,'original','non_solid_or_scene_background')",(row['file'],json.dumps(row)))
            db.commit()
            with self.assertRaisesRegex(ValueError,'cannot promote'):
                apply_review(db,row,True,{'fake_model_approval':True})
            self.assertEqual(db.execute('SELECT decision FROM images').fetchone()[0],'original')
            self.assertEqual(db.execute('SELECT count(*) FROM product_reviews').fetchone()[0],0)
            db.close()

    def test_uncertain_product_review_retains_original(self):
        with tempfile.TemporaryDirectory() as folder:
            db=audit.connect(Path(folder))
            db.execute('CREATE TABLE product_reviews(file TEXT,source_sha256 TEXT,output_sha256 TEXT,accepted INTEGER,reviewed_at REAL,details TEXT)')
            row={'file':'product.jpg','source_sha256':'original','output_sha256':'candidate'}
            db.execute("INSERT INTO images(n,file,row_json,decision) VALUES(1,?,?,'white')",(row['file'],json.dumps(row)))
            db.commit();apply_review(db,row,False,{'reason':'uncertain pale frame'})
            self.assertEqual(db.execute('SELECT decision FROM images').fetchone()[0],'original')
            self.assertEqual(db.execute('SELECT accepted FROM product_reviews').fetchone()[0],0)
            db.close()

    def test_mini_import_is_atomic_if_a_later_source_identity_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);job=root/'job';audit_dir=root/'audit';originals=root/'originals'
            job.mkdir();audit_dir.mkdir();originals.mkdir()
            (job/'manifest.json').write_text(json.dumps({'originals':str(originals)}))
            destination=audit_dir/'finished-mini';media=destination/'media/wands-expanded';media.mkdir(parents=True)
            packet=audit_dir/'mini-packet';packet.mkdir()
            db=audit.connect(audit_dir);mapping=[];manifest=[]
            for i in (1,2):
                source=Image.new('RGB',(256,256),(244,237,222));draw=ImageDraw.Draw(source)
                draw.rectangle((65,50,190,200),fill=(40+i,80,140));temp=root/'source.jpg';source.save(temp,quality=90)
                source_hash=hashlib.sha256(temp.read_bytes()).hexdigest();file=source_hash+'.jpg';temp.replace(originals/file)
                candidate=Image.new('RGB',(256,256),'white');ImageDraw.Draw(candidate).rectangle((65,50,190,200),fill=(40+i,80,140))
                temp=root/'candidate.jpg';candidate.save(temp,quality=90);out_hash=hashlib.sha256(temp.read_bytes()).hexdigest();out=out_hash+'.jpg';temp.replace(media/out)
                row={'n':i,'file':file,'source_sha256':source_hash,'source_bytes':(originals/file).stat().st_size,'state':'pending','output_file':None}
                db.execute("INSERT INTO images(n,file,row_json,metrics,scores,decision) VALUES(?,?,?,?,?,'eligible')",(i,file,json.dumps(row),'{}',json.dumps([7,9,1,1,0,1,1])))
                manifest.append({'n':i,'file':file,'sha256':source_hash})
                mapping.append({'original_file':file,'original_sha256':source_hash if i==1 else 'wrong identity',
                                'state':'done','output_file':out,'output_sha256':out_hash,'output_bytes':(media/out).stat().st_size,'warning':''})
            db.commit()
            (packet/'manifest.json').write_text(json.dumps({'images':manifest}))
            with (destination/'mapping.csv').open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(mapping[0]));writer.writeheader();writer.writerows(mapping)
            with patch.object(runner,'sync'):
                with self.assertRaisesRegex(ValueError,'identity changed'):
                    runner.import_finished(job,audit_dir)
            # A later invalid row must not commit an earlier conversion.
            self.assertEqual(db.execute("SELECT count(*) FROM images WHERE decision='eligible'").fetchone()[0],2)
            self.assertTrue(all(json.loads(r[0])['output_file'] is None for r in db.execute('SELECT row_json FROM images')))
            db.close()


if __name__=='__main__':unittest.main()
