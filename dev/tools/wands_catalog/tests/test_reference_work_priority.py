import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bulk_expansion_images import connect
from repair_expansion_references import queue


class ReferencePriorityTest(unittest.TestCase):
    def test_unlimited_completion_retries_do_not_starve_untried_repairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);db=connect(run)
            try:
                db.execute('CREATE TABLE references_to_review(image_sha256,design_sha256,path,design,review)')
                for key,n in [('a-repeated',14),('z-untried',3)]:
                    db.execute('INSERT INTO references_to_review VALUES(?,?,?,?,?)',
                               (key,'design',key+'.jpg','{}',json.dumps({'decision':'rejected'})))
                    for attempt in range(1,n+1):
                        db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,?)',
                                   (key,'design',attempt,'image.jpg',str(attempt),json.dumps({'decision':'rejected'})))
                with mock.patch('authorized_completion.reference_admitted',return_value=True), \
                        mock.patch('export_expanded_catalog.accepted_retained',return_value=None), \
                        mock.patch('bulk_expansion_images.descriptor',return_value={'review_identity':'qa'}):
                    self.assertEqual([row['image_sha256'] for row,_ in queue(db,False,run)],
                                     ['z-untried','a-repeated'])
            finally:db.close()

    def test_queue_verifies_large_frozen_candidate_once_per_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);db=connect(run)
            try:
                db.execute('CREATE TABLE references_to_review(image_sha256,design_sha256,path,design,review)')
                for key in ('a','b','c'):
                    db.execute('INSERT INTO references_to_review VALUES(?,?,?,?,?)',
                               (key,'design',key+'.jpg','{}',json.dumps({'decision':'rejected'})))
                with mock.patch('authorized_completion.reference_admitted',return_value=True), \
                        mock.patch('export_expanded_catalog.accepted_retained',return_value=None), \
                        mock.patch('bulk_expansion_images.descriptor',return_value={'review_identity':'qa'}) as descriptor:
                    self.assertEqual(len(queue(db,False,run)),3)
                    descriptor.assert_called_once_with(run)
            finally:db.close()

    def test_admitted_bounded_reference_pilot_precedes_generic_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);db=connect(run)
            try:
                db.execute('CREATE TABLE references_to_review(image_sha256,design_sha256,path,design,review)')
                for key in ('a-generic','z-admitted'):
                    db.execute('INSERT INTO references_to_review VALUES(?,?,?,?,?)',
                               (key,'design',key+'.jpg','{}',json.dumps({'decision':'rejected'})))
                for attempt in range(1,4):
                    db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,?)',
                               ('z-admitted','design',attempt,'image.jpg',str(attempt),json.dumps({'decision':'rejected'})))
                with mock.patch('completion_recovery.reference_plan',side_effect=lambda run,db,row,attempts:
                                {'prompt':'pilot'} if row['image_sha256']=='z-admitted' else None):
                    self.assertEqual([row['image_sha256'] for row,_ in queue(db,False,run)],
                                     ['z-admitted','a-generic'])
            finally:db.close()

    def test_repair_pending_product_sources_before_unrelated_retained_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=connect(Path(tmp))
            try:
                db.executescript('''CREATE TABLE references_to_review(image_sha256,design_sha256,path,design,review);
                    CREATE TABLE jobs(job_id,state,pilot);
                    CREATE TABLE job_references(job_id,image_sha256,design_sha256);''')
                for key in ('a-unrelated','z-blocking'):
                    db.execute('INSERT INTO references_to_review VALUES(?,?,?,?,?)',
                               (key,'design',key+'.jpg','{}',json.dumps({'decision':'rejected'})))
                db.execute("INSERT INTO jobs VALUES('variant','pending',0)")
                db.execute("INSERT INTO job_references VALUES('variant','z-blocking','design')")
                self.assertEqual([row['image_sha256'] for row,_ in queue(db,False)],
                                 ['z-blocking','a-unrelated'])
                db.execute("UPDATE jobs SET state='accepted'")
                self.assertEqual([row['image_sha256'] for row,_ in queue(db,False)],
                                 ['a-unrelated','z-blocking'])
            finally:db.close()


if __name__=='__main__':unittest.main()
