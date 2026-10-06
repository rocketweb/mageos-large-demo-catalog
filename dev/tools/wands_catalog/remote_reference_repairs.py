"""Send retained-photo repairs through existing renderers and ordinary Studio QA.

Only the Studio writes reservations and repair rows. A remote renderer receives
immutable prompts and source bytes, never the ledger or review credentials.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
import uuid

from build_expanded_catalog import canonical, digest
from image_policy import validate_prompt
from prepare_catalog import sha256

KIND = 'retained-reference-repairs'


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS remote_reference_jobs(
        original_sha256 TEXT NOT NULL, design_sha256 TEXT NOT NULL,
        job_id TEXT NOT NULL UNIQUE, batch_id TEXT NOT NULL REFERENCES remote_batches(batch_id),
        attempt INTEGER NOT NULL, PRIMARY KEY(original_sha256,design_sha256))''')


def reserved_targets(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='remote_reference_jobs'").fetchone():return set()
    return {(r[0],r[1]) for r in db.execute("SELECT original_sha256,design_sha256 FROM remote_reference_jobs JOIN remote_batches USING(batch_id) WHERE state='reserved'")}


def kept_images(run):
    feedback = run.parent / 'human-image-review' / 'feedback.sqlite'
    if not feedback.is_file():return set()
    with closing(sqlite3.connect(f'file:{feedback.resolve()}?mode=ro',uri=True)) as db:
        return {r[0] for r in db.execute("SELECT json_extract(i.payload,'$.image_sha256') FROM items i JOIN decisions d ON d.item_id=i.id WHERE d.choice='keep'")}


def history(db,row):
    return [dict(r) for r in db.execute('SELECT * FROM reference_repairs WHERE original_sha256=? AND design_sha256=? ORDER BY attempt',
        (row['image_sha256'],row['design_sha256']))]


def plan(run,db,row,attempts,identity,protected):
    from bulk_expansion_images import CONFIG
    from completion_recovery import reference_plan
    from export_expanded_catalog import accepted_retained
    from repair_expansion_references import repair_strategy
    design=json.loads(row['design'])
    if digest(design)!=row['design_sha256']:raise ValueError('Retained design changed')
    if row['image_sha256'] in protected or any(a['image_sha256'] in protected for a in attempts):return None
    if accepted_retained(db,row,identity):return None
    from authorized_completion import reference_admitted,reference_strategy
    completion=reference_admitted(db,row)
    if (not row['review'] and not completion) or (attempts and not attempts[-1]['review']):return None
    recovery=reference_plan(run,db,row,attempts)
    if len(attempts)>=CONFIG['max_attempts'] and not recovery and not completion:return None
    if [a['attempt'] for a in attempts]!=list(range(1,len(attempts)+1)):raise ValueError('Noncontiguous retained attempt history')
    if attempts and sha256(Path(attempts[-1]['image_path']))!=attempts[-1]['image_sha256']:
        raise ValueError('Latest retained repair changed')
    mode,prompt=reference_strategy(db,row,attempts) or ((recovery['mode'],recovery['prompt']) if recovery else repair_strategy(row,attempts))
    validate_prompt(prompt)
    attempt=len(attempts)+1
    source=Path(row['path']) if mode=='edit' else None
    return {'mode':mode,'prompt':prompt,'attempt':attempt,
        'seed':(int(row['image_sha256'][:8],16)+104729*attempt)%(2**32),
        'reference_sha256':row['image_sha256'] if source else None,'source':source}


def reserve_in_lock(run,db,desc,profile,limit,worker_id):
    from bulk_expansion_images import atomic_json,status
    from repair_expansion_references import queue
    columns={r[1] for r in db.execute('PRAGMA table_info(references_to_review)')}
    if not {'image_sha256','design_sha256','path','design','review'}<=columns:return None
    schema(db);protected=kept_images(run);selected=[];sources={};before=[]
    for row,_ in queue(db,False,run):
        attempts=history(db,row);planned=plan(run,db,row,attempts,desc['review_identity'],protected)
        if planned is None:continue
        if selected and planned['mode']!=selected[0]['target']['mode']:continue
        target={'original_sha256':row['image_sha256'],'design_sha256':row['design_sha256'],
            'row_sha256':digest(dict(row)),'history_sha256':digest(attempts),'mode':planned['mode'],
            'review_identity':desc['review_identity']}
        job_id=digest([KIND,row['image_sha256'],row['design_sha256'],planned['attempt']])
        job={'job_id':job_id,'request_sha256':digest(target),'target':target,
             **{k:planned[k] for k in ('prompt','attempt','seed','reference_sha256')},
             'reference_file':f"references/{planned['reference_sha256']}.jpg" if planned['source'] else None}
        if planned['source']:sources[planned['reference_sha256']]=planned['source']
        selected.append(job);before.append({'row':dict(row),'history':attempts})
        if len(selected)>=limit:break
    if not selected:return None
    batch_id=uuid.uuid4().hex
    manifest={'schema':2,'kind':KIND,'batch_id':batch_id,'candidate_sha256':desc['candidate_sha256'],
        'config':desc['config'],'model_files':desc['model_files'],'packages':desc['packages'],'jobs':selected}
    if profile:manifest.update(schema=3,worker_id=worker_id,renderer=profile)
    directory=run/'remote-batches'/batch_id;directory.mkdir(parents=True)
    for pin,source in sources.items():
        destination=directory/'references'/(pin+'.jpg');destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(source,destination)
        if sha256(destination)!=pin:raise ValueError('Retained source changed during snapshot')
    atomic_json(directory/'rows-before.json',before)
    path=directory/'manifest.json';atomic_json(path,manifest)
    with db:
        db.execute("INSERT INTO remote_batches VALUES(?,?,?,'reserved',NULL,?)",
            (batch_id,canonical(manifest),sha256(path),time.time()))
        db.execute('INSERT INTO remote_batch_workers VALUES(?,?)',(batch_id,worker_id))
        for job in selected:
            target=job['target']
            db.execute('INSERT INTO remote_reference_jobs VALUES(?,?,?,?,?)',
                (target['original_sha256'],target['design_sha256'],job['job_id'],batch_id,job['attempt']))
    atomic_json(directory/'reservation-receipt.json',{'kind':KIND,'batch_id':batch_id,'reserved':len(selected),
        'worker_id':worker_id,'original_images_changed':0,'accepted':0,'max_new_attempts_per_target':1,
        'rollback':'Cancel this reserved batch to remove only its reservation rows; originals and prior repairs remain intact.'})
    status(run);return path


def import_in_lock(run,db,desc,batch,manifest,result,verified,directory):
    from bulk_expansion_images import atomic_json,status
    schema(db)
    result_pin=sha256(directory/'results.json')
    if batch['state']=='imported':
        if result_pin!=batch['results_sha256']:raise ValueError('Previously imported retained result changed')
        return status(run)
    protected=kept_images(run);records=[]
    # Validate the entire packet before publishing any attempt or ledger row.
    for job,item,source in verified:
        target=job['target']
        owner=db.execute('SELECT * FROM remote_reference_jobs WHERE original_sha256=? AND design_sha256=?',
            (target['original_sha256'],target['design_sha256'])).fetchone()
        row=db.execute('SELECT * FROM references_to_review WHERE image_sha256=? AND design_sha256=?',
            (target['original_sha256'],target['design_sha256'])).fetchone()
        if (not owner or owner['batch_id']!=batch['batch_id'] or owner['job_id']!=job['job_id']
                or owner['attempt']!=job['attempt'] or not row or digest(dict(row))!=target['row_sha256']
                or target['review_identity']!=desc['review_identity'] or digest(target)!=job['request_sha256']):
            raise ValueError('Retained reservation or brief changed; no import')
        attempts=history(db,row)
        if digest(attempts)!=target['history_sha256']:raise ValueError('Retained repair history changed; no import')
        planned=plan(run,db,row,attempts,desc['review_identity'],protected)
        if planned is None or any(planned[k]!=job[k] for k in ('prompt','attempt','seed','reference_sha256')) or planned['mode']!=target['mode']:
            raise ValueError('Retained generation eligibility or inputs changed; no import')
        destination=run/'reference-repairs'/digest([row['image_sha256'],row['design_sha256']])/f"attempt-{job['attempt']:02d}.jpg"
        event={'original_sha256':row['image_sha256'],'design_sha256':row['design_sha256'],
            'attempt':job['attempt'],'prompt':job['prompt'],'seed':job['seed'],'mode':target['mode'],
            'config':manifest['config'],'image_sha256':item['image_sha256'],'seconds':item['seconds'],
            'remote_batch_id':batch['batch_id'],'job_sha256':digest(job)}
        if manifest.get('renderer'):
            event['renderer']=manifest['renderer'];event['config']={**manifest['config'],'quantize':manifest['renderer']['quantize']}
        if destination.exists():
            if sha256(destination)!=item['image_sha256'] or (destination.with_suffix('.json').exists()
                    and json.loads(destination.with_suffix('.json').read_text())!=event):
                raise ValueError('Existing retained attempt conflicts; no import')
        elif destination.with_suffix('.json').exists():raise ValueError('Orphan retained metadata; no import')
        records.append((job,item,source,destination,event))
    for job,item,source,destination,event in records:
        destination.parent.mkdir(parents=True,exist_ok=True)
        if not destination.exists():
            temporary=destination.with_suffix('.transfer.jpg');shutil.copyfile(source,temporary)
            if sha256(temporary)!=item['image_sha256']:raise ValueError('Retained image copy changed')
            with temporary.open('rb') as stream:os.fsync(stream.fileno())
            os.link(temporary,destination);temporary.unlink()
        atomic_json(destination.with_suffix('.json'),event)
    with db:
        for job,item,source,destination,event in records:
            target=job['target']
            db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,NULL)',
                (target['original_sha256'],target['design_sha256'],job['attempt'],str(destination.resolve()),item['image_sha256']))
        db.execute("UPDATE remote_batches SET state='imported',results_sha256=?,updated=? WHERE batch_id=?",
            (result_pin,time.time(),batch['batch_id']))
        db.execute('DELETE FROM remote_reference_jobs WHERE batch_id=?',(batch['batch_id'],))
    atomic_json(run/'remote-batches'/batch['batch_id']/'retained-import-receipt.json',
        {'kind':KIND,'batch_id':batch['batch_id'],'imported_for_review':len(records),'accepted':0,
         'original_images_changed':0,'records':[{'target':j['target'],'attempt':j['attempt'],
             'path':str(p.resolve()),'image_sha256':i['image_sha256']} for j,i,_,p,_ in records],
         'rollback':'Preserve files; remove only exact imported repair rows while attempt/path/hash still match and review remains NULL. Later QA or changes require a new scoped inverse.'})
    return status(run)


def cancel_in_lock(db,batch_id,manifest):
    schema(db)
    for job in manifest['jobs']:
        row=db.execute('SELECT batch_id,attempt FROM remote_reference_jobs WHERE job_id=?',(job['job_id'],)).fetchone()
        if not row or row['batch_id']!=batch_id or row['attempt']!=job['attempt']:raise ValueError('Retained reservation ownership changed')
    with db:
        db.execute('DELETE FROM remote_reference_jobs WHERE batch_id=?',(batch_id,))
        db.execute("UPDATE remote_batches SET state='cancelled',updated=? WHERE batch_id=?",(time.time(),batch_id))
