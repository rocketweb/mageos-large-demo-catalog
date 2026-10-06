#!/usr/bin/env python3
"""Checkpointed local catalog image generation and review. Never imports a store."""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
import fcntl
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time

from build_expanded_catalog import canonical, digest, csv_rows
from generate_images import append_event
from image_policy import GuardedImageModel, validate_prompt, visual_text, product_prompt, NO_MEASUREMENTS
from image_review import Reviewer, ReviewUnavailable, ReviewServiceUnavailable, review_identity
from prepare_catalog import sha256
import component_review
from run_catalog_media_pilot import check_token_budget

CONFIG = {'model':'flux2-klein-4b','quantize':4,'width':768,'height':768,'steps':4,'guidance':1.0,'max_attempts':3}


def atomic_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix=path.name+'.',suffix='.tmp',delete=False) as stream:
        temporary=Path(stream.name)
        stream.write(json.dumps(value,indent=2,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def connect(run):
    db=sqlite3.connect(run/'ledger.sqlite',timeout=30)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('''CREATE TABLE IF NOT EXISTS reference_repairs(
        original_sha256 TEXT NOT NULL, design_sha256 TEXT NOT NULL, attempt INTEGER NOT NULL,
        image_path TEXT NOT NULL, image_sha256 TEXT NOT NULL, review TEXT,
        PRIMARY KEY(original_sha256,design_sha256,attempt))''')
    db.execute('''CREATE TABLE IF NOT EXISTS manual_reviews(job_id TEXT NOT NULL,
        image_sha256 TEXT NOT NULL, decision TEXT NOT NULL, observations TEXT NOT NULL,
        PRIMARY KEY(job_id,image_sha256))''')
    db.execute('CREATE TABLE IF NOT EXISTS manual_reference_reviews(image_sha256 TEXT PRIMARY KEY,observations TEXT NOT NULL)')
    db.execute('''CREATE TABLE IF NOT EXISTS review_failures(
        scope TEXT NOT NULL, item TEXT NOT NULL, failures INTEGER NOT NULL, evidence TEXT NOT NULL,
        PRIMARY KEY(scope,item))''')
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='job_references'").fetchone():
        db.execute('CREATE INDEX IF NOT EXISTS job_references_original ON job_references(image_sha256,design_sha256)')
        db.execute('CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(pilot,state,ordinal)')
    return db


def reference_design(row):
    return {'subject':visual_text(row['name']),
            'product_class':row.get('wands_product_class',''),
            'material':row.get('lab_spec_material') or row.get('lab_spec_frame_material') or '',
            'color':row.get('color') or row.get('lab_spec_color') or row.get('wands_finish') or '',
            'construction':'Existing synthetic catalog reference; inspect its visible construction and exact sale unit.'}


def initialize(candidate, baseline, run, model_snapshot, vision_model):
    candidate=candidate.resolve();baseline=baseline.resolve();run=run.resolve();model_snapshot=model_snapshot.resolve()
    m=json.loads((candidate/'manifest.json').read_text())
    for name, pin in m['outputs'].items():
        if sha256(candidate/name)!=pin:raise ValueError('Candidate changed: '+name)
    files={str(p.relative_to(model_snapshot)):{'sha256':sha256(p),'bytes':p.stat().st_size}
           for p in sorted(model_snapshot.rglob('*')) if p.is_file()}
    if not files:raise ValueError('No cached image-model files')
    descriptor={'schema':1,'candidate':str(candidate),'candidate_sha256':sha256(candidate/'manifest.json'),
                'baseline':str(baseline),'config':CONFIG,'model_snapshot':str(model_snapshot),'model_files':files,
                'vision_model':vision_model,'review_identity':review_identity(vision_model),
                'packages':{p:version(p) for p in ('mflux','mlx','Pillow','transformers')},
                'jobs_sha256':sha256(candidate/'image-jobs.jsonl')}
    if (run/'run.json').exists():
        if json.loads((run/'run.json').read_text())!=descriptor:raise ValueError('Immutable run inputs changed')
        return status(run)
    if run.exists() and any(run.iterdir()):raise ValueError('Run directory is not empty')
    run.mkdir(parents=True,exist_ok=True,mode=0o700)
    db=connect(run)
    db.executescript('''
        CREATE TABLE jobs(job_id TEXT PRIMARY KEY, ordinal INTEGER UNIQUE NOT NULL, request TEXT NOT NULL,
            pilot INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            image_path TEXT, image_sha256 TEXT, review TEXT, error TEXT, updated REAL);
        CREATE TABLE references_to_review(image_sha256 TEXT NOT NULL, design_sha256 TEXT NOT NULL,
            path TEXT NOT NULL, design TEXT NOT NULL, review TEXT, PRIMARY KEY(image_sha256,design_sha256));
        CREATE TABLE job_references(job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),image_sha256 TEXT NOT NULL,
            design_sha256 TEXT NOT NULL);
        CREATE TABLE job_dependencies(job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),
            source_job_id TEXT NOT NULL REFERENCES jobs(job_id));
    ''')
    pilot=set(json.loads((candidate/'pilot.json').read_text())['job_ids'])
    source={r['sku']:r for file in ('1-simple.csv','2-configurable.csv','3-bundle.csv') for r in csv_rows(baseline/'data'/file)}
    with db:
        for ordinal,line in enumerate((candidate/'image-jobs.jsonl').open()):
            job=json.loads(line);validate_prompt(job['prompt'])
            db.execute('INSERT INTO jobs(job_id,ordinal,request,pilot,updated) VALUES(?,?,?,?,?)',
                       (job['job_id'],ordinal,canonical(job),int(job['job_id'] in pilot),time.time()))
            if job['reference']:
                ref=job['reference']
                if ref.get('job_id'):
                    db.execute('INSERT INTO job_dependencies VALUES(?,?)',(job['job_id'],ref['job_id']))
                    continue
                row=source[ref['sku']]
                design=reference_design(row)
                dh=digest(design);path=baseline/ref['file']
                if not path.is_file() or sha256(path)!=ref['sha256']:raise ValueError('Missing or changed reference: '+ref['sku'])
                db.execute('INSERT OR IGNORE INTO references_to_review VALUES(?,?,?,?,NULL)',(ref['sha256'],dh,str(path),canonical(design)))
                db.execute('INSERT INTO job_references VALUES(?,?,?)',(job['job_id'],ref['sha256'],dh))
    db.close();atomic_json(run/'run.json',descriptor)
    return status(run)


def descriptor(run):
    value=json.loads((run/'run.json').read_text())
    candidate=Path(value['candidate'])
    if sha256(candidate/'manifest.json')!=value['candidate_sha256'] or sha256(candidate/'image-jobs.jsonl')!=value['jobs_sha256']:
        raise ValueError('Candidate changed after initialization')
    if value['config']!=CONFIG or value['review_identity']!=review_identity(value['vision_model']):
        raise ValueError('Generation or review policy changed; prepare a new run')
    if any(version(package)!=pinned for package,pinned in value['packages'].items()):
        raise ValueError('Local generation environment changed during the run')
    return value


def status(run):
    db=connect(run)
    states={r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) n FROM jobs GROUP BY state')}
    pilot={r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) n FROM jobs WHERE pilot=1 GROUP BY state')}
    refs=Counter()
    for r in db.execute('SELECT review FROM references_to_review'):
        refs['pending' if r['review'] is None else json.loads(r['review'])['decision']]+=1
    repairs=Counter('pending' if r['review'] is None else json.loads(r['review'])['decision']
                    for r in db.execute('SELECT review FROM reference_repairs'))
    value={'states':states,'pilot':pilot,'references':dict(refs),'reference_repairs':dict(repairs),
           'total_jobs':sum(states.values()),'updated_at':time.time()}
    db.close();atomic_json(run/'status.json',value)
    return value


def current_accepted(row, expected_identity):
    if row['state']!='accepted' or not row['review'] or not row['image_path']:return False
    review=json.loads(row['review']);path=Path(row['image_path'])
    if review.get('direct_riser_acceptance'):
        from direct_riser_acceptance import valid as valid_riser
        if not valid_riser(review,json.loads(row['request']),expected_identity):return False
    if review.get('human_keep'):
        from human_keep_acceptance import valid
        quality_ok=valid(row,review,expected_identity)
    else:quality_ok=component_review.accepted(review,json.loads(row['request']).get('design',{}))
    return (review['decision']=='accepted' and review['review_identity']==expected_identity and path.is_file()
            and sha256(path)==row['image_sha256']==review['image_sha256']
            and review['design_sha256']==json.loads(row['request'])['design_sha256']
            and quality_ok)


def reference_held(db,image_sha256):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='manual_reference_reviews'").fetchone():return False
    return bool(db.execute('SELECT 1 FROM manual_reference_reviews WHERE image_sha256=?',(image_sha256,)).fetchone())


def reject_reference(run,image_sha256,observations):
    if not observations or not observations.strip():raise ValueError('Direct visual observations required')
    with lock(run,'generation'),lock(run,'reference-review'),lock(run,'reference-repair-review'),lock(run,'review'):
        db=connect(run)
        rows=list(db.execute('SELECT image_path path FROM reference_repairs WHERE image_sha256=?',(image_sha256,)))
        rows+=list(db.execute('SELECT path FROM references_to_review WHERE image_sha256=?',(image_sha256,)))
        if not rows or any(sha256(Path(r['path']))!=image_sha256 for r in rows):raise ValueError('No intact reference bytes')
        with db:db.execute('INSERT OR REPLACE INTO manual_reference_reviews VALUES(?,?)',(image_sha256,observations))
        append_event(run/'manual-reference-reviews.jsonl',{'image_sha256':image_sha256,'decision':'rejected','observations':observations})
        db.close()
    return status(run)


def accepted_reference(db, job, identity):
    if not job['reference']: return None
    if job['reference'].get('job_id'):
        source=db.execute('SELECT * FROM jobs WHERE job_id=?',(job['reference']['job_id'],)).fetchone()
        if source is None or not current_job_accepted(db,source,identity):return False
        return Path(source['image_path'])
    rr=db.execute('SELECT r.* FROM references_to_review r JOIN job_references j USING(image_sha256,design_sha256) WHERE j.job_id=?',(job['job_id'],)).fetchone()
    if rr is None:return False
    review=json.loads(rr['review'] or '{}');reference=Path(rr['path'])
    if review.get('decision')!='accepted' or reference_held(db,rr['image_sha256']) or not component_review.accepted(review,json.loads(rr['design'])):
        for replacement in db.execute('SELECT * FROM reference_repairs WHERE original_sha256=? AND design_sha256=? ORDER BY attempt DESC',
                                      (rr['image_sha256'],rr['design_sha256'])):
            if not replacement['review'] or reference_held(db,replacement['image_sha256']):continue
            evidence=json.loads(replacement['review']);path=Path(replacement['image_path'])
            if (evidence['decision']=='accepted' and evidence['review_identity']==identity
                    and evidence['design_sha256']==rr['design_sha256']
                    and component_review.accepted(evidence,json.loads(rr['design']))
                    and sha256(path)==replacement['image_sha256']==evidence['image_sha256']):return path
        return False
    if (review['review_identity']!=identity or sha256(reference)!=rr['image_sha256']
            or review['image_sha256']!=rr['image_sha256'] or review['design_sha256']!=rr['design_sha256']):
        raise ValueError('Reference acceptance became stale')
    return reference


def current_job_accepted(db, row, identity):
    if not current_accepted(row,identity):return False
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='manual_reviews'").fetchone():
        evidence=db.execute('SELECT decision FROM manual_reviews WHERE job_id=? AND image_sha256=?',
                            (row['job_id'],row['image_sha256'])).fetchone()
        if evidence and evidence['decision']!='accepted':return False
    job=json.loads(row['request'])
    # An exact current Keep approves these pixels and this complete request.
    # A later source repair cannot revoke that independent human decision.
    if json.loads(row['review']).get('human_keep'):return True
    if not job.get('reference'):return True
    reference=accepted_reference(db,job,identity)
    return bool(reference and json.loads(row['review']).get('reference_sha256')==sha256(reference))


def retry_prompt(job):
    design=job['design'];color=design.get('color','')
    finish=('an opaque painted '+color+' finish, with material texture beneath the coating'
            if design.get('material') in {'Solid Wood','Engineered Wood','Bamboo','Metal'}
            else 'the specified '+color+' color throughout its principal surfaces')
    detail=(' Show the two solid mounting brackets clearly behind the planter trough.'
            if 'railing planter' in design.get('subject','') else '')
    return product_prompt('Correct this candidate image to match the intended product. '+
                          job['prompt'].replace(NO_MEASUREMENTS,'')+
                          ' The product must have '+finish+'. Correct any disconnected, extra or missing parts.'+detail)


def reject_image(run,job_id,observations):
    if not observations or not observations.strip():raise ValueError('Direct visual observations required')
    # Do not race a generation or review worker while invalidating an image.
    with lock(run,'generation'),lock(run,'review'):
        db=connect(run);row=db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()
        if row is None or not row['image_path'] or sha256(Path(row['image_path']))!=row['image_sha256']:
            raise ValueError('No intact generated candidate to reject')
        with db:
            db.execute('INSERT OR REPLACE INTO manual_reviews VALUES(?,?,?,?)',
                       (job_id,row['image_sha256'],'rejected',observations))
            db.execute("UPDATE jobs SET state='rejected',updated=? WHERE job_id=?",(time.time(),job_id))
        append_event(run/'manual-reviews.jsonl',{'job_id':job_id,'image_sha256':row['image_sha256'],
                     'decision':'rejected','observations':observations,'reviewer':'direct visual inspection'})
        db.close()
    return status(run)


def accept_ocr_review(run,job_id,image_sha256,observations):
    if not observations or not image_sha256:raise ValueError('Exact image hash and direct observations required')
    with lock(run,'generation'),lock(run,'review'):
        desc=descriptor(run);db=connect(run);row=db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()
        if (row is None or row['state']!='review_required' or row['image_sha256']!=image_sha256
                or sha256(Path(row['image_path']))!=image_sha256):raise ValueError('No matching held image')
        evidence=json.loads(row['review'])
        if (not evidence['vision']['acceptable'] or not evidence['ocr_flags']
                or evidence['review_identity']!=desc['review_identity']):
            raise ValueError('Direct OCR resolution cannot override a failed or uncertain vision review')
        resolution={'image_sha256':image_sha256,'observations':observations,'reviewer':'direct visual inspection'}
        evidence['manual_ocr_resolution']=resolution;evidence['decision']='accepted'
        evidence=hold_half_round_geometry(evidence,json.loads(row['request']).get('design',{}))
        with db:
            db.execute('INSERT OR REPLACE INTO manual_reviews VALUES(?,?,?,?)',(job_id,image_sha256,'accepted',observations))
            db.execute("UPDATE jobs SET state=?,review=?,updated=? WHERE job_id=?",(evidence['decision'],canonical(evidence),time.time(),job_id))
        append_event(run/'manual-reviews.jsonl',{'job_id':job_id,'decision':'accepted','scope':'OCR false positive only',**resolution})
        db.close()
    return status(run)


def hold_half_round_geometry(result,design):
    """Require direct shape inspection after the general reviewer falsely passed round tops."""
    if (result['decision']!='accepted' or design.get('profile')!='balcony-table'
            or design.get('construction')!='half-round top and straight legs'):
        return result
    return {**result,'decision':'review_required','geometry_hold':{
        'version':'half-round-geometry-v1','required':'visible straight rear tabletop edge'}}


def geometry_ocr_clear(evidence):
    if not evidence.get('ocr_flags'):return True
    resolution=evidence.get('manual_ocr_resolution') or {}
    return bool(resolution.get('image_sha256')==evidence.get('image_sha256')
                and resolution.get('reviewer')=='direct visual inspection'
                and resolution.get('observations','').strip())


def awaiting_direct_geometry_review(record):
    if record['state']!='review_required' or not record['review']:return False
    evidence=json.loads(record['review'])
    return bool(evidence.get('geometry_hold',{}).get('version')=='half-round-geometry-v1'
                and evidence.get('vision',{}).get('acceptable') and geometry_ocr_clear(evidence))


def accept_geometry_review(run,job_id,image_sha256,observations):
    if (not image_sha256 or 'straight rear edge' not in observations.lower()
            or 'curved front' not in observations.lower()):
        raise ValueError('Direct observations must describe the straight rear edge and curved front')
    with lock(run,'generation'),lock(run,'review'):
        desc=descriptor(run);db=connect(run)
        try:
            row=db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()
            if (row is None or row['state']!='review_required' or row['image_sha256']!=image_sha256
                    or not row['image_path'] or sha256(Path(row['image_path']))!=image_sha256):
                raise ValueError('No matching held image')
            job=json.loads(row['request']);design=job['design'];evidence=json.loads(row['review'])
            if (design.get('profile')!='balcony-table' or design.get('construction')!='half-round top and straight legs'
                    or evidence.get('geometry_hold',{}).get('version')!='half-round-geometry-v1'
                    or evidence.get('review_identity')!=desc['review_identity']
                    or evidence.get('image_sha256')!=image_sha256
                    or evidence.get('design_sha256')!=job['design_sha256']
                    or not evidence.get('vision',{}).get('acceptable') or not geometry_ocr_clear(evidence)
                    or not component_review.accepted(evidence,design)):
                raise ValueError('Geometry resolution cannot override another QA failure')
            existing=db.execute('SELECT decision FROM manual_reviews WHERE job_id=? AND image_sha256=?',
                                (job_id,image_sha256)).fetchone()
            if existing and existing['decision']=='rejected':raise ValueError('Image was directly rejected')
            reference=accepted_reference(db,job,desc['review_identity'])
            if reference is False or (reference and evidence.get('reference_sha256')!=sha256(reference)):
                raise ValueError('Source image is no longer accepted')
            resolution={'image_sha256':image_sha256,'observations':observations,'reviewer':'direct visual inspection'}
            evidence['geometry_hold']['direct_resolution']=resolution;evidence['decision']='accepted'
            with db:
                db.execute('INSERT OR REPLACE INTO manual_reviews VALUES(?,?,?,?)',
                           (job_id,image_sha256,'accepted',observations))
                db.execute("UPDATE jobs SET state='accepted',review=?,updated=? WHERE job_id=?",
                           (canonical(evidence),time.time(),job_id))
            append_event(run/'manual-reviews.jsonl',{'job_id':job_id,'decision':'accepted',
                         'scope':'half-round tabletop geometry',**resolution})
        finally:db.close()
    return status(run)


def require_bulk_gate(run, db, desc):
    receipt=run/'pilot-acceptance.json'
    if not receipt.is_file():raise ValueError('Bulk generation requires a reviewed pilot acceptance receipt')
    acceptance=json.loads(receipt.read_text())
    actual={r['job_id']:r['image_sha256'] for r in db.execute('SELECT * FROM jobs WHERE pilot=1')
            if current_job_accepted(db,r,desc['review_identity'])}
    from category_image_corrections import original_pilot_image
    for row in db.execute('SELECT * FROM jobs WHERE pilot=1'):
        if actual.get(row['job_id'])!=acceptance.get('images',{}).get(row['job_id']):
            historical=original_pilot_image(db,row,desc['review_identity'])
            if historical:actual[row['job_id']]=historical
    total=db.execute('SELECT COUNT(*) FROM jobs WHERE pilot=1').fetchone()[0]
    if len(actual)!=total or acceptance.get('images')!=actual or acceptance.get('candidate_sha256')!=desc['candidate_sha256']:
        raise ValueError('Pilot acceptance is incomplete or stale')
    if not acceptance.get('visual_review_receipt_sha256'):raise ValueError('Pilot contact-sheet review missing')


@contextlib.contextmanager
def lock(run, name):
    with (run/(name+'.lock')).open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def retry_allowed(run,record,job,reference):
    if record['attempts']<CONFIG['max_attempts']:return True
    # A repaired source is a materially different input. Keep prior attempts,
    # but allow a fresh bounded budget for that exact accepted source hash.
    if not job.get('reference') or not reference:return False
    pin=sha256(reference);directory=run/'candidates'/job['job_id']
    history=[json.loads(p.read_text()) for p in sorted(directory.glob('attempt-*.json'))]
    if len(history)!=record['attempts']:return False
    if sum(item.get('reference_sha256')==pin for item in history)<CONFIG['max_attempts']:return True
    from source_prompt_recovery import allowed
    return allowed(run,record,job,reference,history)


def requeue_changed_sources(run,db,identity,pilot=False):
    changed=0
    selection=' AND pilot=1' if pilot else ''
    rows=list(db.execute("SELECT * FROM jobs WHERE state IN ('accepted','review_required','review_error') AND review IS NOT NULL"+selection))
    for row in rows:
        # Source revisions must never overwrite a human-kept image. A stale
        # source still blocks export through current_job_accepted until reviewed.
        from human_keep_acceptance import is_kept
        if json.loads(row['review']).get('human_keep'):continue
        job=json.loads(row['request'])
        if not job.get('reference'):continue
        source=accepted_reference(db,job,identity)
        if row['review']:evidence=json.loads(row['review'])
        else:
            metadata=Path(row['image_path']).with_suffix('.json')
            if not metadata.is_file():continue
            evidence=json.loads(metadata.read_text())
            if not evidence.get('reference_sha256'):continue
        # A disproved source must also queue its dependents. They remain
        # blocked from rendering until a clean source is accepted, while their
        # existing pixels and prior review evidence remain unchanged.
        pin=sha256(source) if source else None
        if evidence.get('reference_sha256')==pin:continue
        # Only changed inputs can cause a mutation. Most of the catalog is
        # unchanged; repeatedly scanning the live feedback JSON for every row
        # held the scheduling lock for minutes without doing useful work.
        # Check the live Keep immediately before the actual state change.
        if is_kept(run,row):continue
        with db:db.execute("UPDATE jobs SET state='rejected',updated=? WHERE job_id=?",(time.time(),row['job_id']))
        append_event(run/'reference-revisions.jsonl',{'job_id':row['job_id'],
                     'previous_reference_sha256':evidence.get('reference_sha256'),'current_reference_sha256':pin,
                     'prior_state':row['state'],'prior_updated':row['updated'],
                     'action':'regenerate from corrected accepted source' if source else 'wait for a clean source, then regenerate'})
        changed+=1
    return changed


def initial_generation_prompt(job):
    """The same first-attempt prompt for local and remote standalone images."""
    prompt=job['prompt'];design=job['design']
    if design.get('material') in {'Solid Wood','Engineered Wood','Bamboo','Metal'} and design.get('color') in {'Black','White','Green','Navy','Blue','Red','Cream'}:
        prompt=product_prompt(prompt.replace(NO_MEASUREMENTS,'')+' The main product surfaces have an opaque '+design['color']+' painted finish over the '+design['material']+' structure. Preserve subtle physical texture beneath the coating; do not substitute the unpainted natural material color.')
    validate_prompt(prompt)
    return prompt


def source_recolor_prompt(job):
    """Change the requested finish using only parts present in the clean source."""
    design=job['design'];color=visual_text(job['reference'].get('value') or design['color'])
    subject=' '.join(design.get(k,'') for k in ('subject','profile','product_class')).lower()
    material=(design.get('material','')+' '+subject).lower()
    upholstered=(any(part in subject for part in ('chair','sofa','couch','loveseat','ottoman','pouf','bench','headboard','bed'))
                 and any(hint in material for hint in ('upholstered','tufted','fabric','velvet','linen','polyester','cotton','leather','boucle','suede')))
    surfaces='upholstered surfaces' if upholstered else 'product surfaces'
    detail=(' Keep the source upholstery texture and detailing. Leave any exposed frame, legs and feet '
            'in their original colors and materials.' if upholstered else '')
    return product_prompt(
        'Recolor only the '+surfaces+' in the approved source photograph to '+color+'. '
        'Preserve the exact source product: silhouette, construction, component count, proportions, '
        'material texture, surface pattern and viewpoint. '
        'Preserve only components already present in the source. Do not add parts or decorations. '
        'Keep all empty openings and gaps empty. '
        'Keep the original background, lighting and secondary hardware unchanged. '
        'Retain visible material detail beneath the requested color or finish.'+detail)


def generation_input(run,db,record,desc):
    """One source, prompt and retry policy shared by Studio and remote workers."""
    from human_keep_acceptance import is_kept
    if is_kept(run,record):return None
    from authorized_completion import job_plan
    handled,planned=job_plan(run,db,record,desc)
    if handled:return planned
    if awaiting_direct_geometry_review(record):return None
    from category_image_corrections import plan_generation as category_plan
    handled,planned=category_plan(run,db,record,desc)
    if handled:return planned
    from human_keep_acceptance import is_kept
    if is_kept(run,record):return None
    job=json.loads(record['request']);validate_prompt(job['prompt'])
    from feedback_reprocessing import plan_generation
    handled,planned=plan_generation(run,db,record,desc)
    if handled:return planned
    reference=accepted_reference(db,job,desc['review_identity'])
    if reference is False:return None
    if not retry_allowed(run,record,job,reference):return None
    prompt=job['prompt']
    if reference is None and record['state'] not in {'rejected','review_required'}:
        prompt=initial_generation_prompt(job)
    if reference and job.get('reference'):
        # This input is the accepted original, not the defective prior candidate.
        # Naming nonexistent parts or fabric here made the renderer invent them.
        prompt=source_recolor_prompt(job)
    elif record['state'] in {'rejected','review_required'}:
        prompt=retry_prompt(job)
        manual=db.execute("SELECT observations FROM manual_reviews WHERE job_id=? AND image_sha256=? AND decision='rejected'",
                          (job['job_id'],record['image_sha256'])).fetchone()
        if manual:
            prompt=product_prompt(prompt.replace(NO_MEASUREMENTS,'')+' Correct the directly observed defect: '+manual['observations'])
        if reference is None:
            reference=Path(record['image_path'])
            if sha256(reference)!=record['image_sha256']:raise ValueError('Rejected candidate changed before repair')
    validate_prompt(prompt)
    attempt=record['attempts']+1
    return {'prompt':prompt,'reference':reference,'attempt':attempt,
            'seed':(job['seed']+(attempt-1)*104729)%(2**32)}


def remote_import_pending(run,db):
    """Yield scheduling priority to received packets, without accepting them."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='remote_batches'").fetchone():return False
    return any((run/'remote-batches'/row[0]/'returned'/'results.json').is_file()
               for row in db.execute("SELECT batch_id FROM remote_batches WHERE state='reserved'"))


def generation_checkpoint_requested(run,db):
    if (run/'STOP').exists() or remote_import_pending(run,db):return True
    # A ready remote renderer also needs this lock to reserve its next batch.
    # A recent heartbeat and held coordinator lock exclude stale/idle workers.
    for path in run.glob('remote-*-state.json'):
        try:
            state=json.loads(path.read_text())
            if state.get('state')!='waiting_for_catalog_worker' or not 0<=time.time()-state.get('updated',0)<=15:continue
            worker=path.name[len('remote-'):-len('-state.json')]
            coordinator='remote-coordinator'+('' if worker=='worker' else '-'+worker)
            if not (run/(coordinator+'.lock')).is_file():continue
            try:
                with lock(run,coordinator):pass
            except BlockingIOError:return True
        except (OSError,ValueError,TypeError):continue
    return False


def generate(run, *, pilot=False, limit=0, visual_receipt=None, job_id=None):
    if job_id is not None and not re.fullmatch(r'[a-f0-9]{64}',job_id):raise ValueError('Invalid exact job ID')
    with lock(run,'generation'):
        desc=descriptor(run);db=connect(run)
        admitted=None
        if visual_receipt:
            if pilot:raise ValueError('Profile admission is for non-pilot generation only')
            from profile_admission import admitted_profiles,profile_key
            admitted=admitted_profiles(db,desc,visual_receipt)
            atomic_json(run/'profile-admission.json',{'candidate_sha256':desc['candidate_sha256'],
                'visual_receipt_sha256':sha256(visual_receipt),'profiles':sorted(admitted),'updated':time.time()})
            if not admitted:db.close();return status(run)
        elif not pilot:require_bulk_gate(run,db,desc)
        if generation_checkpoint_requested(run,db):
            db.close();logging.info('Yielding generation at a safe checkpoint');return status(run)
        os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
        from transformers import Qwen2TokenizerFast
        from mflux.models.common.config.model_config import ModelConfig
        from mflux.models.flux2.variants import Flux2Klein, Flux2KleinEdit
        snapshot=Path(desc['model_snapshot'])
        for name, pinned in desc['model_files'].items():
            source=snapshot/name
            if not source.is_file() or source.stat().st_size!=pinned['bytes'] or sha256(source)!=pinned['sha256']:
                raise ValueError('Pinned local image model changed')
        tokenizer=Qwen2TokenizerFast.from_pretrained(snapshot/'tokenizer',local_files_only=True)
        # A stopped process cannot remain the owner after acquiring the same lock.
        with db:db.execute("UPDATE jobs SET state='interrupted' WHERE state='generating'")
        requeue_changed_sources(run,db,desc['review_identity'],pilot)
        selection="AND pilot=1" if pilot else ('AND pilot=0' if admitted is not None else '')
        exact=' AND job_id=?' if job_id else ''
        from authorized_completion import policy
        order='attempts,ordinal' if policy(db,desc) else 'ordinal'
        queue=list(db.execute("SELECT * FROM jobs WHERE state IN ('pending','rejected','review_required','interrupted') "+selection+exact+' ORDER BY '+order,(job_id,) if job_id else ()))
        models={};completed=0;blocked=0
        for record in queue:
            if generation_checkpoint_requested(run,db):
                logging.info('Yielding generation after %s complete images',completed);break
            if limit and completed>=limit:break
            job=json.loads(record['request'])
            if admitted is not None and profile_key(job) not in admitted:continue
            validate_prompt(job['prompt']);check_token_budget(job['prompt'],tokenizer)
            planned=generation_input(run,db,record,desc)
            if planned is None:blocked+=1;continue
            reference=planned['reference'];prompt=planned['prompt']
            check_token_budget(prompt,tokenizer)
            mode='edit' if reference else 'generate'
            if mode not in models:
                klass=Flux2KleinEdit if reference else Flux2Klein
                logging.info('Loading local %s model',mode)
                models[mode]=GuardedImageModel(klass(model_config=ModelConfig.from_name(CONFIG['model']),model_path=str(snapshot),quantize=CONFIG['quantize']))
            attempt=planned['attempt'];directory=run/'candidates'/job['job_id'];directory.mkdir(parents=True,exist_ok=True)
            image_path=directory/f'attempt-{attempt:02d}.jpg'
            if image_path.exists():raise ValueError('Refusing to overwrite an existing attempt')
            with db:db.execute("UPDATE jobs SET state='generating',attempts=?,updated=? WHERE job_id=?",(attempt,time.time(),job['job_id']))
            started=time.monotonic()
            runtime={'seed':planned['seed'],'prompt':prompt,
                     'width':CONFIG['width'],'height':CONFIG['height'],'guidance':CONFIG['guidance'],'num_inference_steps':CONFIG['steps']}
            if reference:runtime['image_paths']=[reference]
            try:
                result=models[mode].generate_image(**runtime)
                temporary=image_path.with_suffix('.tmp.jpg')
                result.image.convert('RGB').save(temporary,format='JPEG',quality=92,optimize=True)
                with temporary.open('rb') as stream:os.fsync(stream.fileno())
                os.link(temporary,image_path);temporary.unlink()
                image_hash=sha256(image_path)
                event={'status':'generated','job_id':job['job_id'],'attempt':attempt,'image_sha256':image_hash,
                       'request_sha256':digest(job),'actual_prompt':prompt,'config':CONFIG,'seed':runtime['seed'],
                       'reference_sha256':sha256(reference) if reference else None,'seconds':round(time.monotonic()-started,3)}
                atomic_json(image_path.with_suffix('.json'),event)
                with db:db.execute("UPDATE jobs SET state='generated',image_path=?,image_sha256=?,review=NULL,error=NULL,updated=? WHERE job_id=?",
                                   (str(image_path.resolve()),image_hash,time.time(),job['job_id']))
                append_event(run/'events.jsonl',event);completed+=1
                status(run)
            except Exception as exception:
                with db:db.execute("UPDATE jobs SET state='generation_error',error=?,updated=? WHERE job_id=?",(type(exception).__name__,time.time(),job['job_id']))
                status(run);raise
        db.close();logging.info('Generated %s; %s blocked on references',completed,blocked)
        return status(run)


def review_eligible(db,scope,item):
    row=db.execute('SELECT failures FROM review_failures WHERE scope=? AND item=?',(scope,item)).fetchone()
    from authorized_completion import review_window
    return row is None or row['failures']<review_window(db,scope,item)


def record_review_failure(db,run,scope,item,exception):
    evidence={'scope':scope,'item':item,'attempts':exception.attempts,'updated':time.time()}
    with db:db.execute('INSERT INTO review_failures VALUES(?,?,1,?) ON CONFLICT(scope,item) '
                       'DO UPDATE SET failures=failures+1,evidence=excluded.evidence',
                       (scope,item,canonical(evidence)))
    append_event(run/'review-errors.jsonl',evidence)


def record_service_outage(run,scope,item,exception):
    append_event(run/'review-service-errors.jsonl',{'scope':scope,'item':item,
                 'attempts':exception.attempts,'updated':time.time()})


def prioritize_reference_work(db, rows, original_key='image_sha256'):
    """Unblock new products first; keep every retained image in the audit queue."""
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'jobs','job_references'}<=tables:return rows
    waiting={(r[0],r[1]):r[2] for r in db.execute(
        "SELECT r.image_sha256,r.design_sha256,COUNT(*) FROM job_references r JOIN jobs j USING(job_id) "
        "WHERE j.state IN ('pending','rejected','review_required','interrupted') GROUP BY r.image_sha256,r.design_sha256")}
    return sorted(rows,key=lambda row:-waiting.get((row[original_key],row['design_sha256']),0))


def review(run,ocr,settings,*,pilot=False,limit=0,references=False,non_pilot=False):
    if non_pilot and (pilot or references):raise ValueError('Non-pilot selection is only for product review')
    with lock(run,'reference-review' if references else 'review'):
        desc=descriptor(run);db=connect(run)
        from authorized_completion import policy
        p=policy(db,desc) or {}
        reviewer=Reviewer(desc['vision_model'],ocr,settings,component_advisory=bool(p.get('advisory_component_counts')),synthetic_names=bool(p.get('synthetic_name_context')))
        try:
            if references:
                selection='AND EXISTS(SELECT 1 FROM job_references j JOIN jobs b ON b.job_id=j.job_id WHERE j.image_sha256=r.image_sha256 AND j.design_sha256=r.design_sha256 AND b.pilot=1)' if pilot else ''
                queue=list(db.execute('SELECT * FROM references_to_review r WHERE review IS NULL '+selection+' ORDER BY path'))
                queue=prioritize_reference_work(db,queue)
            else:
                with db:db.execute("UPDATE jobs SET state='generated' WHERE state='reviewing'")
                selection='AND pilot=1' if pilot else ('AND pilot=0' if non_pilot else '')
                queue=list(db.execute("SELECT * FROM jobs WHERE state IN ('generated','review_error') "+selection+' ORDER BY ordinal'))
            completed=0;consecutive_errors=0
            for row in queue:
                if (run/'STOP').exists():break
                if limit and completed>=limit:break
                scope='reference' if references else 'job'
                item=digest([row['image_sha256'],row['design_sha256']]) if references else row['job_id']
                if not review_eligible(db,scope,item):continue
                if not references and accepted_reference(db,json.loads(row['request']),desc['review_identity']) is False:continue
                completed+=1
                path=Path(row['path'] if references else row['image_path'])
                design=json.loads(row['design']) if references else json.loads(row['request'])['design']
                if sha256(path)!=row['image_sha256']:raise ValueError('Candidate changed before review')
                if not references:
                    with db:db.execute("UPDATE jobs SET state='reviewing',updated=? WHERE job_id=?",(time.time(),row['job_id']))
                try:
                    reference=None if references else accepted_reference(db,json.loads(row['request']),desc['review_identity'])
                    if reference is False:raise ValueError('Source image is no longer accepted')
                    result=reviewer.inspect(path,design,reference=reference)
                    from authorized_completion import relieve_review
                    result=relieve_review(db,result,design)
                    if not references:result=hold_half_round_geometry(result,design)
                    if references:
                        with db:db.execute('UPDATE references_to_review SET review=? WHERE image_sha256=? AND design_sha256=?',(canonical(result),row['image_sha256'],row['design_sha256']))
                    else:
                        with db:db.execute('UPDATE jobs SET state=?,review=?,error=NULL,updated=? WHERE job_id=?',(result['decision'],canonical(result),time.time(),row['job_id']))
                    consecutive_errors=0
                    append_event(run/'reviews.jsonl',{'job_id':None if references else row['job_id'],'path':str(path),**result})
                    status(run)
                except Exception as exception:
                    if isinstance(exception,ReviewServiceUnavailable):
                        if not references:
                            with db:db.execute("UPDATE jobs SET state='generated',error=NULL,updated=? WHERE job_id=?",
                                               (time.time(),row['job_id']))
                        record_service_outage(run,scope,item,exception)
                        status(run);raise
                    if not references:
                        with db:db.execute("UPDATE jobs SET state='review_error',error=?,updated=? WHERE job_id=?",(type(exception).__name__,time.time(),row['job_id']))
                    if isinstance(exception,ReviewUnavailable):
                        record_review_failure(db,run,scope,item,exception)
                        consecutive_errors+=1
                        status(run)
                        if consecutive_errors<3:continue
                    status(run);raise
        finally:reviewer.close();db.close()
        return status(run)


def accept_pilot(run,visual_receipt):
    desc=descriptor(run);db=connect(run)
    rows=list(db.execute('SELECT * FROM jobs WHERE pilot=1 ORDER BY ordinal'))
    if not rows or not all(current_job_accepted(db,r,desc['review_identity']) for r in rows):
        raise ValueError('Every pilot image must pass before bulk generation')
    receipt=json.loads(visual_receipt.read_text());images={r['job_id']:r['image_sha256'] for r in rows}
    if receipt.get('images')!=images or receipt.get('decision')!='accepted' or not receipt.get('observations'):
        raise ValueError('Visual pilot review is incomplete or stale')
    atomic_json(run/'pilot-acceptance.json',{'candidate_sha256':desc['candidate_sha256'],'images':images,
                'visual_review_receipt_sha256':sha256(visual_receipt),'review_identity':desc['review_identity']})
    db.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('init','generate','review','review-references','repair-references',
                                     'review-repairs','register-baseline-audit','reject-reference','reject-image','accept-ocr-review','accept-geometry-review','status','accept-pilot'))
    p.add_argument('--run',type=Path,required=True);p.add_argument('--candidate',type=Path);p.add_argument('--baseline',type=Path)
    p.add_argument('--model-snapshot',type=Path);p.add_argument('--vision-model',default='Qwen3.6-35B-A3B-8bit')
    p.add_argument('--ocr',type=Path);p.add_argument('--omlx-settings',type=Path);p.add_argument('--pilot',action='store_true')
    p.add_argument('--non-pilot',action='store_true')
    p.add_argument('--limit',type=int,default=0);p.add_argument('--visual-receipt',type=Path)
    p.add_argument('--job-id');p.add_argument('--observations');p.add_argument('--image-sha256')
    args=p.parse_args()
    if args.limit<0:p.error('limit must be nonnegative')
    args.run=args.run.resolve()
    if args.command=='init':result=initialize(args.candidate,args.baseline,args.run,args.model_snapshot,args.vision_model)
    elif args.command=='status':result=status(args.run)
    else:
        logging.basicConfig(filename=args.run/(args.command+'.log'),level=logging.INFO,format='%(asctime)s %(message)s')
        if args.command=='generate':result=generate(args.run,pilot=args.pilot,limit=args.limit,visual_receipt=args.visual_receipt,job_id=args.job_id)
        elif args.command=='reject-reference':result=reject_reference(args.run,args.image_sha256,args.observations)
        elif args.command=='reject-image':result=reject_image(args.run,args.job_id,args.observations)
        elif args.command=='accept-ocr-review':result=accept_ocr_review(args.run,args.job_id,args.image_sha256,args.observations)
        elif args.command=='accept-geometry-review':result=accept_geometry_review(args.run,args.job_id,args.image_sha256,args.observations)
        elif args.command in {'review','review-references'}:result=review(args.run,args.ocr,args.omlx_settings,pilot=args.pilot,limit=args.limit,references=args.command=='review-references',non_pilot=args.non_pilot)
        elif args.command in {'repair-references','review-repairs','register-baseline-audit'}:
            from repair_expansion_references import dispatch
            result=dispatch(args)
        else:accept_pilot(args.run,args.visual_receipt);result=status(args.run)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    try:main()
    except ReviewServiceUnavailable:
        # EX_TEMPFAIL is reserved for an outage, never a failed image verdict.
        raise SystemExit(75)
    except BlockingIOError:
        # A central reservation/import may briefly own the generation lock.
        raise SystemExit(73)
