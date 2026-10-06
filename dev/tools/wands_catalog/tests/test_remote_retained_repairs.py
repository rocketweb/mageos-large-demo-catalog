"""Remote retained repairs preserve originals, budgets, ownership and ordinary QA."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bulk_expansion_images import CONFIG, connect
from build_expanded_catalog import canonical, digest
from remote_image_batch import reserve, import_results, cancel, sha256
from repair_expansion_references import queue


class RemoteRetainedRepairTest(unittest.TestCase):
    def completion_with_pending_new_job(self):
        from authorized_completion import AUTHORIZATION
        from image_policy import product_prompt
        db=connect(self.run)
        db.executescript('CREATE TABLE completion_authorization(id PRIMARY KEY,policy,policy_sha256); CREATE TABLE completion_targets(kind,target,intent_sha256,PRIMARY KEY(kind,target));')
        p={'schema':1,'active':True,'authorization':AUTHORIZATION,'candidate_sha256':'candidate','review_identity':'policy'}
        db.execute('INSERT INTO completion_authorization VALUES(1,?,?)',(canonical(p),digest(p)))
        for row in self.rows:
            db.execute('INSERT INTO completion_targets VALUES(?,?,?)',('reference',digest([row[0],row[1]]),row[1]))
        job={'job_id':'a'*64,'prompt':product_prompt('Plain blue cart'),'reference':None,'seed':1,
             'profile':'cart','design':{'profile':'cart','subject':'Plain blue cart','material':'Metal','color':'Blue','construction':'two shelves'}}
        db.execute("INSERT INTO jobs VALUES(?,?,?,0,'pending',0,NULL,NULL,NULL,NULL,0)",(job['job_id'],1,canonical(job)))
        db.execute('INSERT INTO completion_targets VALUES(?,?,?)',('job',job['job_id'],digest(job)))
        db.commit();db.close()
        return job

    def test_completion_allocates_two_retained_packets_before_one_new_packet(self):
        job=self.completion_with_pending_new_job()
        for _ in range(2):
            path,packet=self.packet(limit=1)
            self.assertEqual(packet.get('kind'),'retained-reference-repairs',
                'A few hard new variants must not monopolize every remote packet')
            import_results(self.run,packet['batch_id'],self.returned(path,packet))
        _,packet=self.packet(limit=1)
        self.assertNotIn('kind',packet)
        self.assertEqual(packet['jobs'][0]['job_id'],job['job_id'])

    def test_completion_allocation_does_not_replace_an_inflight_new_packet(self):
        from image_policy import product_prompt
        db=connect(self.run);job={'job_id':'b'*64,'prompt':product_prompt('Plain cart'),'reference':None,'seed':1,'design':{'profile':'cart'}}
        db.execute("INSERT INTO jobs VALUES(?,?,?,0,'pending',0,NULL,NULL,NULL,NULL,0)",(job['job_id'],1,canonical(job)));db.commit();db.close()
        path,packet=self.packet(limit=1)
        self.assertNotIn('kind',packet)
        self.completion_with_pending_new_job()
        self.assertEqual(reserve(self.run,1),path)
        self.assertEqual(json.loads(path.read_text()),packet)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        self.desc = {'candidate_sha256': 'candidate', 'review_identity': 'policy',
                     'config': {**CONFIG, 'width': 16, 'height': 16}, 'model_files': {}, 'packages': {}}
        for p in (patch('bulk_expansion_images.descriptor', return_value=self.desc),
                  patch('bulk_expansion_images.require_bulk_gate')):
            p.start(); self.addCleanup(p.stop)
        db = connect(self.run)
        db.executescript('''CREATE TABLE jobs(job_id PRIMARY KEY,ordinal,request,pilot,state,attempts,image_path,image_sha256,review,error,updated);
            CREATE TABLE references_to_review(image_sha256,design_sha256,path,design,review,PRIMARY KEY(image_sha256,design_sha256));''')
        self.rows = []
        for i in range(3):
            path = self.run / f'original-{i}.jpg'; Image.new('RGB', (16, 16), (i * 50, 60, 120)).save(path)
            design = {'subject': f'Blue storage cabinet {chr(65+i)}', 'product_class': 'Cabinets',
                      'material': 'Metal', 'color': 'Blue', 'construction': 'Plain cabinet'}
            q = {'decision': 'rejected', 'review_identity': 'policy', 'image_sha256': sha256(path),
                 'design_sha256': digest(design), 'vision': {'product_matches': False}}
            row = (sha256(path), digest(design), str(path), canonical(design), canonical(q))
            db.execute('INSERT INTO references_to_review VALUES(?,?,?,?,?)', row); self.rows.append(row)
        db.commit(); db.close()

    def packet(self, worker='mini', limit=2):
        path = reserve(self.run, limit, worker_id=worker)
        self.assertIsNotNone(path, 'Idle remote workers must receive eligible retained repairs')
        return path, json.loads(path.read_text())

    def returned(self, path, packet):
        output = path.parent / 'returned'; output.mkdir()
        images = []
        for job in packet['jobs']:
            image = output / (job['job_id'] + '.jpg'); Image.new('RGB', (16, 16), 'blue').save(image)
            images.append({'job_id': job['job_id'], 'job_sha256': digest(job), 'image_sha256': sha256(image), 'seconds': 1})
        result = {'batch_id': packet['batch_id'], 'manifest_sha256': sha256(path), 'images': images}
        (output / 'results.json').write_text(json.dumps(result)); return output

    def test_reserve_freezes_original_and_full_design_without_new_catalog_jobs(self):
        path, packet = self.packet()
        self.assertEqual(packet['kind'], 'retained-reference-repairs')
        self.assertEqual(len(packet['jobs']), 2)
        for job in packet['jobs']:
            self.assertEqual(job['attempt'], 1)
            self.assertEqual(sha256(path.parent / job['reference_file']), job['reference_sha256'])
            self.assertIn('target', job)
        db = connect(self.run)
        self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT count(*) FROM reference_repairs').fetchone()[0], 0)
        self.assertEqual(len(queue(db, False, self.run)), 1)
        db.close()
        self.assertEqual(reserve(self.run, 2), path)

    def test_return_registers_immutable_attempts_for_qa_and_reimport_is_idempotent(self):
        path, packet = self.packet(); output = self.returned(path, packet)
        before = [sha256(Path(row[2])) for row in self.rows]
        import_results(self.run, packet['batch_id'], output)
        import_results(self.run, packet['batch_id'], output)
        db = connect(self.run); rows = list(db.execute('SELECT * FROM reference_repairs'))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['review'] is None and row['attempt'] == 1 for row in rows))
        self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT state FROM remote_batches').fetchone()[0], 'imported'); db.close()
        self.assertEqual([sha256(Path(row[2])) for row in self.rows], before)

    def test_changed_design_or_original_rejects_entire_return_before_any_attempt_write(self):
        path, packet = self.packet(); output = self.returned(path, packet)
        target = packet['jobs'][-1]['target']
        db = connect(self.run); db.execute('UPDATE references_to_review SET design=? WHERE image_sha256=?',
            ('{}', target['original_sha256'])); db.commit(); db.close()
        with self.assertRaises(ValueError): import_results(self.run, packet['batch_id'], output)
        db = connect(self.run); self.assertEqual(db.execute('SELECT count(*) FROM reference_repairs').fetchone()[0], 0); db.close()
        self.assertFalse((self.run / 'reference-repairs').exists())

    def test_changed_history_fails_closed_and_exhausted_budget_is_never_reset(self):
        db = connect(self.run)
        for row in self.rows:
            for attempt in range(1, 4):
                db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,?)',
                    (row[0], row[1], attempt, row[2], row[0], row[4]))
        db.commit(); db.close()
        self.assertIsNone(reserve(self.run, 2))

    def test_authorized_completion_imports_attempt_four_without_resetting_history(self):
        from authorized_completion import AUTHORIZATION
        db=connect(self.run)
        db.executescript('CREATE TABLE completion_authorization(id PRIMARY KEY,policy,policy_sha256); CREATE TABLE completion_targets(kind,target,intent_sha256,PRIMARY KEY(kind,target));')
        p={'schema':1,'active':True,'authorization':AUTHORIZATION,'candidate_sha256':'candidate','review_identity':'policy'}
        db.execute('INSERT INTO completion_authorization VALUES(1,?,?)',(canonical(p),digest(p)))
        for row in self.rows:
            db.execute('INSERT INTO completion_targets VALUES(?,?,?)',('reference',digest([row[0],row[1]]),row[1]))
            for attempt in range(1,4):db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,?)',(row[0],row[1],attempt,row[2],row[0],row[4]))
        db.commit();db.close()
        path,packet=self.packet(limit=1)
        self.assertEqual(packet['jobs'][0]['attempt'],4)
        self.assertEqual(packet['jobs'][0]['target']['mode'],'generate')
        import_results(self.run,packet['batch_id'],self.returned(path,packet))
        db=connect(self.run);self.assertEqual(db.execute('SELECT count(*) FROM reference_repairs').fetchone()[0],10)
        self.assertIsNone(db.execute('SELECT review FROM reference_repairs WHERE attempt=4').fetchone()[0]);db.close()

    def test_original_pixel_change_rejects_packet_without_publishing_any_candidate(self):
        path, packet = self.packet(); output = self.returned(path, packet)
        target = packet['jobs'][-1]['target'];row = next(r for r in self.rows if r[0] == target['original_sha256'])
        Image.new('RGB', (16,16), 'red').save(row[2])
        with self.assertRaises(ValueError):import_results(self.run, packet['batch_id'], output)
        self.assertFalse((self.run/'reference-repairs').exists())

    def test_authorized_completion_can_repair_an_unreviewable_original(self):
        from authorized_completion import AUTHORIZATION
        db=connect(self.run)
        db.executescript('CREATE TABLE completion_authorization(id PRIMARY KEY,policy,policy_sha256); CREATE TABLE completion_targets(kind,target,intent_sha256,PRIMARY KEY(kind,target));')
        p={'schema':1,'active':True,'authorization':AUTHORIZATION,'candidate_sha256':'candidate','review_identity':'policy'}
        db.execute('INSERT INTO completion_authorization VALUES(1,?,?)',(canonical(p),digest(p)))
        for row in self.rows:
            db.execute('INSERT INTO completion_targets VALUES(?,?,?)',('reference',digest([row[0],row[1]]),row[1]))
        db.execute('UPDATE references_to_review SET review=NULL');db.commit();db.close()
        path,packet=self.packet(limit=1)
        self.assertEqual(packet['jobs'][0]['target']['mode'],'generate')
        self.assertIsNone(packet['jobs'][0]['reference_sha256'])
        import_results(self.run,packet['batch_id'],self.returned(path,packet))
        db=connect(self.run)
        self.assertEqual(len(queue(db,False,self.run)),2,'Wait for the new repair QA before rendering another attempt')
        self.assertTrue(all(r[0] is None for r in db.execute('SELECT review FROM references_to_review')))
        db.close()

    def test_accepted_repair_can_supply_a_source_without_original_qa(self):
        from bulk_expansion_images import accepted_reference
        row=self.rows[0];db=connect(self.run)
        db.execute('CREATE TABLE job_references(job_id,image_sha256,design_sha256)')
        db.execute('INSERT INTO job_references VALUES(?,?,?)',('child',row[0],row[1]))
        db.execute('UPDATE references_to_review SET review=NULL WHERE image_sha256=?',(row[0],))
        q={'decision':'accepted','model':'model','review_identity':'policy','image_sha256':row[0],
           'design_sha256':row[1],'component_review':None,'table_component_review':None}
        db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,?)',(row[0],row[1],1,row[2],row[0],canonical(q)))
        job={'job_id':'child','reference':{'image_sha256':row[0]}}
        self.assertEqual(accepted_reference(db,job,'policy'),Path(row[2]))
        db.close()

    def test_history_change_rejects_packet_before_writing_other_targets(self):
        path, packet = self.packet(); output = self.returned(path, packet)
        target = packet['jobs'][-1]['target'];row = next(r for r in self.rows if r[0] == target['original_sha256'])
        db=connect(self.run);db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,?)',
            (row[0], row[1], 1, row[2], row[0], row[4]));db.commit();db.close()
        with self.assertRaises(ValueError):import_results(self.run, packet['batch_id'], output)
        self.assertFalse((self.run/'reference-repairs').exists())

    def test_human_keep_and_older_accepted_repair_are_not_reprocessed(self):
        protected = {self.rows[0][0]}
        row = self.rows[1];design=json.loads(row[3])
        q={'decision':'accepted','model':'model','review_identity':'policy','image_sha256':row[0],
            'design_sha256':row[1],'component_review':None,'table_component_review':None}
        db=connect(self.run)
        db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,?)',(row[0],row[1],1,row[2],row[0],canonical(q)))
        db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,?)',(row[0],row[1],2,row[2],row[0],row[4]))
        db.commit();db.close()
        with patch('remote_reference_repairs.kept_images',return_value=protected):
            self.assertEqual(len(queue(connect(self.run),False,self.run)),1)
            _,packet=self.packet(limit=2)
        self.assertEqual(len(packet['jobs']),1)
        self.assertEqual(packet['jobs'][0]['target']['original_sha256'],self.rows[2][0])

    def test_cuda_retained_results_require_the_admitted_renderer_provenance(self):
        profile={'quantize':None,'backend':'diffusers-cuda','fixture':'admitted'}
        with patch('remote_image_batch.renderer_profile',return_value=profile):
            path,packet=self.packet('laptop');output=self.returned(path,packet)
            with self.assertRaises(ValueError):import_results(self.run,packet['batch_id'],output)
            p=output/'results.json';result=json.loads(p.read_text());result['renderer_sha256']=digest(profile);p.write_text(json.dumps(result))
            import_results(self.run,packet['batch_id'],output)
        db=connect(self.run);row=db.execute('SELECT * FROM reference_repairs LIMIT 1').fetchone();db.close()
        event=json.loads(Path(row['image_path']).with_suffix('.json').read_text())
        self.assertEqual(event['renderer'],profile)
        self.assertIsNone(event['config']['quantize'])

    def test_cancel_releases_only_owned_reservations_and_preserves_originals(self):
        path, packet = self.packet(); cancel(self.run, packet['batch_id'])
        db = connect(self.run)
        self.assertEqual(len(queue(db, False, self.run)), 3)
        self.assertEqual(db.execute('SELECT count(*) FROM reference_repairs').fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT state FROM remote_batches').fetchone()[0], 'cancelled'); db.close()
        self.assertTrue(all(sha256(Path(row[2])) == row[0] for row in self.rows))

    def test_two_workers_get_disjoint_retained_targets(self):
        first, a = self.packet(limit=1)
        profile = {'fixture': 'admitted cuda profile'}
        with patch('remote_image_batch.renderer_profile', return_value=profile):
            second, b = self.packet('laptop', limit=2)
            self.assertEqual(reserve(self.run, 2, worker_id='laptop'), second)
        self.assertTrue({j['job_id'] for j in a['jobs']}.isdisjoint(j['job_id'] for j in b['jobs']))
        self.assertEqual(b['schema'], 3)

    def test_new_product_work_keeps_priority_over_retained_repairs(self):
        from image_policy import product_prompt
        db = connect(self.run); job = {'job_id': 'a'*64, 'prompt': product_prompt('Plain cart'), 'reference': None, 'seed': 1, 'design': {'profile': 'cart'}}
        db.execute('INSERT INTO jobs VALUES(?,?,?,0,\'pending\',0,NULL,NULL,NULL,NULL,0)', (job['job_id'], 1, canonical(job))); db.commit(); db.close()
        _, packet = self.packet(limit=1)
        self.assertNotIn('kind', packet)
        self.assertEqual(packet['jobs'][0]['job_id'], job['job_id'])
