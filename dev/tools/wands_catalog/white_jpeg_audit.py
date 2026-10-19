#!/usr/bin/env python3
"""Conservative audit and separate selection of original/white catalog JPEGs."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import io
import inspect
import math
import json
import os
from pathlib import Path
import sqlite3
import time

import numpy as np
from PIL import Image

from white_jpeg_worker import atomic_json, sha256

VERSION = 'scene-preserving-selection-v3'
MODEL = '/Users/matt/.cache/huggingface/hub/models--google--siglip-large-patch16-384/snapshots/ce005573a40965dfd21fd937fbdeeebf2439fc35'
TEXTS = [
    'A studio product photograph of a single product isolated against a plain solid white background.',
    'A studio product photograph of a product against a plain seamless cream or beige background.',
    'A photograph of a furnished room or home interior with walls, floor, furniture, and decor.',
    'A lifestyle photograph of a product in a room, kitchen, bathroom, or real home setting.',
    'An outdoor photograph of a product in a garden, patio, yard, or landscape.',
    'A close-up photograph with a detailed textured or patterned background.',
    'A product photograph with props and a complex non-solid background.',
]
POLICY = {'border_p95_max':16, 'border_uniform_min':.985, 'border_neutral_min':205,
          'border_chroma_max':48, 'core_min':.01, 'core_preserved_min':.992,
          'edges_preserved_min':.995, 'white_border_min':.995, 'plain_margin_min':2.5,
          'shadow_chroma_tolerance':.012,'core_coverage_min':.6,'edge_tile_min':.8}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def border(a, width=8):
    return np.concatenate((a[:width].reshape(-1,3),a[-width:].reshape(-1,3),
                           a[width:-width,:width].reshape(-1,3),a[width:-width,-width:].reshape(-1,3)))


def edge_strength(a):
    x=np.max(np.abs(a[1:-1,2:]-a[1:-1,:-2]),axis=2)
    y=np.max(np.abs(a[2:,1:-1]-a[:-2,1:-1]),axis=2)
    return np.maximum(x,y)


def neighbor_max(a):
    padded=np.pad(a,1,mode='edge')
    return np.maximum.reduce([padded[y:y+a.shape[0],x:x+a.shape[1]] for y in range(3) for x in range(3)])


def metrics(original, processed=None):
    a=np.asarray(original.resize((256,256),Image.Resampling.BILINEAR),dtype=np.float32)
    perimeter=border(a);bg=np.median(perimeter,axis=0)
    deviations=np.max(np.abs(perimeter-bg),axis=1)
    core=(np.max(np.abs(a-bg),axis=2)>35)&(np.min(a,axis=2)<225)
    # A cast shadow darkens the backdrop without becoming part of the product.
    # Reject near-backdrop chromaticity from the color-preservation measurement.
    chroma=a/np.maximum(a.sum(axis=2,keepdims=True),1)
    bg_chroma=bg/max(float(bg.sum()),1)
    core &= np.max(np.abs(chroma-bg_chroma),axis=2)>POLICY['shadow_chroma_tolerance']
    # Interior-only color comparison avoids judging normal antialiasing as loss.
    core=np.logical_and.reduce([np.roll(np.roll(core,y,axis=0),x,axis=1) for y in (-1,0,1) for x in (-1,0,1)])
    core[:3]=False;core[-3:]=False;core[:,:3]=False;core[:,-3:]=False
    e=edge_strength(a);strong=e>=32
    result={'background_rgb':bg.round(3).tolist(),'border_p95':float(np.quantile(deviations,.95)),
            'border_uniform':float(np.mean(deviations<=20)),'core_fraction':float(np.mean(core)),
            'source_edge_fraction':float(np.mean(strong)),'dimensions':list(original.size)}
    if processed is not None:
        if original.size!=processed.size:
            return {**result,'candidate_error':'dimensions_changed'}
        b=np.asarray(processed.resize((256,256),Image.Resampling.BILINEAR),dtype=np.float32)
        delta=np.max(np.abs(a-b),axis=2)
        out_edges=neighbor_max(edge_strength(b))
        retained=core&(np.min(b,axis=2)<245)
        hits=out_edges>=12
        tile_recalls=[]
        for y in range(0,strong.shape[0],16):
            for x in range(0,strong.shape[1],16):
                region=strong[y:y+16,x:x+16]
                if region.sum()>=8:tile_recalls.append(float(np.mean(hits[y:y+16,x:x+16][region])))
        result.update(core_preserved=float(np.mean(delta[retained]<=20)) if retained.any() else 0,
                      core_coverage=float(retained.sum()/max(core.sum(),1)),
                      edges_preserved=float(np.mean(out_edges[strong]>=12)) if strong.any() else 0,
                      edge_tile_min=min(tile_recalls) if tile_recalls else 0,
                      white_border=float(np.mean(np.min(border(b),axis=1)>=250)))
    return result


def numeric_reason(m, has_candidate):
    p=POLICY;bg=m['background_rgb']
    if m['border_p95']>p['border_p95_max'] or m['border_uniform']<p['border_uniform_min']:
        return 'non_solid_or_scene_background'
    if min(bg)<p['border_neutral_min'] or max(bg)-min(bg)>p['border_chroma_max']:
        return 'uncertain_or_colored_background'
    if m['core_fraction']<p['core_min'] or m['source_edge_fraction']<.001:
        return 'uncertain_product_boundaries'
    if has_candidate:
        if m.get('candidate_error'):return m['candidate_error']
        if m.get('core_coverage',0)<p['core_coverage_min']:return 'uncertain_foreground_coverage'
        if m.get('core_preserved',0)<p['core_preserved_min']:return 'cutout_lost_product_color'
        if m.get('edges_preserved',0)<p['edges_preserved_min']:return 'cutout_lost_product_edges'
        if m.get('edge_tile_min',0)<p['edge_tile_min']:return 'uncertain_local_product_edges'
        if m.get('white_border',0)<p['white_border_min']:return 'uncertain_white_background'
    return None


def decision(row,m,scores=None):
    if row.get('warning'):return 'original','flagged_cutout'
    if m.get('candidate_error'):return 'original',m['candidate_error']
    reason=numeric_reason(m,bool(row.get('output_file')))
    if reason:return 'original',reason
    if scores is None:return 'original','unclassified_background'
    if len(scores)!=len(TEXTS) or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in scores):
        return 'original','invalid_or_uncertain_scene_scores'
    margin=max(scores[:2])-max(scores[2:])
    if margin<POLICY['plain_margin_min']:
        return 'original','scene_or_uncertain_semantics'
    return ('white','verified_plain_background_and_preserved_product') if row.get('output_file') else ('eligible','verified_plain_background_needs_conversion')


def connect(audit):
    db=sqlite3.connect(audit/'audit.sqlite3',timeout=30);db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
    db.executescript('''CREATE TABLE IF NOT EXISTS images(n INTEGER PRIMARY KEY,file TEXT UNIQUE,
      row_json TEXT NOT NULL,metrics TEXT,scores TEXT,decision TEXT,reason TEXT);
      CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
      CREATE INDEX IF NOT EXISTS audit_work ON images(decision,n);''')
    return db


def progress(audit,db,phase,started,error=None):
    total=db.execute('SELECT count(*) FROM images').fetchone()[0]
    complete=db.execute('SELECT count(*) FROM images WHERE metrics IS NOT NULL').fetchone()[0]
    classified=db.execute('SELECT count(*) FROM images WHERE scores IS NOT NULL').fetchone()[0]
    counts=dict(db.execute('SELECT coalesce(decision,\'pending\'),count(*) FROM images GROUP BY decision'))
    state={'phase':phase,'updated_at':time.time(),'started_at':started,'total':total,
           'metrics_complete':complete,'classified':classified,'decisions':counts,'error':error,
           'originals_modified':False,'catalog_imported':False,'pid':os.getpid()}
    atomic_json(audit/'status.json',state)
    return state


def initialize(job,audit):
    audit.mkdir(parents=True,exist_ok=True)
    identity={'version':VERSION,'inventory_sha256':sha256(job/'audit-inputs.json'),
              'policy':POLICY,'scene_texts':TEXTS,'model':MODEL,
              'feature_sha256':digest((inspect.getsource(metrics)+inspect.getsource(border)+inspect.getsource(edge_strength)+inspect.getsource(neighbor_max)).encode())}
    path=audit/'identity.json'
    if path.exists() and json.loads(path.read_text())!=identity:raise ValueError('Audit identity changed')
    if not path.exists():atomic_json(path,identity)
    rows=json.loads((job/'audit-inputs.json').read_text())
    db=connect(audit)
    if not db.execute('SELECT 1 FROM images LIMIT 1').fetchone():
        with db:db.executemany('INSERT INTO images(n,file,row_json) VALUES(?,?,?)',[(r['n'],r['file'],json.dumps(r)) for r in rows])
    if db.execute('SELECT count(*) FROM images').fetchone()[0]!=len(rows):raise ValueError('Audit count mismatch')
    return db


def inspect_row(row,originals,media):
    path=originals/row['file'];data=path.read_bytes()
    if path.is_symlink() or digest(data)!=row['source_sha256']:raise ValueError('Original hash mismatch: '+row['file'])
    with Image.open(io.BytesIO(data)) as source:original=source.convert('RGB')
    processed=None;candidate_error=None
    if row.get('output_file'):
        candidate=media/row['output_file']
        if candidate.is_symlink() or not candidate.is_file():candidate_error='missing_candidate'
        else:
            content=candidate.read_bytes()
            if digest(content)!=row['output_sha256']:candidate_error='candidate_hash_mismatch'
            else:
                with Image.open(io.BytesIO(content)) as image:processed=image.convert('RGB')
    m=metrics(original,processed)
    if candidate_error:m['candidate_error']=candidate_error
    return row['n'],m


def measure(job,audit,workers=8):
    db=initialize(job,audit);started=time.time()
    originals=Path(json.loads((job/'manifest.json').read_text())['originals'])
    media=job/'media/wands-expanded'
    rows=[json.loads(r[0]) for r in db.execute('SELECT row_json FROM images WHERE metrics IS NULL ORDER BY n')]
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            iterator=pool.map(lambda row:inspect_row(row,originals,media),rows)
            pending=[]
            for n,m in iterator:
                pending.append((json.dumps(m,separators=(',',':')),n))
                if len(pending)>=256:
                    with db:db.executemany('UPDATE images SET metrics=? WHERE n=?',pending)
                    pending=[]
                    state=progress(audit,db,'measuring',started)
                    if state['metrics_complete']%4096==0:print(json.dumps(state),flush=True)
            if pending:
                with db:db.executemany('UPDATE images SET metrics=? WHERE n=?',pending)
        print(json.dumps(progress(audit,db,'metrics_complete',started)),flush=True)
    except BaseException as error:
        progress(audit,db,'needs_attention',started,str(error));raise
    finally:db.close()


def classify(job,audit,batch_size=64,limit=0,pending_only=False):
    db=initialize(job,audit);started=time.time()
    counts=db.execute('SELECT count(*),count(metrics) FROM images').fetchone()
    if counts[0]!=counts[1]:
        db.close();raise ValueError('Complete all image measurements before classifying')
    import torch
    from transformers import AutoProcessor,SiglipModel
    originals=Path(json.loads((job/'manifest.json').read_text())['originals'])
    rows=[]
    rejected=[]
    records=db.execute('SELECT * FROM images ORDER BY n').fetchall()
    for r in records:
        row=json.loads(r['row_json']);m=json.loads(r['metrics'])
        if pending_only and row.get('output_file'):continue
        reason='flagged_cutout' if row.get('warning') else m.get('candidate_error') or numeric_reason(m,bool(row.get('output_file')))
        if reason:
            rejected.append((reason,r['n']))
        elif r['scores'] is None:rows.append((r['n'],row))
    with db:db.executemany('UPDATE images SET decision=\'original\',reason=? WHERE n=?',rejected)
    if limit:rows=rows[:limit]
    progress(audit,db,'loading_scene_model',started)
    processor=AutoProcessor.from_pretrained(MODEL,local_files_only=True,use_fast=False)
    model=SiglipModel.from_pretrained(MODEL,local_files_only=True,dtype=torch.float16).eval().to('mps')
    for offset in range(0,len(rows),batch_size):
        batch=rows[offset:offset+batch_size];images=[]
        for n,row in batch:
            with Image.open(originals/row['file']) as im:images.append(im.convert('RGB'))
        inputs=processor(text=TEXTS,images=images,return_tensors='pt',padding='max_length')
        inputs={k:v.to('mps') for k,v in inputs.items()}
        with torch.inference_mode():out=model(**inputs)
        scores=out.logits_per_image.float().cpu().tolist()
        with db:
            for (n,row),s in zip(batch,scores):
                m=json.loads(db.execute('SELECT metrics FROM images WHERE n=?',(n,)).fetchone()[0])
                kind,reason=decision(row,m,s)
                db.execute('UPDATE images SET scores=?,decision=?,reason=? WHERE n=?',(json.dumps(s),kind,reason,n))
        state=progress(audit,db,'classifying',started)
        done=min(offset+len(batch),len(rows))
        state.update(phase_done=done,phase_total=len(rows),
                     eta_at=time.time()+(time.time()-started)/max(done,1)*(len(rows)-done))
        atomic_json(audit/'status.json',state)
        if offset%(batch_size*16)==0:print(json.dumps(state),flush=True)
    print(json.dumps(progress(audit,db,'classification_complete',started)),flush=True);db.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['measure','classify'])
    p.add_argument('--job',required=True,type=Path);p.add_argument('--audit',required=True,type=Path)
    p.add_argument('--workers',type=int,default=8);p.add_argument('--batch',type=int,default=64);p.add_argument('--limit',type=int,default=0)
    p.add_argument('--pending-only',action='store_true')
    a=p.parse_args()
    if a.command=='measure':measure(a.job.resolve(),a.audit.resolve(),a.workers)
    else:classify(a.job.resolve(),a.audit.resolve(),a.batch,a.limit,a.pending_only)


if __name__=='__main__':main()
