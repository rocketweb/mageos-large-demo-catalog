"""Studio-side coordinator for an explicitly configured remote image worker.

Requires an already provisioned model/runtime. Does not install dependencies,
copy model weights, alter SSH keys, deploy a store, or perform image acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

from bulk_expansion_images import atomic_json,lock,connect
from remote_image_batch import reserve,import_results,sha256


def ssh_options():
    return ['-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=30',
            '-o','ServerAliveCountMax=3','-o','ControlMaster=auto','-o','ControlPersist=600',
            '-o','ControlPath=/tmp/codex-wands-mini-%C']


class RemoteRetryStopped(Exception):
    """Operator stopped a checkpointed transport retry."""


def checked(args,log):
    match=re.fullmatch(r'remote-([a-z][a-z0-9_-]{0,31})-console\.log',log.name)
    worker=match[1] if match and match[1]!='worker' else 'mini'
    state_path=log.parent/('remote-worker-state.json' if worker=='mini' else f'remote-{worker}-state.json')
    stop_path=log.parent/('REMOTE_STOP' if worker=='mini' else f'REMOTE_STOP-{worker}')
    original=json.loads(state_path.read_text()) if state_path.exists() else {}
    command=Path(args[0]).name
    for retry in range(31):
        if stop_path.exists():raise RemoteRetryStopped()
        with log.open('ab') as stream:
            result=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT)
        if result.returncode==0:
            if retry:atomic_json(state_path,{**original,'transport_retries':retry,'updated':time.time()})
            return
        # Only transport loss or the renderer's explicit lock-busy exit can
        # retry. Validation/model failures remain fatal. A reconnect repeats
        # the exact packet; renderer locking and per-image hashes prevent races.
        busy=command=='ssh' and result.returncode==73 and any(name+' render' in args[-1] for name in ('remote_image_batch.py','cuda_image_batch.py'))
        transient=(command=='ssh' and result.returncode==255) or (command=='rsync' and result.returncode in {10,30,35,255})
        if not (busy or transient) or retry==30:
            raise RuntimeError(f'{command} failed with exit {result.returncode}; see {log.name}')
        for remaining in range(60,0,-5):
            if stop_path.exists():raise RemoteRetryStopped()
            atomic_json(state_path,{**original,'state':'waiting_for_remote_renderer' if busy else 'waiting_for_remote_connection',
                                   'transport_retries':retry+1,'retry_in_seconds':remaining,
                                   'exit_code':result.returncode,'updated':time.time()})
            time.sleep(5)


def remote_command(target,args,log):
    checked(['ssh',*ssh_options(),target,shlex.join([str(x) for x in args])],log)


def sync(source,target,log):
    checked(['rsync','-a','--partial','-e',shlex.join(['ssh',*ssh_options()]),str(source),str(target)],log)


def has_future_work(run):
    db=connect(run)
    try:
        if db.execute("SELECT 1 FROM jobs WHERE pilot=0 AND state IN ('pending','interrupted','generating','generated','reviewing','review_error') LIMIT 1").fetchone():return True
        if db.execute('SELECT 1 FROM reference_repairs WHERE review IS NULL LIMIT 1').fetchone():return True
        if db.execute('SELECT 1 FROM references_to_review WHERE review IS NULL LIMIT 1').fetchone():return True
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='remote_batches'").fetchone():
            return bool(db.execute("SELECT 1 FROM remote_batches WHERE state='reserved' LIMIT 1").fetchone())
        return False
    finally:db.close()


def coordinate(run,target,root,batch_size=64,max_batches=0,worker_id='mini'):
    # Targets are operator input, never supplied by a returned packet.
    if not re.fullmatch(r'[A-Za-z0-9_.-]+@[A-Za-z0-9.-]+',target):raise ValueError('Invalid SSH destination')
    if not re.fullmatch('[a-z][a-z0-9_-]{0,31}',worker_id) or worker_id=='worker':raise ValueError('Invalid worker ID')
    pattern=(r'/Users/[A-Za-z0-9_.-]+/wands-image-worker' if worker_id=='mini'
             else r'/(root|home/[A-Za-z0-9_.-]+)/wands-image-worker')
    if not re.fullmatch(pattern,str(root)):
        raise ValueError('Use the isolated ~/wands-image-worker directory')
    if not 1<=batch_size<=64 or max_batches<0:raise ValueError('Invalid batch limits')
    suffix='' if worker_id=='mini' else '-'+worker_id
    stop=run/('REMOTE_STOP'+suffix)
    with lock(run,'remote-coordinator'+suffix):
        stem='remote-worker' if worker_id=='mini' else 'remote-'+worker_id
        state=run/(stem+'-state.json');log=run/(stem+'-console.log');completed=0
        def update(phase,**values):
            atomic_json(state,{'state':phase,'target':target,'completed_batches':completed,'updated':time.time(),**values})
        try:
            while True:
                if stop.exists():update('stopped_by_request');return
                try:manifest=reserve(run,batch_size,diverse=batch_size<=8,worker_id=worker_id)
                except BlockingIOError:
                    update('waiting_for_catalog_worker');time.sleep(5);continue
                if manifest is None:
                    if not has_future_work(run):update('no_eligible_jobs_remaining');return
                    update('waiting_for_eligible_images')
                    for _ in range(12):
                        if stop.exists():break
                        time.sleep(5)
                    continue
                packet=json.loads(manifest.read_text());batch_id=packet['batch_id'];remote=root/'batches'/batch_id
                incoming=manifest.parent/'returned';incoming.mkdir(exist_ok=True)
                kind=packet.get('kind','new-product-images')
                update('transferring_batch',batch_id=batch_id,jobs=len(packet['jobs']),kind=kind)
                remote_command(target,['mkdir','-p',remote],log)
                sync(manifest,f'{target}:{remote}/manifest.json',log)
                if (manifest.parent/'references').is_dir():
                    remote_command(target,['mkdir','-p',remote/'references'],log)
                    sync(str(manifest.parent/'references')+'/',f'{target}:{remote}/references/',log)
                update('generating',batch_id=batch_id,jobs=len(packet['jobs']),kind=kind)
                prefix=(['caffeinate','-i','env','-u','METAL_DEVICE_WRAPPER_TYPE'] if worker_id=='mini'
                        else ['systemd-inhibit','--what=sleep:idle','--mode=block','--who=WANDS','--why=Catalog image generation'])
                renderer='remote_image_batch.py' if worker_id=='mini' else 'cuda_image_batch.py'
                remote_command(target,[*prefix,root/'.venv/bin/python',root/'code'/renderer,'render',
                                      '--manifest',remote/'manifest.json','--manifest-sha256',sha256(manifest),
                                      '--model-path',root/'model','--output',remote/'output'],log)
                update('receiving_images',batch_id=batch_id)
                sync(f'{target}:{remote}/output/',str(incoming)+'/',log)
                while True:
                    try:import_results(run,batch_id,incoming);break
                    except BlockingIOError:
                        update('waiting_to_import',batch_id=batch_id);time.sleep(5)
                completed+=1;update('imported_for_review',batch_id=batch_id)
                if max_batches and completed>=max_batches:return
        except RemoteRetryStopped:
            update('stopped_by_request')
        except Exception as error:
            # Leave the reservation intact. A restart reuses the same manifest,
            # seed and completed image bytes; malformed returns never pass QA.
            update('needs_attention',error_type=type(error).__name__)
            raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True,type=Path);p.add_argument('--target',required=True)
    p.add_argument('--remote-root',required=True,type=Path);p.add_argument('--batch',type=int,default=64)
    p.add_argument('--max-batches',type=int,default=0)
    p.add_argument('--worker-id',default='mini')
    a=p.parse_args();coordinate(a.run.resolve(),a.target,a.remote_root,a.batch,a.max_batches,a.worker_id)


if __name__=='__main__':main()
