#!/usr/bin/env python3
"""Execute explicitly diagnosed image corrections, preserving every prior attempt."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import time

from bulk_expansion_images import CONFIG, atomic_json, connect, descriptor, lock, status, reference_held
from build_expanded_catalog import canonical, digest
from generate_images import append_event
from image_policy import GuardedImageModel, validate_prompt
from prepare_catalog import sha256
from run_catalog_media_pilot import check_token_budget


def validate(db, records):
    items=[]
    for item in records:
        if item['scope'] not in ('job','reference') or item['mode'] not in ('generate','edit'):
            raise ValueError('Unsupported correction')
        if not item.get('diagnosis') or not item.get('strategy_change'):raise ValueError('Concrete diagnosis and changed strategy required')
        validate_prompt(item['prompt'])
        if item['scope']=='job':
            row=db.execute('SELECT * FROM jobs WHERE job_id=?',(item['job_id'],)).fetchone()
            if row is None or row['state'] not in ('rejected','review_required','review_error'):raise ValueError('Job must be held before correction')
            if row['image_sha256']!=item['expected_image_sha256']:raise ValueError('Stale correction')
            if sha256(Path(row['image_path']))!=item['expected_image_sha256']:raise ValueError('Candidate changed')
            key=item['job_id'];attempt=row['attempts']+1
        else:
            row=db.execute('SELECT * FROM references_to_review WHERE image_sha256=? AND design_sha256=?',
                           (item['original_sha256'],item['design_sha256'])).fetchone()
            if row is None or not row['review'] or (json.loads(row['review'])['decision']!='rejected'
                    and not reference_held(db,row['image_sha256'])):raise ValueError('Reference must be rejected')
            key=digest([item['original_sha256'],item['design_sha256']])
            attempt=db.execute('SELECT COALESCE(MAX(attempt),0)+1 FROM reference_repairs WHERE original_sha256=? AND design_sha256=?',
                               (item['original_sha256'],item['design_sha256'])).fetchone()[0]
        if item['mode']=='edit':
            if sha256(Path(item['reference_path']))!=item['reference_sha256']:raise ValueError('Correction source changed')
        items.append((item,key,attempt))
    return items


def execute(run, manifest, apply=False):
    desc=descriptor(run);records=json.loads(manifest.read_text())['corrections']
    with ExitStack() as locks:
        for name in ('supervisor','generation','review','reference-review','reference-repair-review'):locks.enter_context(lock(run,name))
        db=connect(run);items=validate(db,records)
        receipt=run/('correction-'+sha256(manifest)+'.json')
        if receipt.exists():raise ValueError('Correction already executed')
        if not apply:db.close();return {'validated':len(items),'applied':False}
        os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
        from transformers import Qwen2TokenizerFast
        from mflux.models.common.config.model_config import ModelConfig
        from mflux.models.flux2.variants import Flux2Klein,Flux2KleinEdit
        snapshot=Path(desc['model_snapshot'])
        for name,pin in desc['model_files'].items():
            if sha256(snapshot/name)!=pin['sha256']:raise ValueError('Pinned model changed')
        tokenizer=Qwen2TokenizerFast.from_pretrained(snapshot/'tokenizer',local_files_only=True)
        models={};completed=[]
        for item,key,attempt in items:
            prompt=item['prompt'];check_token_budget(prompt,tokenizer);mode=item['mode']
            if mode not in models:
                klass=Flux2Klein if mode=='generate' else Flux2KleinEdit
                models[mode]=GuardedImageModel(klass(model_config=ModelConfig.from_name(CONFIG['model']),model_path=str(snapshot),quantize=CONFIG['quantize']))
            directory=run/('candidates' if item['scope']=='job' else 'reference-repairs')/key
            directory.mkdir(parents=True,exist_ok=True);path=directory/f'attempt-{attempt:02d}.jpg'
            if path.exists():raise ValueError('Prior correction bytes cannot be overwritten')
            args={'prompt':prompt,'seed':item['seed'],'width':CONFIG['width'],'height':CONFIG['height'],
                  'num_inference_steps':CONFIG['steps'],'guidance':CONFIG['guidance']}
            if mode=='edit':args['image_paths']=[Path(item['reference_path'])]
            result=models[mode].generate_image(**args)
            temp=path.with_suffix('.tmp.jpg');result.image.convert('RGB').save(temp,format='JPEG',quality=92,optimize=True)
            os.link(temp,path);temp.unlink();pin=sha256(path)
            event={**item,'attempt':attempt,'image_sha256':pin,'image_path':str(path.resolve()),'correction_manifest_sha256':sha256(manifest),'config':CONFIG}
            atomic_json(path.with_suffix('.json'),event)
            with db:
                if item['scope']=='job':
                    db.execute("UPDATE jobs SET state='generated',attempts=?,image_path=?,image_sha256=?,review=NULL,error=NULL,updated=? WHERE job_id=?",
                               (attempt,str(path.resolve()),pin,time.time(),key))
                    db.execute("DELETE FROM review_failures WHERE scope='job' AND item=?",(key,))
                else:
                    db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,NULL)',(item['original_sha256'],item['design_sha256'],attempt,str(path.resolve()),pin))
            append_event(run/'correction-events.jsonl',event);completed.append(event);status(run)
        atomic_json(receipt,{'completed':completed,'acceptances_granted':0});db.close()
    return {'generated':len(completed),'applied':True,'review_required':True}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--apply',action='store_true')
    a=p.parse_args();print(json.dumps(execute(a.run.resolve(),a.manifest.resolve(),a.apply),indent=2))
