#!/usr/bin/env python3
"""Serial, resumable local image work. Stops for visual pilot acceptance or unresolved QA."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from bulk_expansion_images import atomic_json, connect, descriptor, lock, status


def counts(run,pilot):
    db=connect(run)
    scope='WHERE pilot=1' if pilot else ''
    jobs=[dict(r) for r in db.execute('SELECT state,COUNT(*) n,SUM(attempts) attempts FROM jobs '+scope+' GROUP BY state')]
    ref_scope=('WHERE EXISTS(SELECT 1 FROM job_references j JOIN jobs b ON b.job_id=j.job_id '
               'WHERE j.image_sha256=r.image_sha256 AND j.design_sha256=r.design_sha256 AND b.pilot=1)') if pilot else ''
    refs=[r['review'] for r in db.execute('SELECT review FROM references_to_review r '+ref_scope)]
    repairs=[tuple(r) for r in db.execute('SELECT original_sha256,design_sha256,attempt,review FROM reference_repairs')]
    failed_reviews=db.execute('SELECT COALESCE(SUM(failures),0) FROM review_failures').fetchone()[0]
    from category_image_corrections import has_table
    category_reviews=db.execute('SELECT COUNT(*) FROM category_image_reviews').fetchone()[0] if has_table(db) else 0
    db.close()
    return {'category_reviews':category_reviews,'failed_review_batches':failed_reviews,'jobs':jobs,'reviewed_references':sum(r is not None for r in refs),'total_references':len(refs),
            'repair_attempts':len(repairs),'reviewed_repairs':sum(r[3] is not None for r in repairs)}


def other_workers_running(run):
    for name in ('generation','review','reference-review','reference-repair-review'):
        try:
            with lock(run,name):pass
        except BlockingIOError:return True
    return False


def remote_batches_pending(run):
    db=connect(run)
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='remote_batches'").fetchone():return False
        return bool(db.execute("SELECT 1 FROM remote_batches WHERE state='reserved' LIMIT 1").fetchone())
    finally:db.close()


def review_batch_limit(run,minimum):
    if not (run/'remote-batches').exists():return minimum
    db=connect(run)
    try:
        queued=db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('generated','review_error')").fetchone()[0]
        return max(minimum,min(256,queued))
    finally:db.close()


def run_phase(run,state,args,command,cycle,pilot):
    """Wait through a local inference outage without consuming image QA retries."""
    base={'phase':command,'cycle':cycle,'pilot':pilot,'pid':os.getpid()}
    service_retries=0
    while True:
        if (run/'STOP').exists():
            atomic_json(state,{**base,'state':'stopped_by_request','updated':time.time()})
            return False
        atomic_json(state,{**base,'state':'running','service_retries':service_retries,'updated':time.time()})
        child_env=None
        if command in {'generate','generate-admitted','repair-references'}:
            child_env=os.environ.copy()
            # The inherited Metal debug wrapper aborts this MLX repair kernel
            # on a nil-buffer assertion. Use the normal runtime for generation;
            # keep memory limits, model settings and independent image QA intact.
            child_env.pop('METAL_DEVICE_WRAPPER_TYPE',None)
        with (run/'worker-console.log').open('ab') as log:
            result=subprocess.run(args,stdout=log,stderr=log,env=child_env)
        if result.returncode==0:return True
        if result.returncode not in {73,75}:
            atomic_json(state,{**base,'state':'needs_attention','exit_code':result.returncode,'updated':time.time()})
            return False
        service_retries+=1
        # A missing local service may need the user to start it. Keep the run
        # checkpointed and check once per minute, without changing the service.
        waiting='waiting_for_review_service' if result.returncode==75 else 'waiting_for_catalog_worker'
        for remaining in range(60 if result.returncode==75 else 5,0,-5):
            if (run/'STOP').exists():
                atomic_json(state,{**base,'state':'stopped_by_request','updated':time.time()})
                return False
            atomic_json(state,{**base,'state':waiting,'exit_code':result.returncode,
                               'service_retries':service_retries,'retry_in_seconds':remaining,'updated':time.time()})
            time.sleep(5)


def supervise(run,ocr,settings,pilot=True,batch=16,max_cycles=0,visual_receipt=None,export_output=None):
    desc=descriptor(run)
    with lock(run,'supervisor'):
        state=run/'worker-state.json'
        atomic_json(state,{'state':'starting','pid':__import__('os').getpid(),'pilot':pilot,'updated':time.time()})
        while other_workers_running(run):
            atomic_json(state,{'state':'waiting_for_existing_workers','pilot':pilot,'updated':time.time()})
            if (run/'STOP').exists():return
            time.sleep(10)
        cycle=0
        while True:
            if (run/'STOP').exists():
                atomic_json(state,{'state':'stopped_by_request','updated':time.time()});return
            before=counts(run,pilot and not visual_receipt)
            phases=[('review-references',batch,pilot),('repair-references',max(1,batch//2),pilot),
                    ('review-repairs',batch,pilot),('generate',batch,pilot),('review',batch,pilot)]
            if visual_receipt:
                phases=[('review-non-pilot',batch,False),('generate-admitted',batch,False)]+phases+[
                    ('review-references',batch,False),('repair-references',max(1,batch//2),False),
                    ('review-repairs',batch,False)]
            if not pilot:phases=[('review-categories',batch,False)]+phases
            for command,limit,pilot_phase in phases:
                if (run/'STOP').exists():break
                if command=='review' and not pilot_phase:limit=review_batch_limit(run,limit)
                if visual_receipt:
                    from profile_admission import apply_direct_holds
                    apply_direct_holds(run,visual_receipt)
                args=[sys.executable,str(Path(__file__).with_name('bulk_expansion_images.py')),
                      {'generate-admitted':'generate','review-non-pilot':'review'}.get(command,command),
                      '--run',str(run),'--limit',str(limit),'--ocr',str(ocr),'--omlx-settings',str(settings)]
                if command=='review-categories':
                    args=[sys.executable,str(Path(__file__).with_name('category_image_corrections.py')),
                          '--run',str(run),'--limit',str(limit),'--omlx-settings',str(settings)]
                if pilot_phase:args+=['--pilot']
                if command=='review-non-pilot':args+=['--non-pilot']
                if command=='generate-admitted':args+=['--visual-receipt',str(visual_receipt)]
                if not run_phase(run,state,args,command,cycle,pilot):return
            after=counts(run,pilot and not visual_receipt);cycle+=1
            product_states={r['state']:r['n'] for r in after['jobs']}
            if set(product_states)=={'accepted'}:
                ready=pilot
                if not pilot:
                    from export_expanded_catalog import inspect
                    _,readiness,_,_=inspect(run)
                    atomic_json(run/'export-readiness.json',readiness)
                    ready=readiness['ready']
                if ready:
                    if export_output:
                        if pilot:raise ValueError('Automatic export requires full bulk mode')
                        from export_expanded_catalog import export
                        from prepare_catalog import sha256
                        atomic_json(state,{'state':'exporting_accepted_catalog','cycle':cycle,
                                           'output':str(export_output),'updated':time.time()})
                        export(run,export_output)
                        atomic_json(state,{'state':'accepted_catalog_exported; installation_pending','cycle':cycle,
                            'output':str(export_output),'manifest_sha256':sha256(export_output/'manifest.json'),
                            'updated':time.time()});return
                    atomic_json(state,{'state':'ready_for_visual_pilot_review' if pilot else 'ready_for_final_audit',
                                       'cycle':cycle,'counts':after,'updated':time.time()});return
            if before==after:
                if (product_states.get('remote_reserved') or remote_batches_pending(run)) and not (max_cycles and cycle>=max_cycles):
                    atomic_json(state,{'state':'waiting_for_remote_images','cycle':cycle,'updated':time.time()})
                    time.sleep(5);continue
                atomic_json(state,{'state':'needs_attention','reason':'No eligible progress; unresolved review or exhausted retries',
                                   'cycle':cycle,'counts':after,'updated':time.time()});return
            if max_cycles and cycle>=max_cycles:
                atomic_json(state,{'state':'cycle_limit_reached','cycle':cycle,'counts':after,'updated':time.time()});return


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--ocr',type=Path,required=True)
    p.add_argument('--omlx-settings',type=Path,required=True);p.add_argument('--bulk',action='store_true')
    p.add_argument('--batch',type=int,default=16);p.add_argument('--max-cycles',type=int,default=0)
    p.add_argument('--visual-receipt',type=Path,help='Generate non-pilot jobs only for profiles with complete current direct and automated pilot acceptance')
    p.add_argument('--export-output',type=Path,help='Export the complete catalog only after every image gate passes; does not install it')
    a=p.parse_args()
    if not 1<=a.batch<=64 or a.max_cycles<0:p.error('Batch must be 1..64; cycles nonnegative')
    if a.bulk and a.visual_receipt:p.error('Full bulk and progressive profile generation are separate modes')
    if a.export_output and not a.bulk:p.error('Automatic export requires --bulk')
    if a.export_output and a.export_output.exists():p.error('Choose a fresh export destination')
    try:
        supervise(a.run.resolve(),a.ocr.resolve(),a.omlx_settings.resolve(),not a.bulk,a.batch,a.max_cycles,
                  a.visual_receipt.resolve() if a.visual_receipt else None,
                  a.export_output.resolve() if a.export_output else None)
    except Exception as error:
        # A failing second supervisor must not overwrite the active worker state.
        if not isinstance(error,BlockingIOError):
            atomic_json(a.run.resolve()/'worker-state.json',{'state':'needs_attention',
                        'reason':type(error).__name__,'updated':time.time()})
        raise


if __name__=='__main__':main()
