import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import white_jpeg_calibrated_audit as checks
import white_jpeg_calibrated_run as run
from image_review import ReviewServiceUnavailable
from white_jpeg_worker import atomic_json,sha256


class CalibratedRunTest(unittest.TestCase):
    def row(self,n):
        return {'n':n,'file':f'source-{n}.jpg','source_sha256':f'source-{n}',
                'output_file':f'candidate-{n}.jpg','output_sha256':f'candidate-{n}'}

    def evidence(self,good):
        return ({'white_border':1,'backdrop_fit_p90':2,'border_edge_fraction':0,'risk_regions':[]},
                {'background':'studio','confidence':.99,'product_preserved':good,'white_background':True,'reason':'Observed product parts.'},
                {'model':checks.MODEL,'review_identity':checks.review_identity(checks.MODEL)})

    def populate(self,db,rows):
        with db:
            for row in rows:db.execute('INSERT INTO images(n,file,row_json) VALUES(?,?,?)',(row['n'],row['file'],json.dumps(row)))

    def test_outage_keeps_negative_reviews_and_resume_uses_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);db=checks.connect(p);rows=[self.row(1),self.row(2)];self.populate(db,rows)
            def outage(job,row,key,**kwargs):
                if row['n']==1:return self.evidence(False)
                raise ReviewServiceUnavailable([])
            with patch.object(run,'api_key',return_value='test-only'),patch.object(checks,'assess',side_effect=outage):
                with self.assertRaises(ReviewServiceUnavailable):run.review_rows(p,p,db,rows,'test',workers=2)
            self.assertEqual(db.execute('SELECT decision FROM images WHERE n=1').fetchone()[0],'original')
            with patch.object(run,'api_key',return_value='test-only'),patch.object(checks,'assess',return_value=self.evidence(True)) as assess:
                run.review_rows(p,p,db,rows,'test',workers=2)
            self.assertEqual(assess.call_count,1)
            self.assertEqual(assess.call_args.args[1]['n'],2)
            self.assertEqual(dict(db.execute('SELECT n,decision FROM images')),{1:'original',2:'white'})
            db.close()

    def test_changed_candidate_cannot_reuse_a_cached_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            db=checks.connect(Path(folder));row=self.row(1);self.populate(db,[row]);run.save_result(db,row,*self.evidence(True))
            self.assertIsNotNone(run.cached_result(db,row))
            with self.assertRaisesRegex(ValueError,'mismatch'):run.cached_result(db,{**row,'output_sha256':'changed'})
            db.close()

    def test_mini_import_recovers_after_committed_transaction_before_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);job=root/'job';audit=root/'audit';originals=root/'originals'
            for p in (job,audit,originals):p.mkdir()
            atomic_json(job/'manifest.json',{'originals':str(originals)})
            source=root/'source.jpg';Image.new('RGB',(32,32),(230,220,210)).save(source)
            sh=sha256(source);file=sh+'.jpg';source.rename(originals/file)
            media=audit/'finished-mini/media/wands-expanded';media.mkdir(parents=True)
            output=root/'output.jpg';Image.new('RGB',(32,32),'white').save(output)
            oh=sha256(output);out=oh+'.jpg';output.rename(media/out)
            row={'n':1,'file':file,'source_sha256':sh,'source_bytes':(originals/file).stat().st_size,'output_file':None}
            db=checks.connect(audit);self.populate(db,[row]);db.execute("UPDATE images SET decision='eligible'");db.commit()
            packet=audit/'mini-packet';packet.mkdir();atomic_json(packet/'manifest.json',{'images':[{'file':file}]})
            atomic_json(audit/'mini-config.json',{'manifest_sha256':'pinned'})
            mapping={'original_file':file,'original_sha256':sh,'state':'done','output_file':out,'output_sha256':oh,'output_bytes':(media/out).stat().st_size,'warning':''}
            with (media.parents[1]/'mapping.csv').open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(mapping));writer.writeheader();writer.writerow(mapping)
            with patch.object(run.export,'sync'),patch.object(run,'atomic_json',side_effect=OSError('interrupted receipt write')):
                with self.assertRaises(OSError):run.import_mini(job,audit,db)
            self.assertIsNone(db.execute('SELECT decision FROM images').fetchone()[0])
            self.assertIsNotNone(db.execute("SELECT value FROM meta WHERE key='calibrated_mini_import'").fetchone())
            with patch.object(run.export,'sync',side_effect=AssertionError('Must recover committed import locally')):run.import_mini(job,audit,db)
            self.assertEqual(json.loads((audit/'mini-imported.json').read_text())['count'],1)
            self.assertEqual(sha256(originals/file),sh);db.close()


class PilotRecoveryContractTest(unittest.TestCase):
    def evidence(self,folder,cal_good,hold_good,unsafe=False):
        ref=folder/'reference';ref.mkdir();atomic_json(ref/'expected-counts.json',{'calibration':315,'holdout':185})
        out=ref/'evaluations'/checks.decision_identity()[:16];out.mkdir(parents=True);atomic_json(out/'identity.json',checks.identity())
        for split,good,bad,recovered in [('calibration',282,33,cal_good),('holdout',179,6,hold_good)]:
            labels=[];results={}
            for i in range(good+bad):
                f=f'{split}-{i}.jpg';truth='white' if i<good else 'original';decision='white' if i<recovered else 'original'
                if unsafe and split=='calibration' and i==good:decision='white'
                labels.append({'file':f,'truth':truth});results[f]={'decision':decision}
            atomic_json(ref/(split+'.json'),labels);atomic_json(out/(split+'-results.json'),results)

    def test_recovery_is_counted_across_the_full_pilot_with_an_independent_floor(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);self.evidence(p,267,178);report=run.reference_report(p)
            self.assertTrue(report['passed'])
            self.assertEqual(report['overall']['good_recovered'],445)
            self.assertEqual(report['overall']['good'],461)
            self.assertFalse(report['splits']['calibration']['recovery_target_met'])

    def test_one_unsafe_control_fails_even_with_high_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);self.evidence(p,282,179,unsafe=True)
            self.assertFalse(run.reference_report(p)['passed'])

    def test_good_overall_recovery_cannot_hide_poor_independent_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);self.evidence(p,282,169);report=run.reference_report(p)
            self.assertTrue(report['overall']['recovery_target_met'])
            self.assertFalse(report['passed'])

class SourcePilotGateTest(unittest.TestCase):
    def test_changed_source_pilot_results_cannot_authorize_conversion(self):
        with tempfile.TemporaryDirectory() as folder:
            audit=Path(folder);pilot=audit/'source-only-pilot';pilot.mkdir()
            atomic_json(pilot/'qualified-results.json',{})
            atomic_json(pilot/'qualified-validation.json',{'passed':True,'checks_identity':checks.decision_identity(),
                'count':13,'studio_sources':8,'scene_controls':5,'qualified_results_sha256':'different-content'})
            with self.assertRaisesRegex(ValueError,'Source eligibility pilot'):
                run.validate_source_pilot(audit)

    def test_catalog_mapping_changed_during_a_long_audit_cannot_be_exported(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'4-media.csv';source.write_text('sku,base_image\nproduct,original.jpg\n')
            expected=sha256(source)
            self.assertEqual(run.export.verify_source_csv(source,expected),expected)
            source.write_text('sku,base_image\nproduct,replaced.jpg\n')
            with self.assertRaisesRegex(ValueError,'Original media CSV changed'):
                run.export.verify_source_csv(source,expected)

class ConservativeQualificationTest(unittest.TestCase):
    evidence=PilotRecoveryContractTest.evidence
    def policy(self,p):
        atomic_json(p/'selection-policy.json',{'mode':'conservative_keep_uncertain_originals',
            'checks_identity':checks.decision_identity()})

    def test_conservative_mode_preserves_the_failed_recovery_target_in_the_report(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);self.evidence(p,255,170);report=run.reference_report(p)
            self.assertFalse(report['passed'])
            self.assertFalse(run.reference_qualification(p,report)['accepted'])
            self.policy(p);qualified=run.reference_qualification(p,report)
            self.assertTrue(qualified['accepted'])
            self.assertFalse(qualified['original_recovery_contract_passed'])
            self.assertFalse(report['passed'])

    def test_conservative_mode_cannot_override_an_unsafe_control(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);self.evidence(p,282,179,unsafe=True);self.policy(p)
            self.assertFalse(run.reference_qualification(p,run.reference_report(p))['accepted'])

if __name__=='__main__':unittest.main()
