#!/usr/bin/env python3
"""Checkpointed calibrated audit, isolated Mini conversion, and verified selection.

The pilot report must match the frozen checks before the catalog can be audited.
No source media or accepted catalog data is modified.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import csv
import fcntl
import hashlib
import inspect
import importlib.metadata
import json
import os
from pathlib import Path
import plistlib
import random
import platform
import shutil
import subprocess
import time

import white_jpeg_calibrated_audit as checks
import white_jpeg_audit_run as export
from image_review import api_key, ReviewServiceUnavailable
from white_jpeg_worker import atomic_json, sha256

REMOTE=Path('/Users/matt/wands-image-worker/jobs/white-jpeg-calibrated-20261017')
LABEL='com.matt.wands-white-jpeg-calibrated-20261017'
WORKERS=4


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def initialize(job,audit):
    if audit==job or not audit.is_relative_to(job):raise ValueError('Expected a separate audit folder within the image job')
    db=checks.connect(audit)
    records=db.execute('SELECT row_json FROM images ORDER BY n').fetchall()
    if len(records)!=95401:raise ValueError('Expected all 95,401 source records')
    inventory=audit/'candidate-inventory.json'
    if not inventory.exists():atomic_json(inventory,[json.loads(r[0]) for r in records])
    verify_runtime(audit)
    ident={**checks.identity(),'decision_identity':checks.decision_identity(),
           'reviewer_runtime_sha256':sha256(audit/'reviewer-runtime.json'),
           'processing_runtime_sha256':sha256(audit/'processing-runtime.json'),
           'source_protocol_sha256':hashlib.sha256((inspect.getsource(checks.request)+inspect.getsource(checks.load_pair)).encode()).hexdigest(),
           'initial_inventory_sha256':sha256(inventory),'original_inventory_sha256':sha256(job/'audit-inputs.json')}
    path=audit/'identity.json'
    if path.exists() and json.loads(path.read_text())!=ident:raise ValueError('Frozen audit identity changed')
    if not path.exists():atomic_json(path,ident)
    return db,ident


def verify_runtime(audit):
    expected=json.loads((audit/'processing-runtime.json').read_text())
    actual={'python':platform.python_version(),'packages':{name:importlib.metadata.version(name) for name in expected['packages']}}
    if actual!=expected:raise ValueError('Image processing runtime changed')
    runtime=json.loads((audit/'reviewer-runtime.json').read_text())
    if runtime['model_id']!=checks.MODEL:raise ValueError('Reviewer model changed')
    for item in runtime['files']:
        path=Path(runtime['model_path'])/item['name'];stat=path.stat()
        if stat.st_size!=item['bytes'] or stat.st_mtime_ns!=item['mtime_ns']:raise ValueError('Reviewer files changed')
        if item.get('sha256') and sha256(path)!=item['sha256']:raise ValueError('Reviewer configuration changed')


def progress(audit,db,phase,started=None,**extra):
    total=db.execute('SELECT count(*) FROM images').fetchone()[0]
    measured=db.execute('SELECT count(*) FROM calibrated_features').fetchone()[0]
    reviewed=db.execute('SELECT count(DISTINCT file) FROM calibrated_reviews').fetchone()[0]
    pairs=db.execute("SELECT count(*) FROM calibrated_reviews WHERE kind='pair'").fetchone()[0]
    counts=dict(db.execute("SELECT coalesce(decision,'pending'),count(*) FROM images GROUP BY decision"))
    now=time.time();values={'audit_kind':'calibrated','pid':os.getpid(),'total':total,
        'metrics_complete':measured,'classified':reviewed,'product_reviews':pairs,'decisions':counts,**extra}
    if started:values['pass_started_at']=started
    return checks.status(audit,phase,**values)


def save_result(db,row,m,review,details):
    kind='pair' if row.get('output_file') else 'source'
    if review is not None:
        checks.parse(json.dumps(review))
        model=details['model']
        if model!=checks.MODEL or details.get('review_identity')!=checks.review_identity(model):raise ValueError('Review protocol identity changed')
    decision,reason=checks.choose(row,m,review,details.get('focus'))
    with db:
        db.execute('INSERT OR REPLACE INTO calibrated_features VALUES(?,?)',(row['file'],json.dumps(m)))
        if review is not None:
            db.execute('INSERT INTO calibrated_reviews VALUES(?,?,?,?,?,?,?,?)',
                (row['file'],kind,checks.decision_identity(),row['source_sha256'],row.get('output_sha256'),
                 json.dumps(review),json.dumps(details),time.time()))
        db.execute('UPDATE images SET decision=?,reason=? WHERE file=?',(decision,reason,row['file']))
    return decision


def cached_result(db,row):
    feature=db.execute('SELECT features FROM calibrated_features WHERE file=?',(row['file'],)).fetchone()
    if not feature:return None
    m=json.loads(feature[0]);reason=checks.screen(row,m)
    if reason:return m,None,{'skipped':reason}
    kind='pair' if row.get('output_file') else 'source'
    result=db.execute('SELECT * FROM calibrated_reviews WHERE file=? AND kind=?',(row['file'],kind)).fetchone()
    if not result:return None
    if (result['identity']!=checks.decision_identity() or result['source_sha256']!=row['source_sha256'] or
        result['output_sha256']!=row.get('output_sha256')):raise ValueError('Cached review content or policy mismatch')
    return m,json.loads(result['review']),json.loads(result['details'])


def seed_references(job,audit,db):
    folder=audit/'reference/evaluations'/checks.decision_identity()[:16]
    for split in ('calibration','holdout'):
        items=json.loads((audit/'reference'/(split+'.json')).read_text())
        results=json.loads((folder/(split+'-results.json')).read_text())
        for item in items:
            row=item['row']
            if cached_result(db,row):continue
            result=results[item['file']]
            # Verify native inputs again before accepting a reference review into the run.
            checks.load_pair(job,row)
            save_result(db,row,result['features'],result['review'],result['details'])


def reference_report(audit):
    folder=audit/'reference/evaluations'/checks.decision_identity()[:16];reports={}
    expected=json.loads((audit/'reference/expected-counts.json').read_text()) if (audit/'reference/expected-counts.json').exists() else {'calibration':105,'holdout':105}
    for split in ('calibration','holdout'):
        items=json.loads((audit/'reference'/(split+'.json')).read_text())
        results=json.loads((folder/(split+'-results.json')).read_text())
        if len(items)!=expected[split] or len(results)!=len(items):raise ValueError('Reference validation incomplete')
        if json.loads((folder/'identity.json').read_text())!=checks.identity():raise ValueError('Reference policy mismatch')
        good=[r for r in items if r.get('truth')=='white'];bad=[r for r in items if r.get('truth')=='original']
        if len(good)+len(bad)!=len(items):raise ValueError('Every reference needs independent truth')
        approved_good=sum(results[r['file']]['decision']=='white' for r in good)
        unsafe=[r['file'] for r in bad if results[r['file']]['decision']!='original']
        recovery=approved_good/len(good)
        reports[split]={'total':len(items),'good':len(good),'good_recovered':approved_good,
            'good_recovery':recovery,'keep_original':len(bad),'unsafe_approvals':unsafe,
            'safety_passed':not unsafe,'recovery_target_met':recovery>=.95,'labels_sha256':sha256(audit/'reference'/(split+'.json')),
            'results_sha256':sha256(folder/(split+'-results.json'))}
    good=sum(r['good'] for r in reports.values());recovered=sum(r['good_recovered'] for r in reports.values())
    safety=all(not r['unsafe_approvals'] for r in reports.values())
    overall={'good':good,'good_recovered':recovered,'good_recovery':recovered/good,
             'safety_passed':safety,'recovery_target_met':recovered/good>=.95}
    return {'checks_identity':checks.decision_identity(),'splits':reports,'overall':overall,
            'passed':safety and overall['recovery_target_met'] and reports['holdout']['good_recovery']>=.95}


def reference_qualification(audit,report):
    """Keep recovery-contract results intact when an explicit conservative mode is chosen."""
    result={'accepted':report['passed'],'mode':'original_recovery_contract',
            'original_recovery_contract_passed':report['passed']}
    path=audit/'selection-policy.json'
    if not path.exists():return result
    policy=json.loads(path.read_text())
    if policy.get('checks_identity')!=checks.decision_identity():raise ValueError('Selection policy identity changed')
    if policy.get('mode')!='conservative_keep_uncertain_originals':raise ValueError('Unknown selection policy')
    if report['checks_identity']!=checks.decision_identity():raise ValueError('Reference checks identity changed')
    safe=report['overall']['safety_passed'] and all(not split['unsafe_approvals'] for split in report['splits'].values())
    return {**result,'accepted':safe,'mode':policy['mode'],'selection_policy_sha256':sha256(path)}


def pilot_manifest(audit,db):
    path=audit/'pilot-manifest.json'
    if path.exists():return json.loads(path.read_text())
    refs=[]
    for split in ('calibration','holdout'):refs.extend(r['file'] for r in json.loads((audit/'reference'/(split+'.json')).read_text()))
    if len(set(refs))!=len(refs) or not 210<=len(refs)<=500:raise ValueError('Reference split count or overlap invalid')
    remaining=[r[0] for r in db.execute('SELECT file FROM images ORDER BY n') if r[0] not in set(refs)]
    files=refs+random.Random(2026101703).sample(remaining,500-len(refs))
    result={'files':files,'seed':2026101703,'reference_count':len(refs),'additional_random':500-len(refs),
        'checks_identity':checks.decision_identity()}
    atomic_json(path,result);return result


def review_rows(job,audit,db,rows,phase,workers=WORKERS,tick=None):
    key=api_key('/Users/matt/.omlx/settings.json');started=time.time();initial=0;done=0
    future_images=0;mini_manifest=audit/'mini-packet/manifest.json'
    if phase=='re_auditing_existing_jpgs' and mini_manifest.exists():
        known={row['file'] for row in rows}
        known.update(row[0] for row in db.execute("SELECT file FROM images WHERE decision IN ('white','original')"))
        future_images=sum(row['file'] not in known for row in json.loads(mini_manifest.read_text())['images'])
    todo=[]
    for row in rows:
        cached=cached_result(db,row)
        if cached:
            decision,reason=checks.choose(row,cached[0],cached[1],cached[2].get('focus'))
            with db:db.execute('UPDATE images SET decision=?,reason=? WHERE file=?',(decision,reason,row['file']))
            initial+=1
        else:todo.append(row)
    total=len(rows);progress(audit,db,phase,started,phase_done=initial,phase_total=total,eta_at=None)
    from white_jpeg_review_queue import ReviewQueue
    iterator=ReviewQueue(audit,todo,checks.decision_identity());errors=[];last_tick=time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending={}
        def submit():
            row=next(iterator,None)
            if row is not None:pending[pool.submit(checks.assess,job,row,key,region_cache=audit/'region-cache')]=row
        for _ in range(workers):submit()
        while pending:
            finished,_=wait(pending,timeout=30,return_when=FIRST_COMPLETED)
            for future in finished:
                row=pending.pop(future)
                try:
                    m,review,details=future.result()
                    save_result(db,row,m,review,details);done+=1
                except Exception as error:errors.append(error)
            # Drain every in-flight result on an error, including valid negative reviews.
            # A transient outage must never discard an unfavorable verdict and retry it.
            if not errors:
                for _ in finished:submit()
            elapsed=time.time()-started
            eta=time.time()+elapsed/max(done,1)*(total-initial-done) if done else None
            estimate={}
            if (phase=='re_auditing_existing_jpgs' and done>=100) or (phase=='reviewing_new_white_jpgs' and done>=10):
                estimate={'estimated_complete_at':eta+elapsed/done*future_images+900,
                    'estimate_basis':f'Current review throughput, including {future_images:,} later converted-image reviews and final verification; subject to local service availability.'}
            progress(audit,db,phase,started,phase_done=initial+done,phase_total=total,eta_at=eta,
                throughput_images_per_hour=3600*done/elapsed if done else None,**estimate)
            if done and done%100==0:print(json.dumps({'phase':phase,'done':initial+done,'total':total,'seconds':elapsed}),flush=True)
            if tick and time.time()-last_tick>=300:
                tick();last_tick=time.time()
    if errors:raise errors[0]
    return {'newly_reviewed':done,'cached':initial,'seconds':time.time()-started,'total':total}


def pilot(job,audit,db):
    refs=reference_report(audit);atomic_json(audit/'reference-validation.json',refs)
    qualification=reference_qualification(audit,refs)
    if not qualification['accepted']:raise ValueError('Reference checks failed; catalog processing is held')
    seed_references(job,audit,db);manifest=pilot_manifest(audit,db)
    rows=[json.loads(db.execute('SELECT row_json FROM images WHERE file=?',(f,)).fetchone()[0]) for f in manifest['files']]
    checks.status(audit,'validating_pilot',pilot_state='500-image pilot running')
    timing=review_rows(job,audit,db,rows,'validating_pilot')
    records=[dict(db.execute('SELECT file,decision,reason FROM images WHERE file=?',(f,)).fetchone()) for f in manifest['files']]
    report={'state':'awaiting_visual_spot_check','checks_identity':checks.decision_identity(),
        'manifest_sha256':sha256(audit/'pilot-manifest.json'),'reference_validation_sha256':sha256(audit/'reference-validation.json'),
        'references':refs,'qualification':qualification,'timing':timing,'decisions':records,'created_at':time.time()}
    atomic_json(audit/'pilot-results.json',report)
    progress(audit,db,'pilot_awaiting_visual_spot_check',pilot_state='Awaiting independent review of pilot selections',
        pilot_summary={'images':500,'references_passed':refs['passed'],'qualification':qualification,'visual_spot_check':'pending'},eta_at=None)
    return report


def validate_source_pilot(audit):
    folder=audit/'source-only-pilot'
    report=json.loads((folder/'qualified-validation.json').read_text())
    results=folder/'qualified-results.json'
    if (report.get('passed') is not True or report.get('checks_identity')!=checks.decision_identity() or
        report.get('count')!=13 or report.get('studio_sources')!=8 or report.get('scene_controls')!=5 or
        report.get('qualified_results_sha256')!=sha256(results)):
        raise ValueError('Source eligibility pilot missing, changed or unqualified')
    evidence=json.loads(results.read_text())
    if len(evidence)!=13:raise ValueError('Source eligibility pilot is incomplete')
    for file,result in evidence.items():
        row={'file':file,'source_sha256':result['source_sha256'],'output_file':None}
        original,_=checks.load_pair(audit.parent,row)
        decision,_=checks.choose(row,checks.features(original),result['review'])
        if decision!=result['expected']:raise ValueError('Source eligibility pilot decision changed')
    return report


def validate_pilot(audit):
    report=json.loads((audit/'pilot-validation.json').read_text())
    if report.get('passed') is not True or report['checks_identity']!=checks.decision_identity():raise ValueError('Validated pilot missing or outdated')
    if report['pilot_results_sha256']!=sha256(audit/'pilot-results.json'):raise ValueError('Pilot results changed after validation')
    current=reference_report(audit)
    qualification=reference_qualification(audit,current)
    results=json.loads((audit/'pilot-results.json').read_text())
    if (not qualification['accepted'] or qualification!=results['qualification'] or
        current!=json.loads((audit/'reference-validation.json').read_text())):raise ValueError('Reference validation changed')
    manifest=json.loads((audit/'pilot-manifest.json').read_text())
    if manifest['checks_identity']!=checks.decision_identity() or len(manifest['files'])!=500:raise ValueError('Pilot identity or count changed')
    if report.get('reviewed_accepted',0)<32 or report.get('unsafe_accepted',1)!=0:raise ValueError('Pilot visual acceptance failed')
    validate_source_pilot(audit)
    return report


def prepare_mini(job,audit,db):
    config_path=audit/'mini-config.json'
    if config_path.exists():return json.loads(config_path.read_text())
    rows=[json.loads(r[0]) for r in db.execute("SELECT row_json FROM images WHERE decision='eligible' ORDER BY n")]
    if not rows:return None
    if any(r.get('output_file') for r in rows):raise ValueError('Conversion must only process missing candidates')
    packet=audit/'mini-packet';packet.mkdir(exist_ok=True)
    manifest={'schema':1,'originals':str(checks.original_root(job)),
        'images':[{'n':n,'file':r['file'],'sha256':r['source_sha256'],'bytes':r['source_bytes']} for n,r in enumerate(rows,1)]}
    path=packet/'manifest.json'
    if path.exists() and json.loads(path.read_text())!=manifest:raise ValueError('Mini allowlist changed')
    atomic_json(path,manifest);config=json.loads((job/'config.json').read_text());config['manifest_sha256']=sha256(path)
    atomic_json(packet/'config.json',config);worker=Path(__file__).with_name('white_jpeg_worker.py');shutil.copy2(worker,packet/worker.name)
    spec={'Label':LABEL,'ProgramArguments':['/usr/bin/caffeinate','-i',export.REMOTE_PYTHON,'-B',str(REMOTE/worker.name),'run','--job',str(REMOTE)],
        'RunAtLoad':True,'KeepAlive':{'SuccessfulExit':False},'ThrottleInterval':300,'ExitTimeOut':60,
        'WorkingDirectory':str(REMOTE),'EnvironmentVariables':{'PYTHONDONTWRITEBYTECODE':'1','NUMBA_CACHE_DIR':str(REMOTE/'numba-cache')},
        'StandardOutPath':str(REMOTE/'worker.log'),'StandardErrorPath':str(REMOTE/'worker-error.log')}
    (packet/'worker.plist').write_bytes(plistlib.dumps(spec))
    # Read-only process check prevents loading a second 11 GiB segmentation session.
    processes=export.remote(['/bin/ps','-axo','pid=,command=']).stdout
    if any('white_jpeg_worker.py run' in line and str(REMOTE) not in line for line in processes.splitlines()):
        raise RuntimeError('Another Mini conversion worker is active')
    export.remote(['mkdir','-p',REMOTE]);export.sync(str(packet)+'/',export.TARGET+':'+str(REMOTE)+'/')
    loaded=export.remote(['/bin/launchctl','print','gui/501/'+LABEL],check=False)
    if loaded.returncode:
        agent=Path('/Users/matt/Library/LaunchAgents')/(LABEL+'.plist')
        export.remote(['/usr/bin/install','-m','600',REMOTE/'worker.plist',agent]);export.remote(['/bin/launchctl','bootstrap','gui/501',agent])
    info={'target':export.TARGET,'remote_job':str(REMOTE),'remote_python':export.REMOTE_PYTHON,'remote_worker':str(REMOTE/worker.name),
        'eligible_count':len(rows),'manifest_sha256':config['manifest_sha256']}
    atomic_json(config_path,info);return info


def mini_status(audit):
    info=json.loads((audit/'mini-config.json').read_text())
    result=export.remote([info['remote_python'],'-B',info['remote_worker'],'status','--job',info['remote_job'],'--json'],retries=3)
    value=json.loads(result.stdout)
    if value['manifest_sha256']!=info['manifest_sha256']:raise ValueError('Mini allowlist identity changed')
    atomic_json(audit/'mini-status.json',value);return value


def import_mini(job,audit,db):
    if (audit/'mini-imported.json').exists():return
    info=json.loads((audit/'mini-config.json').read_text());destination=audit/'finished-mini';destination.mkdir(exist_ok=True)
    committed=db.execute("SELECT value FROM meta WHERE key='calibrated_mini_import'").fetchone()
    if committed:
        value=json.loads(committed[0])
        if value['manifest_sha256']!=info['manifest_sha256']:raise ValueError('Mini import transaction identity changed')
        atomic_json(audit/'mini-imported.json',value);return
    export.sync(export.TARGET+':'+str(REMOTE)+'/media/',str(destination/'media')+'/')
    export.sync(export.TARGET+':'+str(REMOTE)+'/mapping.csv',destination/'mapping.csv')
    with (destination/'mapping.csv').open() as stream:results=list(csv.DictReader(stream))
    expected={r['file']:r for r in json.loads((audit/'mini-packet/manifest.json').read_text())['images']}
    if len(results)!=len(expected) or {r['original_file'] for r in results}!=set(expected):raise ValueError('Mini results do not match pinned allowlist')
    updates=[]
    for result in results:
        record=db.execute('SELECT * FROM images WHERE file=?',(result['original_file'],)).fetchone();row=json.loads(record['row_json'])
        if record['decision']!='eligible' or row.get('output_file'):raise ValueError('Mini result outside eligible missing-candidate set')
        if result['original_sha256']!=row['source_sha256'] or sha256(checks.original_root(job)/row['file'])!=row['source_sha256']:
            raise ValueError('Mini source identity mismatch')
        if result['state']=='done':
            row.update(output_file=result['output_file'],output_sha256=result['output_sha256'],output_bytes=int(result['output_bytes']),
                warning=result['warning'] or None,output_path=str(destination/'media/wands-expanded'/result['output_file']),audit_new_conversion=True)
            checks.load_pair(job,row);updates.append((json.dumps(row),None,None,row['file']))
        else:updates.append((json.dumps(row),'original','conversion_failed_keep_original',row['file']))
    # All copies validate before any row is updated. A restart can repeat the transaction safely.
    receipt={'state':'complete','count':len(updates),'verified_at':time.time(),
        'manifest_sha256':info['manifest_sha256'],'mapping_sha256':sha256(destination/'mapping.csv')}
    with db:
        for content,decision,reason,file in updates:
            db.execute('UPDATE images SET row_json=?,decision=?,reason=? WHERE file=?',(content,decision,reason,file))
            db.execute('DELETE FROM calibrated_features WHERE file=?',(file,))
        db.execute("INSERT INTO meta VALUES('calibrated_mini_import',?)",(json.dumps(receipt),))
    atomic_json(audit/'mini-imported.json',receipt)


def poll_mini(job,audit,db):
    if (audit/'mini-imported.json').exists():return
    try:value=mini_status(audit)
    except (OSError,subprocess.TimeoutExpired) as error:
        checks.status(audit,'re_auditing_existing_jpgs',mini_connection_warning=type(error).__name__);return
    except RuntimeError as error:
        if not any(x in str(error).lower() for x in ('timed out','refused','connection reset','broken pipe','connection closed','unreachable','no route')):raise
        checks.status(audit,'re_auditing_existing_jpgs',mini_connection_warning=str(error));return
    checks.status(audit,'re_auditing_existing_jpgs',mini_connection_warning=None)
    if value['state'] in {'complete','complete_with_errors'}:import_mini(job,audit,db)
    elif value['state'] not in {'running','loading_model','verifying'}:raise RuntimeError('Mini needs attention: '+value['state'])


def ensure_mini(job,audit,db):
    """A temporary LAN outage may delay the Mini without discarding local reviews."""
    try:
        if (audit/'mini-config.json').exists():poll_mini(job,audit,db)
        else:prepare_mini(job,audit,db)
    except subprocess.TimeoutExpired as error:
        checks.status(audit,'re_auditing_existing_jpgs',mini_connection_warning=type(error).__name__)
    except subprocess.CalledProcessError as error:
        if error.returncode not in {12,255}:raise
        checks.status(audit,'re_auditing_existing_jpgs',mini_connection_warning='Mini transfer interrupted; will resume.')
    except RuntimeError as error:
        if not any(x in str(error).lower() for x in ('timed out','refused','connection reset','broken pipe','connection closed','unreachable','no route')):raise
        checks.status(audit,'re_auditing_existing_jpgs',mini_connection_warning=str(error))


def run(job,audit,db):
    accepted=validate_pilot(audit)
    checks.status(audit,'re_auditing_existing_jpgs',pilot_state='passed',pilot_summary=accepted['summary'])
    if (audit/'verification.json').exists():return
    rows=[json.loads(r[0]) for r in db.execute("SELECT row_json FROM images WHERE json_extract(row_json,'$.output_file') IS NULL AND decision IS NULL ORDER BY n")]
    review_rows(job,audit,db,rows,'checking_remaining_sources')
    mini_needed=(audit/'mini-config.json').exists() or bool(db.execute("SELECT 1 FROM images WHERE decision='eligible' LIMIT 1").fetchone())
    if mini_needed:ensure_mini(job,audit,db)
    rows=[json.loads(r[0]) for r in db.execute("SELECT row_json FROM images WHERE json_extract(row_json,'$.output_file') IS NOT NULL AND decision IS NULL ORDER BY n")]
    review_rows(job,audit,db,rows,'re_auditing_existing_jpgs',tick=(lambda:ensure_mini(job,audit,db)) if mini_needed else None)
    if mini_needed:
        while not (audit/'mini-imported.json').exists():
            ensure_mini(job,audit,db)
            if (audit/'mini-imported.json').exists():break
            progress(audit,db,'finishing_remaining_product_shots');time.sleep(30)
        rows=[json.loads(r[0]) for r in db.execute('SELECT row_json FROM images WHERE decision IS NULL ORDER BY n')]
        review_rows(job,audit,db,rows,'reviewing_new_white_jpgs')
    if db.execute("SELECT count(*) FROM images WHERE decision IS NULL OR decision NOT IN ('white','original')").fetchone()[0]:
        raise ValueError('Unresolved selection decisions remain')
    # The selection writes only a new derivative tree and a separate import CSV.
    progress(audit,db,'building_verified_selection',phase_done=0,phase_total=95401,eta_at=None)
    export.select(job,audit,review_method='Pilot-validated studio eligibility and individual native original/candidate product review',
        progress_callback=lambda i:progress(audit,db,'building_verified_selection',phase_done=i,phase_total=95401,eta_at=None),
        expected_original_csv_sha256=json.loads((audit/'source-integrity.json').read_text())['original_media_csv_sha256'])
    report=json.loads((audit/'verification.json').read_text());report.update(pilot_validation_sha256=sha256(audit/'pilot-validation.json'),
        checks_identity=checks.decision_identity(),individual_pair_reviews=db.execute("SELECT count(*) FROM calibrated_reviews WHERE kind='pair'").fetchone()[0])
    atomic_json(audit/'verification.json',report)
    progress(audit,db,'complete',phase_done=95401,phase_total=95401,eta_at=None)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['pilot','run']);p.add_argument('--job',type=Path,required=True);p.add_argument('--audit',type=Path,required=True)
    args=p.parse_args();job=args.job.resolve();audit=args.audit.resolve()
    with (audit/'controller.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('An audit controller is already running.',flush=True);return
        db,ident=initialize(job,audit)
        try:
            while True:
                try:
                    if args.command=='pilot':pilot(job,audit,db)
                    else:run(job,audit,db)
                    break
                except ReviewServiceUnavailable:
                    progress(audit,db,'waiting_for_local_review_service',error='Local image review service unavailable; completed decisions are checkpointed.',eta_at=None)
                    time.sleep(60)
        except BaseException as error:
            progress(audit,db,'needs_attention',error=str(error),eta_at=None);raise
        finally:db.close()


if __name__=='__main__':main()
