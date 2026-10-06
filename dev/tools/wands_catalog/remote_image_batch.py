"""Reserve generation and edit batches centrally; accept returned bytes for QA only.

The mini never receives the catalog database or review credentials. Reservation
and import share the Studio generation lock, so the native worker cannot race
either operation. Remote images always enter the ordinary generated/QA queue.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
import uuid


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))


def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha256(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def verify_model_files(model_path,files):
    for name,pin in files.items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe model filename')
        # Hugging Face snapshots use links into their sibling blob cache.
        # The frozen content hash, rather than link placement, binds the model.
        if sha256(model_path/relative)!=pin['sha256']:
            raise ValueError('Pinned model differs: '+name)


def schema(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS remote_batches(
          batch_id TEXT PRIMARY KEY, manifest TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
          state TEXT NOT NULL, results_sha256 TEXT, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS remote_image_jobs(
          job_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES remote_batches(batch_id));
        CREATE TABLE IF NOT EXISTS remote_batch_workers(
          batch_id TEXT PRIMARY KEY REFERENCES remote_batches(batch_id),worker_id TEXT NOT NULL);
    ''')


def renderer_profile(run,worker_id,desc):
    if not re.fullmatch('[a-z][a-z0-9_-]{0,31}',worker_id):raise ValueError('Invalid worker ID')
    if worker_id=='mini':return None
    path=run/'remote-renderers'/(worker_id+'.json')
    if not path.is_file():raise ValueError('Worker renderer has not passed benchmark admission')
    profile=json.loads(path.read_text())
    if (profile.get('schema')!=1 or profile.get('worker_id')!=worker_id
            or profile.get('backend')!='diffusers-cuda' or profile.get('dtype')!='bfloat16'
            or profile.get('quantize') is not None or profile.get('offload')!='model_cpu'
            or profile.get('candidate_sha256')!=desc['candidate_sha256']
            or profile.get('review_identity')!=desc['review_identity']):
        raise ValueError('Unsupported or stale renderer profile')
    if any(profile.get('model_files',{}).get(k)!=v for k,v in desc['model_files'].items()):
        raise ValueError('CUDA model differs from the pinned model')
    receipt=run/'remote-renderers'/(worker_id+'-benchmark.json')
    if not receipt.is_file() or sha256(receipt)!=profile.get('benchmark_receipt_sha256'):
        raise ValueError('Renderer benchmark receipt missing or changed')
    evidence=json.loads(receipt.read_text())
    environment={k:v for k,v in profile.items() if k!='benchmark_receipt_sha256'}
    if evidence.get('environment_sha256')!=digest(environment) or evidence.get('passed') is not True:
        raise ValueError('Renderer benchmark does not admit this environment')
    return profile


def reserve(run,limit=64,diverse=False,worker_id='mini'):
    from bulk_expansion_images import (lock,descriptor,connect,require_bulk_gate,
                                      generation_input,atomic_json,status)
    if not 1<=limit<=64:raise ValueError('Batch size must be 1..64')
    with lock(run,'generation'):
        desc=descriptor(run);db=connect(run)
        try:
            require_bulk_gate(run,db,desc);profile=renderer_profile(run,worker_id,desc);schema(db)
            # One outstanding batch at a time prevents unlimited reservation if
            # a transfer or remote process stops. Resuming reuses the same bytes.
            old=db.execute("SELECT b.batch_id,b.manifest_sha256 FROM remote_batches b LEFT JOIN remote_batch_workers w USING(batch_id) WHERE b.state='reserved' AND COALESCE(w.worker_id,'mini')=?",(worker_id,)).fetchone()
            if old:
                path=run/'remote-batches'/old['batch_id']/'manifest.json'
                if sha256(path)!=old['manifest_sha256']:raise ValueError('Reserved batch changed')
                if json.loads(path.read_text()).get('renderer')!=profile:raise ValueError('Reserved renderer changed')
                return path
            from authorized_completion import policy
            completion=bool(policy(db,desc))
            if completion:
                # Completion has thousands of retained repairs and often only
                # a handful of repeatedly failing new variants. Give each
                # renderer two retained packets for every new-product packet.
                # Existing sealed packets were resumed above without changes.
                recent=list(db.execute("SELECT json_extract(b.manifest,'$.kind') AS kind FROM remote_batches b "
                    "LEFT JOIN remote_batch_workers w USING(batch_id) WHERE b.state='imported' "
                    "AND COALESCE(w.worker_id,'mini')=? ORDER BY b.updated DESC,b.rowid DESC LIMIT 2",(worker_id,)))
                if len(recent)<2 or any(r['kind']!='retained-reference-repairs' for r in recent):
                    from remote_reference_repairs import reserve_in_lock
                    retained=reserve_in_lock(run,db,desc,profile,limit,worker_id)
                    if retained is not None:return retained
            selected=[];profiles=set();sources={}
            order='attempts,ordinal DESC' if completion else 'ordinal DESC'
            for row in db.execute("SELECT * FROM jobs WHERE state IN ('pending','rejected','review_required','interrupted') AND pilot=0 ORDER BY "+order):
                job=json.loads(row['request'])
                planned=generation_input(run,db,row,desc)
                if planned is None:continue
                # One model per batch keeps edit memory within the mini's budget.
                if selected and bool(planned['reference'])!=bool(selected[0]['reference_sha256']):continue
                design_profile=job['design'].get('profile')
                if diverse and design_profile in profiles:continue
                profiles.add(design_profile)
                source=planned['reference'];pin=sha256(source) if source else None
                if source:sources[pin]=source
                selected.append({'job_id':row['job_id'],'request_sha256':digest(job),
                                 'prompt':planned['prompt'],'seed':planned['seed'],'attempt':planned['attempt'],
                                 'previous_state':row['state'],'previous_image_sha256':row['image_sha256'],
                                 'reference_sha256':pin,'reference_file':f'references/{pin}.jpg' if pin else None})
                if len(selected)>=limit:break
            if not selected:
                from remote_reference_repairs import reserve_in_lock
                return reserve_in_lock(run,db,desc,profile,limit,worker_id)
            batch_id=uuid.uuid4().hex
            manifest={'schema':2,'batch_id':batch_id,'candidate_sha256':desc['candidate_sha256'],
                      'config':desc['config'],'model_files':desc['model_files'],'packages':desc['packages'],
                      'jobs':selected}
            if profile:manifest.update(schema=3,worker_id=worker_id,renderer=profile)
            directory=run/'remote-batches'/batch_id;directory.mkdir(parents=True)
            for pin,source in sources.items():
                target=directory/'references'/(pin+'.jpg');target.parent.mkdir(exist_ok=True)
                shutil.copyfile(source,target)
                if sha256(target)!=pin:raise ValueError('Reference changed during snapshot')
            path=directory/'manifest.json';atomic_json(path,manifest);pin=sha256(path)
            with db:
                db.execute('INSERT INTO remote_batches VALUES(?,?,?,\'reserved\',NULL,?)',
                           (batch_id,canonical(manifest),pin,time.time()))
                db.execute('INSERT INTO remote_batch_workers VALUES(?,?)',(batch_id,worker_id))
                for job in selected:
                    n=db.execute("UPDATE jobs SET state='remote_reserved',updated=? WHERE job_id=? AND state=? AND attempts=?",
                                 (time.time(),job['job_id'],job['previous_state'],job['attempt']-1)).rowcount
                    if n!=1:raise ValueError('Reservation conflict')
                    db.execute('INSERT INTO remote_image_jobs VALUES(?,?) ON CONFLICT(job_id) DO UPDATE SET batch_id=excluded.batch_id',(job['job_id'],batch_id))
            status(run);return path
        finally:db.close()


def inspect_results(manifest,directory):
    from PIL import Image
    result_path=directory/'results.json'
    result=json.loads(result_path.read_text())
    if result.get('batch_id')!=manifest['batch_id'] or result.get('manifest_sha256')!=manifest['_file_sha256']:
        raise ValueError('Result belongs to a different batch')
    expected={job['job_id']:job for job in manifest['jobs']}
    items=result.get('images',[])
    if len(items)!=len(expected) or {x['job_id'] for x in items}!=set(expected):
        raise ValueError('Missing, duplicate or unexpected result jobs')
    verified=[]
    for item in items:
        job=expected[item['job_id']]
        if not re.fullmatch('[a-f0-9]{64}',job['job_id']):raise ValueError('Unsafe image identifier')
        if item.get('job_sha256')!=digest(job):raise ValueError('Changed job parameters')
        path=directory/(job['job_id']+'.jpg')
        if path.is_symlink() or sha256(path)!=item['image_sha256']:raise ValueError('Image bytes changed')
        with Image.open(path) as image:
            if image.format!='JPEG' or image.mode!='RGB' or image.size!=(manifest['config']['width'],manifest['config']['height']):
                raise ValueError('Unexpected image format or dimensions')
            image.verify()
        seconds=item.get('seconds')
        if type(seconds) not in (int,float) or not 0<=seconds<86400:raise ValueError('Invalid generation timing')
        verified.append((job,item,path))
    return result,verified


def import_results(run,batch_id,directory):
    from bulk_expansion_images import lock,descriptor,connect,atomic_json,status,generation_input
    if not re.fullmatch('[a-f0-9]{32}',batch_id):raise ValueError('Invalid batch ID')
    with lock(run,'generation'):
        desc=descriptor(run);db=connect(run)
        try:
            schema(db)
            batch=db.execute('SELECT * FROM remote_batches WHERE batch_id=?',(batch_id,)).fetchone()
            if not batch or batch['state'] not in {'reserved','imported'}:raise ValueError('Batch is not active')
            manifest=json.loads(batch['manifest'])
            if any(manifest[k]!=desc[k] for k in ('candidate_sha256','config','model_files','packages')):
                raise ValueError('Candidate or generation environment changed')
            if manifest.get('renderer'):
                profile=renderer_profile(run,manifest['worker_id'],desc)
                if profile!=manifest['renderer']:raise ValueError('Admitted renderer changed')
            manifest['_file_sha256']=batch['manifest_sha256']
            result,verified=inspect_results(manifest,directory)
            if manifest.get('renderer') and result.get('renderer_sha256')!=digest(manifest['renderer']):
                raise ValueError('Returned renderer provenance differs')
            if manifest.get('kind')=='retained-reference-repairs':
                from remote_reference_repairs import import_in_lock
                return import_in_lock(run,db,desc,batch,manifest,result,verified,directory)
            result_pin=sha256(directory/'results.json')
            if batch['state']=='imported':
                if result_pin!=batch['results_sha256']:raise ValueError('Previously imported result changed')
                return status(run)
            # Validate every ownership/request before writing any file or row.
            recipe_changes={}
            for job,item,path in verified:
                row=db.execute('SELECT j.*,r.batch_id FROM jobs j JOIN remote_image_jobs r USING(job_id) WHERE j.job_id=?',
                               (job['job_id'],)).fetchone()
                if (not row or row['batch_id']!=batch_id or row['state']!='remote_reserved' or row['attempts']!=job['attempt']-1
                        or digest(json.loads(row['request']))!=job['request_sha256']):
                    raise ValueError('Reserved job changed; no import')
                if manifest['schema']>=2:
                    if row['image_sha256']!=job['previous_image_sha256']:raise ValueError('Previous candidate changed')
                    prior={**dict(row),'state':job['previous_state']}
                    planned=generation_input(run,db,prior,desc)
                    if planned is None:
                        # A geometry hold was added after some batches were reserved.
                        # It prevents *new* attempts, but must not invalidate an
                        # already rendered, hash-bound batch. Recalculate with only
                        # that scheduling hold suppressed; all source and prompt
                        # checks below still apply before import.
                        from bulk_expansion_images import awaiting_direct_geometry_review
                        if awaiting_direct_geometry_review(prior):
                            planned=generation_input(run,db,{**prior,'review':None},desc)
                    if planned is None:raise ValueError('Source acceptance or retry eligibility changed')
                    pin=sha256(planned['reference']) if planned['reference'] else None
                    if (pin!=job['reference_sha256'] or any(planned[k]!=job[k] for k in ('seed','attempt'))):
                        raise ValueError('Generation inputs changed; no import')
                    if planned['prompt']!=job['prompt']:
                        from authorized_completion import admitted,policy
                        if not admitted(db,'job',job['job_id'],job['request_sha256'],desc):
                            raise ValueError('Generation inputs changed; no import')
                        recipe_changes[job['job_id']]={'policy_sha256':digest(policy(db,desc)),
                            'scope':'Import the immutable earlier rendering recipe for ordinary QA only; current request, source, seed, attempt and environment must still match.',
                            'sealed_prompt_sha256':digest(job['prompt']),'current_prompt_sha256':digest(planned['prompt'])}
            with db:
                for job,item,path in verified:
                    target=run/'candidates'/job['job_id']/f"attempt-{job['attempt']:02d}.jpg";target.parent.mkdir(parents=True,exist_ok=True)
                    event={'status':'generated','job_id':job['job_id'],'attempt':job['attempt'],
                           'image_sha256':item['image_sha256'],'request_sha256':job['request_sha256'],
                           'actual_prompt':job['prompt'],'config':manifest['config'],'seed':job['seed'],
                           'reference_sha256':job.get('reference_sha256'),'seconds':item['seconds'],'remote_batch_id':batch_id}
                    if job['job_id'] in recipe_changes:event['completion_recipe_import']=recipe_changes[job['job_id']]
                    if manifest.get('renderer'):
                        event['renderer']=manifest['renderer']
                        event['config']={**manifest['config'],'quantize':manifest['renderer']['quantize']}
                    if target.exists():
                        if sha256(target)!=item['image_sha256']:raise ValueError('Existing attempt conflicts')
                        if target.with_suffix('.json').exists() and json.loads(target.with_suffix('.json').read_text())!=event:
                            raise ValueError('Existing metadata conflicts')
                    else:
                        temporary=target.with_suffix('.transfer.jpg');shutil.copyfile(path,temporary)
                        if sha256(temporary)!=item['image_sha256']:raise ValueError('Copy verification failed')
                        os.link(temporary,target);temporary.unlink()
                    atomic_json(target.with_suffix('.json'),event)
                    db.execute("UPDATE jobs SET state='generated',attempts=?,image_path=?,image_sha256=?,review=NULL,error=NULL,updated=? WHERE job_id=?",
                               (job['attempt'],str(target.resolve()),item['image_sha256'],time.time(),job['job_id']))
                db.execute("UPDATE remote_batches SET state='imported',results_sha256=?,updated=? WHERE batch_id=?",
                           (result_pin,time.time(),batch_id))
            return status(run)
        finally:db.close()


def reference_path(manifest_path,job):
    pin=job.get('reference_sha256');name=job.get('reference_file')
    if pin is None and name is None:return None
    if not isinstance(pin,str) or not re.fullmatch('[a-f0-9]{64}',pin) or name!=f'references/{pin}.jpg':
        raise ValueError('Invalid reference filename or hash')
    path=manifest_path.parent/name
    if path.is_symlink() or path.parent.is_symlink() or sha256(path)!=pin:raise ValueError('Transferred reference changed')
    return path


def render(manifest_path,expected_hash,model_path,output):
    output.mkdir(parents=True,exist_ok=True)
    with (output/'worker.lock').open('a') as stream:
        try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit(73)
        return _render(manifest_path,expected_hash,model_path,output)


def _render(manifest_path,expected_hash,model_path,output):
    from importlib.metadata import version
    from image_policy import GuardedImageModel,validate_prompt
    if sha256(manifest_path)!=expected_hash:raise ValueError('Batch manifest changed')
    manifest=json.loads(manifest_path.read_text())
    if manifest['schema'] not in {1,2} or not manifest['jobs']:raise ValueError('Empty or unsupported batch')
    for package,pin in manifest['packages'].items():
        if version(package)!=pin:raise ValueError('Generation dependency differs: '+package)
    verify_model_files(model_path,manifest['model_files'])
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    os.environ.pop('METAL_DEVICE_WRAPPER_TYPE',None)
    from transformers import Qwen2TokenizerFast
    from mflux.models.common.config.model_config import ModelConfig
    from mflux.models.flux2.variants import Flux2Klein,Flux2KleinEdit
    import mlx.core as mx
    tokenizer=Qwen2TokenizerFast.from_pretrained(model_path/'tokenizer',local_files_only=True)
    config=manifest['config']
    model=None;loaded_mode=None
    output.mkdir(parents=True,exist_ok=True);images=[]
    for job in manifest['jobs']:
        if not re.fullmatch('[a-f0-9]{64}',job['job_id']) or type(job['attempt']) is not int or job['attempt']<1:raise ValueError('Invalid job')
        source=reference_path(manifest_path,job)
        validate_prompt(job['prompt'])
        formatted=tokenizer.apply_chat_template([{'role':'user','content':job['prompt']}],tokenize=False,
                                               add_generation_prompt=True,enable_thinking=False)
        if len(tokenizer(formatted,truncation=False,add_special_tokens=True)['input_ids'])>512:
            raise ValueError('Prompt exceeds token budget')
        path=output/(job['job_id']+'.jpg');metadata=path.with_suffix('.json')
        if path.exists():
            item=json.loads(metadata.read_text())
            if item['job_sha256']!=digest(job) or sha256(path)!=item['image_sha256']:
                raise ValueError('Existing remote attempt changed')
        else:
            mode='edit' if source else 'generate'
            if loaded_mode!=mode:
                # Keep only one model resident on the smaller mini.
                model=None
                import gc
                gc.collect();mx.clear_cache()
                klass=Flux2KleinEdit if source else Flux2Klein
                model=GuardedImageModel(klass(model_config=ModelConfig.from_name(config['model']),
                                            model_path=str(model_path),quantize=config['quantize']))
                loaded_mode=mode
            started=time.monotonic()
            extra={'image_paths':[source]} if source else {}
            result=model.generate_image(prompt=job['prompt'],seed=job['seed'],width=config['width'],height=config['height'],
                                        num_inference_steps=config['steps'],guidance=config['guidance'],**extra)
            temporary=path.with_suffix('.tmp.jpg')
            result.image.convert('RGB').save(temporary,format='JPEG',quality=92,optimize=True)
            item={'job_id':job['job_id'],'job_sha256':digest(job),'image_sha256':sha256(temporary),
                  'seconds':round(time.monotonic()-started,3),'peak_memory_bytes':mx.get_peak_memory()}
            # Metadata first makes interrupted publication recoverable.
            metadata.write_text(canonical(item)+'\n');os.replace(temporary,path)
        images.append(item)
    result={'schema':1,'batch_id':manifest['batch_id'],'manifest_sha256':expected_hash,'images':images}
    temporary=output/'results.tmp.json';temporary.write_text(canonical(result)+'\n');os.replace(temporary,output/'results.json')
    return {'generated':len(images),'seconds':sum(x['seconds'] for x in images),
            'peak_memory_bytes':max(x.get('peak_memory_bytes',0) for x in images)}


def cancel(run,batch_id):
    from bulk_expansion_images import lock,connect,status
    with lock(run,'generation'):
        db=connect(run)
        try:
            schema(db)
            row=db.execute('SELECT state,manifest FROM remote_batches WHERE batch_id=?',(batch_id,)).fetchone()
            if not row or row['state']!='reserved':raise ValueError('Only reserved batches can be cancelled')
            manifest=json.loads(row['manifest'])
            if manifest.get('kind')=='retained-reference-repairs':
                from remote_reference_repairs import cancel_in_lock
                cancel_in_lock(db,batch_id,manifest);return status(run)
            with db:
                for job in json.loads(row['manifest'])['jobs']:
                    owner=db.execute('SELECT batch_id FROM remote_image_jobs WHERE job_id=?',(job['job_id'],)).fetchone()
                    if not owner or owner['batch_id']!=batch_id:raise ValueError('Reservation ownership changed')
                    count=db.execute("UPDATE jobs SET state=?,updated=? WHERE job_id=? AND state='remote_reserved' AND attempts=?",
                                     (job.get('previous_state','pending'),time.time(),job['job_id'],job['attempt']-1)).rowcount
                    if count!=1:raise ValueError('Job changed; cannot release reservation')
                db.execute('DELETE FROM remote_image_jobs WHERE batch_id=?',(batch_id,))
                db.execute("UPDATE remote_batches SET state='cancelled',updated=? WHERE batch_id=?",(time.time(),batch_id))
            return status(run)
        finally:db.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    reserve_p=sub.add_parser('reserve');reserve_p.add_argument('--run',type=Path,required=True);reserve_p.add_argument('--limit',type=int,default=64)
    reserve_p.add_argument('--diverse',action='store_true')
    cancel_p=sub.add_parser('cancel');cancel_p.add_argument('--run',type=Path,required=True);cancel_p.add_argument('--batch-id',required=True)
    import_p=sub.add_parser('import');import_p.add_argument('--run',type=Path,required=True)
    import_p.add_argument('--batch-id',required=True);import_p.add_argument('--results',type=Path,required=True)
    render_p=sub.add_parser('render');render_p.add_argument('--manifest',type=Path,required=True)
    render_p.add_argument('--manifest-sha256',required=True);render_p.add_argument('--model-path',type=Path,required=True)
    render_p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.command=='reserve':
        path=reserve(a.run.resolve(),a.limit,a.diverse)
        print(json.dumps({'manifest':str(path) if path else None,'sha256':sha256(path) if path else None}))
    elif a.command=='import':print(json.dumps(import_results(a.run.resolve(),a.batch_id,a.results.resolve())))
    elif a.command=='cancel':print(json.dumps(cancel(a.run.resolve(),a.batch_id)))
    else:print(json.dumps(render(a.manifest.resolve(),a.manifest_sha256,a.model_path.resolve(),a.output.resolve())))


if __name__=='__main__':main()
