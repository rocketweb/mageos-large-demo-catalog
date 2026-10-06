import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,MagicMock
from types import SimpleNamespace

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bulk_expansion_images import connect,initial_generation_prompt,CONFIG
from image_policy import product_prompt
from remote_image_batch import reserve,import_results,cancel,sha256,digest
import remote_image_batch


class RemoteBatchTest(unittest.TestCase):
    def test_completed_retry_rounds_do_not_starve_less_tried_jobs(self):
        from authorized_completion import AUTHORIZATION
        db=connect(self.run)
        db.execute('CREATE TABLE completion_authorization(id PRIMARY KEY,policy,policy_sha256)')
        policy={'schema':1,'active':True,'authorization':AUTHORIZATION,
                'candidate_sha256':self.desc['candidate_sha256'],'review_identity':self.desc['review_identity']}
        with db:
            db.execute('INSERT INTO completion_authorization VALUES(1,?,?)',(json.dumps(policy),digest(policy)))
            db.execute('UPDATE jobs SET attempts=9')
            db.execute('UPDATE jobs SET attempts=1 WHERE ordinal=1')
        db.close()
        def planned(run,db,row,desc):
            return {'prompt':product_prompt('A plain blue table'),'seed':1,
                    'reference':None,'attempt':row['attempts']+1}
        with patch('bulk_expansion_images.generation_input',side_effect=planned):
            path=reserve(self.run,1)
        self.assertEqual(json.loads(path.read_text())['jobs'][0]['job_id'],f'{1:064x}')

    def cuda_profile(self):
        profile={'schema':1,'worker_id':'laptop','backend':'diffusers-cuda',
                 'candidate_sha256':self.desc['candidate_sha256'],
                 'review_identity':self.desc['review_identity'],'dtype':'bfloat16',
                 'quantize':None,'offload':'model_cpu','packages':{},'model_files':{}}
        directory=self.run/'remote-renderers';directory.mkdir(exist_ok=True)
        receipt=directory/'laptop-benchmark.json'
        receipt.write_text(json.dumps({'passed':True,'environment_sha256':digest(profile)}))
        profile['benchmark_receipt_sha256']=sha256(receipt)
        (directory/'laptop.json').write_text(json.dumps(profile))
        return profile

    def test_two_workers_reserve_disjoint_jobs_and_resume_their_own_batch(self):
        self.cuda_profile()
        mini=reserve(self.run,1)
        laptop=reserve(self.run,1,worker_id='laptop')
        self.assertNotEqual(mini,laptop)
        self.assertNotEqual(json.loads(mini.read_text())['jobs'][0]['job_id'],
                            json.loads(laptop.read_text())['jobs'][0]['job_id'])
        self.assertEqual(reserve(self.run,1),mini)
        self.assertEqual(reserve(self.run,1,worker_id='laptop'),laptop)

    def test_unapproved_cuda_renderer_cannot_reserve_jobs(self):
        with self.assertRaises(ValueError):reserve(self.run,1,worker_id='laptop')

    def test_cuda_return_requires_exact_renderer_provenance(self):
        profile=self.cuda_profile();path=reserve(self.run,1,worker_id='laptop')
        m,out,result=self.result(path)
        with self.assertRaises(ValueError):import_results(self.run,m['batch_id'],out)
        result['renderer_sha256']=digest(profile)
        (out/'results.json').write_text(json.dumps(result))
        import_results(self.run,m['batch_id'],out)
        db=connect(self.run);row=db.execute("SELECT * FROM jobs WHERE state='generated'").fetchone();db.close()
        self.assertIsNone(row['review'])
        event=json.loads(Path(row['image_path']).with_suffix('.json').read_text())
        self.assertEqual(event['renderer'],profile)
        self.assertIsNone(event['config']['quantize'])

    def test_changed_cuda_profile_rejects_return(self):
        self.cuda_profile();path=reserve(self.run,1,worker_id='laptop');m,out,result=self.result(path)
        profile=self.cuda_profile();profile['packages']={'torch':'changed'}
        (self.run/'remote-renderers/laptop.json').write_text(json.dumps(profile))
        with self.assertRaises(ValueError):import_results(self.run,m['batch_id'],out)

    def test_model_verification_accepts_hash_pinned_huggingface_cache_links(self):
        blob=self.run/'blob';blob.write_bytes(b'pinned model bytes')
        model=self.run/'model';model.mkdir();(model/'weights').symlink_to(blob)
        remote_image_batch.verify_model_files(model,{'weights':{'sha256':sha256(blob)}})
        with self.assertRaises(ValueError):
            remote_image_batch.verify_model_files(model,{'../blob':{'sha256':sha256(blob)}})
        blob.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            remote_image_batch.verify_model_files(model,{'weights':{'sha256':'wrong'}})

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.run=Path(self.tmp.name);db=connect(self.run)
        db.executescript('''CREATE TABLE jobs(job_id TEXT PRIMARY KEY,ordinal,request,pilot,state,attempts,
                           image_path,image_sha256,review,error,updated);
                           CREATE TABLE references_to_review(review);''')
        for index in range(5):
            job={'job_id':f'{index:064x}','prompt':product_prompt('A plain blue table'),
                 'reference':{'job_id':'source'} if index==4 else None,'seed':index,
                 'design':{'profile':str(index),'material':'Metal','color':'Blue'}}
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,\'pending\',0,NULL,NULL,NULL,NULL,0)',
                       (job['job_id'],index,json.dumps(job),int(index==0)))
        db.commit();db.close()
        self.desc={'candidate_sha256':'candidate','review_identity':'policy','config':{**CONFIG,'width':16,'height':16},'model_files':{},'packages':{}}
        self.descriptor=patch('bulk_expansion_images.descriptor',return_value=self.desc);self.descriptor.start();self.addCleanup(self.descriptor.stop)
        self.gate=patch('bulk_expansion_images.require_bulk_gate');self.gate.start();self.addCleanup(self.gate.stop)

    def source(self):
        image=self.run/'source.jpg';Image.new('RGB',(16,16),'white').save(image)
        db=connect(self.run)
        job=json.loads(db.execute('SELECT request FROM jobs WHERE ordinal=0').fetchone()[0]);job['design_sha256']='source-design'
        review={'decision':'accepted','review_identity':'policy','image_sha256':sha256(image),'design_sha256':'source-design'}
        db.execute("UPDATE jobs SET state='accepted',request=?,image_path=?,image_sha256=?,review=? WHERE ordinal=0",
                   (json.dumps(job),str(image),sha256(image),json.dumps(review)))
        variant=json.loads(db.execute('SELECT request FROM jobs WHERE ordinal=4').fetchone()[0]);variant['reference']={'job_id':job['job_id']}
        db.execute('UPDATE jobs SET request=? WHERE ordinal=4',(json.dumps(variant),));db.commit();db.close();return image

    def rejected(self,attempts=1):
        image=self.run/'rejected.jpg';Image.new('RGB',(16,16),'red').save(image)
        db=connect(self.run);db.execute("UPDATE jobs SET state='rejected',attempts=?,image_path=?,image_sha256=? WHERE ordinal=3",(attempts,str(image),sha256(image)))
        db.commit();db.close();return image

    def test_completion_imports_sealed_old_recipe_for_qa_only(self):
        from authorized_completion import AUTHORIZATION
        from build_expanded_catalog import canonical
        self.source();path=reserve(self.run,4);manifest,out,_=self.result(path)
        db=connect(self.run)
        db.executescript('CREATE TABLE completion_authorization(id PRIMARY KEY,policy,policy_sha256); CREATE TABLE completion_targets(kind,target,intent_sha256,PRIMARY KEY(kind,target));')
        p={'schema':1,'active':True,'authorization':AUTHORIZATION,'candidate_sha256':'candidate','review_identity':'policy'}
        db.execute('INSERT INTO completion_authorization VALUES(1,?,?)',(canonical(p),digest(p)))
        for job in manifest['jobs']:
            db.execute('INSERT INTO completion_targets VALUES(?,?,?)',('job',job['job_id'],job['request_sha256']))
        db.commit();db.close()
        jobs={j['job_id']:j for j in manifest['jobs']}
        def revised(run,db,row,desc):
            j=jobs[row['job_id']]
            return {'prompt':product_prompt('Updated rendering recipe'),'seed':j['seed'],'attempt':j['attempt'],
                    'reference':self.run/'source.jpg' if j['reference_sha256'] else None}
        with patch('bulk_expansion_images.generation_input',side_effect=revised):import_results(self.run,manifest['batch_id'],out)
        db=connect(self.run);rows=list(db.execute("SELECT * FROM jobs WHERE state='generated'"));db.close()
        self.assertEqual(len(rows),len(manifest['jobs']))
        self.assertTrue(all(r['review'] is None for r in rows))
        for row in rows:
            event=json.loads(Path(row['image_path']).with_suffix('.json').read_text())
            self.assertEqual(event['actual_prompt'],jobs[row['job_id']]['prompt'])
            self.assertEqual(event['completion_recipe_import']['policy_sha256'],digest(p))

    def test_reference_variant_is_reserved_with_frozen_source(self):
        source=self.source();path=reserve(self.run,1);packet=json.loads(path.read_text());job=packet['jobs'][0]
        self.assertEqual(job['job_id'],f'{4:064x}')
        self.assertEqual(job['reference_sha256'],sha256(source))
        self.assertEqual(sha256(path.parent/job['reference_file']),sha256(source))
        self.assertIn('Recolor only the product surfaces',job['prompt'])
        m,out,_=self.result(path);import_results(self.run,m['batch_id'],out)
        db=connect(self.run);row=db.execute('SELECT * FROM jobs WHERE ordinal=4').fetchone();db.close()
        self.assertEqual(row['state'],'generated');self.assertIsNone(row['review'])
        event=json.loads(Path(row['image_path']).with_suffix('.json').read_text())
        self.assertEqual(event['reference_sha256'],sha256(source))

    def test_rejected_candidate_uses_edit_next_attempt_and_cancel_restores_it(self):
        source=self.rejected();path=reserve(self.run,1);m=json.loads(path.read_text());job=m['jobs'][0]
        self.assertEqual(job['job_id'],f'{3:064x}');self.assertEqual(job['attempt'],2)
        self.assertEqual(job['seed'],3+104729);self.assertEqual(job['reference_sha256'],sha256(source))
        cancel(self.run,m['batch_id']);db=connect(self.run);row=db.execute('SELECT * FROM jobs WHERE ordinal=3').fetchone();db.close()
        self.assertEqual(row['state'],'rejected');self.assertEqual(row['attempts'],1)
        self.assertEqual(row['image_sha256'],sha256(source))

    def test_retry_import_preserves_attempt_and_supports_future_reservation(self):
        self.rejected();path=reserve(self.run,1);m,out,_=self.result(path);import_results(self.run,m['batch_id'],out)
        db=connect(self.run);row=db.execute('SELECT * FROM jobs WHERE ordinal=3').fetchone()
        self.assertEqual(row['attempts'],2);self.assertEqual(Path(row['image_path']).name,'attempt-02.jpg')
        db.execute("UPDATE jobs SET state='rejected' WHERE ordinal=3");db.commit();db.close()
        next_job=json.loads(reserve(self.run,1).read_text())['jobs'][0]
        self.assertEqual(next_job['job_id'],row['job_id']);self.assertEqual(next_job['attempt'],3)

    def test_exhausted_retries_are_not_reset(self):
        self.rejected(3);path=reserve(self.run,1)
        self.assertEqual(json.loads(path.read_text())['jobs'][0]['job_id'],f'{2:064x}')

    def test_admitted_prompt_recovery_reserves_and_imports_only_for_normal_qa(self):
        import inspect
        from bulk_expansion_images import source_recolor_prompt,atomic_json
        from source_prompt_recovery import prepare,LEGACY_CUE,ADMISSION
        source=self.source();db=connect(self.run)
        job_id=f'{4:064x}';directory=self.run/'candidates'/job_id;directory.mkdir(parents=True)
        for attempt in range(1,4):
            path=directory/f'attempt-{attempt:02d}.jpg';Image.new('RGB',(16,16),'red').save(path)
            atomic_json(path.with_suffix('.json'),{'attempt':attempt,'reference_sha256':sha256(source),
                        'actual_prompt':LEGACY_CUE,'image_sha256':sha256(path)})
        db.execute("UPDATE jobs SET state='rejected',attempts=3,image_path=?,image_sha256=? WHERE ordinal=4",
                   (str(path),sha256(path)));db.commit();db.close()
        atomic_json(self.run/'run.json',self.desc)
        benchmark=self.run/'prompt-benchmark.json'
        atomic_json(benchmark,{'passed':True,'strategy':'source-recolor-v2','direct_visual_review_complete':True,
                              'prompt_implementation_sha256':digest(inspect.getsource(source_recolor_prompt)),
                              **{k:self.desc[k] for k in ('candidate_sha256','review_identity')}})
        admission=prepare(self.run,benchmark);self.assertEqual(set(admission['jobs']),{job_id})
        atomic_json(self.run/ADMISSION,admission)
        packet=reserve(self.run,1);manifest,out,_=self.result(packet)
        self.assertEqual(manifest['jobs'][0]['attempt'],4)
        self.assertNotIn('hanging chain',manifest['jobs'][0]['prompt'])
        import_results(self.run,manifest['batch_id'],out)
        db=connect(self.run);row=db.execute('SELECT * FROM jobs WHERE ordinal=4').fetchone();db.close()
        self.assertEqual(row['state'],'generated');self.assertIsNone(row['review']);self.assertEqual(row['attempts'],4)
        self.assertTrue((directory/'attempt-03.jpg').is_file())
        with self.assertRaises(ValueError):prepare(self.run,benchmark)

    def test_changed_source_acceptance_rejects_return(self):
        self.source();path=reserve(self.run,1);m,out,_=self.result(path)
        db=connect(self.run);db.execute("UPDATE jobs SET state='rejected' WHERE ordinal=0");db.commit();db.close()
        with self.assertRaises(ValueError):import_results(self.run,m['batch_id'],out)

    def test_transferred_reference_hash_and_path_are_checked(self):
        self.source();path=reserve(self.run,1);job=json.loads(path.read_text())['jobs'][0]
        self.assertEqual(remote_image_batch.reference_path(path,job),path.parent/job['reference_file'])
        with self.assertRaises(ValueError):remote_image_batch.reference_path(path,{**job,'reference_file':'../source.jpg'})
        (path.parent/job['reference_file']).write_bytes(b'changed')
        with self.assertRaises(ValueError):remote_image_batch.reference_path(path,job)

    def test_manual_correction_instruction_is_pinned_and_rechecked(self):
        source=self.rejected();db=connect(self.run)
        db.execute('INSERT INTO manual_reviews VALUES(?,?,?,?)',(f'{3:064x}',sha256(source),'rejected','Remove the extra drawer.'))
        db.commit();db.close();path=reserve(self.run,1);m,out,_=self.result(path)
        self.assertIn('Remove the extra drawer.',m['jobs'][0]['prompt'])
        db=connect(self.run);db.execute("UPDATE manual_reviews SET observations='Correct the legs.'");db.commit();db.close()
        with self.assertRaises(ValueError):import_results(self.run,m['batch_id'],out)

    def test_changed_source_bytes_reject_return(self):
        source=self.source();path=reserve(self.run,1);m,out,_=self.result(path)
        source.write_bytes(b'changed')
        with self.assertRaises(ValueError):import_results(self.run,m['batch_id'],out)

    def test_new_geometry_hold_does_not_strand_previously_reserved_batch(self):
        self.rejected()
        db=connect(self.run)
        row=db.execute('SELECT request FROM jobs WHERE ordinal=3').fetchone()
        request=json.loads(row['request'])
        request['design'].update(profile='balcony-table',construction='half-round top and straight legs')
        hold={'geometry_hold':{'version':'half-round-geometry-v1'},
              'vision':{'acceptable':True},'ocr_flags':[]}
        db.execute("UPDATE jobs SET request=?,state='review_required',review=? WHERE ordinal=3",
                   (json.dumps(request),json.dumps(hold)))
        db.commit();db.close()
        with patch('bulk_expansion_images.awaiting_direct_geometry_review',return_value=False):
            path=reserve(self.run,1)
        manifest,out,_=self.result(path)
        import_results(self.run,manifest['batch_id'],out)
        db=connect(self.run)
        row=db.execute('SELECT state,attempts FROM jobs WHERE ordinal=3').fetchone()
        db.close()
        self.assertEqual((row['state'],row['attempts']),('generated',2))

    def test_renderer_dispatches_reference_to_edit_model(self):
        self.source();path=reserve(self.run,1);job=json.loads(path.read_text())['jobs'][0]
        tokenizer=MagicMock(return_value={'input_ids':[1]})
        tokenizer.apply_chat_template.return_value='prompt'
        edit=MagicMock();edit.return_value.generate_image.return_value=SimpleNamespace(image=Image.new('RGB',(16,16),'blue'))
        generate=MagicMock();mx=SimpleNamespace(clear_cache=lambda:None,get_peak_memory=lambda:123)
        modules={'transformers':SimpleNamespace(Qwen2TokenizerFast=SimpleNamespace(from_pretrained=lambda *a,**k:tokenizer)),
                 'mflux.models.common.config.model_config':SimpleNamespace(ModelConfig=SimpleNamespace(from_name=lambda name:name)),
                 'mflux.models.flux2.variants':SimpleNamespace(Flux2Klein=generate,Flux2KleinEdit=edit),
                 'mlx':SimpleNamespace(core=mx),'mlx.core':mx}
        out=self.run/'rendered'
        with patch.dict(sys.modules,modules):
            remote_image_batch.render(path,sha256(path),self.run/'model',out)
            remote_image_batch.render(path,sha256(path),self.run/'model',out)
        generate.assert_not_called();edit.assert_called_once()
        self.assertEqual(edit.return_value.generate_image.call_count,1)
        self.assertEqual(edit.return_value.generate_image.call_args.kwargs['image_paths'],[path.parent/job['reference_file']])

    def result(self,path):
        m=json.loads(path.read_text());out=self.run/'incoming';out.mkdir(exist_ok=True);items=[]
        for job in m['jobs']:
            img=out/(job['job_id']+'.jpg');Image.new('RGB',(16,16),'blue').save(img)
            items.append({'job_id':job['job_id'],'job_sha256':digest(job),'image_sha256':sha256(img),'seconds':1.2})
        value={'batch_id':m['batch_id'],'manifest_sha256':sha256(path),'images':items}
        (out/'results.json').write_text(json.dumps(value));return m,out,value

    def test_reservation_is_exclusive_and_resumable(self):
        path=reserve(self.run,2)
        self.assertEqual(reserve(self.run,2),path)
        db=connect(self.run)
        rows=db.execute('SELECT job_id,state FROM jobs ORDER BY ordinal').fetchall();db.close()
        self.assertEqual([r['state'] for r in rows],['pending','pending','remote_reserved','remote_reserved','pending'])
        self.assertEqual(len(json.loads(path.read_text())['jobs']),2)

    def test_returned_images_require_qa_and_repeat_import_is_idempotent(self):
        path=reserve(self.run,2);m,out,_=self.result(path)
        import_results(self.run,m['batch_id'],out);import_results(self.run,m['batch_id'],out)
        db=connect(self.run)
        rows=db.execute("SELECT state,attempts,review,image_path FROM jobs WHERE state='generated'").fetchall();db.close()
        self.assertEqual(len(rows),2)
        for row in rows:
            self.assertEqual(row['attempts'],1);self.assertIsNone(row['review'])
            event=json.loads(Path(row['image_path']).with_suffix('.json').read_text())
            self.assertIsNone(event['reference_sha256'])
            self.assertEqual(event['remote_batch_id'],m['batch_id'])

    def test_corrupt_return_changes_no_job(self):
        path=reserve(self.run,2);m,out,result=self.result(path)
        (out/(result['images'][1]['job_id']+'.jpg')).write_bytes(b'corrupt')
        with self.assertRaises(ValueError):import_results(self.run,m['batch_id'],out)
        db=connect(self.run)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs WHERE state='remote_reserved'").fetchone()[0],2)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs WHERE state='generated'").fetchone()[0],0);db.close()

    def test_cancel_releases_jobs_and_rejects_late_results(self):
        path=reserve(self.run,2);m,out,_=self.result(path)
        cancel(self.run,m['batch_id'])
        with self.assertRaises(ValueError):import_results(self.run,m['batch_id'],out)
        second=reserve(self.run,2)
        self.assertNotEqual(path,second)

    def test_changed_request_rejects_whole_batch(self):
        path=reserve(self.run,2);m,out,_=self.result(path)
        db=connect(self.run)
        db.execute('UPDATE jobs SET request=? WHERE job_id=?',('{}',m['jobs'][1]['job_id']));db.commit();db.close()
        with self.assertRaises(ValueError):import_results(self.run,m['batch_id'],out)
        self.assertFalse((self.run/'candidates').exists())

    def test_wrong_batch_or_missing_image_is_rejected(self):
        path=reserve(self.run,2);m,out,result=self.result(path)
        for field,value in [('manifest_sha256','wrong'),('images',result['images'][:1])]:
            with self.subTest(field=field):
                changed={**result,field:value};(out/'results.json').write_text(json.dumps(changed))
                with self.assertRaises(ValueError):import_results(self.run,m['batch_id'],out)

    def test_initial_prompt_preserves_local_paint_instruction(self):
        job={'prompt':product_prompt('A plain blue table'),'design':{'material':'Metal','color':'Blue'}}
        expected=product_prompt('A plain blue table. The main product surfaces have an opaque Blue painted finish over the Metal structure. Preserve subtle physical texture beneath the coating; do not substitute the unpainted natural material color.')
        self.assertEqual(initial_generation_prompt(job),expected)


if __name__=='__main__':unittest.main()
