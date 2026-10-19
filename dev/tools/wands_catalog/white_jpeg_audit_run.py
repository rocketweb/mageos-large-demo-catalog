#!/usr/bin/env python3
"""Run the reversible scene-preserving audit, finish its allowlist, and export."""
from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import sqlite3
import subprocess
import time
import csv

import white_jpeg_audit as audit_code
from white_jpeg_worker import atomic_json,sha256

TARGET='matt@192.168.1.115'
REMOTE=Path('/Users/matt/wands-image-worker/jobs/white-jpeg-eligible-20261017')
REMOTE_PYTHON='/Users/matt/wands-image-worker/benchmarks/background-benchmark-20261012/.venv/bin/python'
LABEL='com.matt.wands-white-jpeg-eligible-20261017'
SSH=['/usr/bin/ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',TARGET]


def remote(args,check=True,retries=1):
    # Retries are opt-in for read-only status checks. Mutations retain one attempt.
    for attempt in range(retries):
        result=subprocess.run(SSH+[shlex.join([str(x) for x in args])],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=60)
        transient=result.returncode==255 and any(message in result.stderr.lower() for message in
            ('operation timed out','connection timed out','connection refused','connection reset',
             'broken pipe','connection closed','no route to host','network is unreachable'))
        if transient and attempt+1<retries:
            print(json.dumps({'mini_status_connection_retry':attempt+1}),flush=True)
            time.sleep(5*(attempt+1));continue
        if check and result.returncode:raise RuntimeError('Mini command failed: '+result.stderr[-500:])
        return result


def sync(source,destination):
    subprocess.run(['/usr/bin/rsync','-rt','--partial','-e',shlex.join(SSH[:-1]),str(source),str(destination)],check=True,timeout=180)


def clone_copy(source,destination):
    """APFS copy-on-write clone, never a hard link back to the originals."""
    if destination.exists():
        if destination.is_symlink() or sha256(destination)!=destination.stem:raise ValueError('Changed selected file: '+str(destination))
        if source.stat().st_ino==destination.stat().st_ino:raise ValueError('Selection aliases its source inode')
        return
    if os.uname().sysname=='Darwin':
        libc=ctypes.CDLL('/usr/lib/libSystem.B.dylib',use_errno=True)
        if libc.clonefile(os.fsencode(source),os.fsencode(destination),0)==0:return
        if ctypes.get_errno() not in {errno.EXDEV,errno.ENOTSUP,errno.EINVAL}:raise OSError(ctypes.get_errno(),'clonefile failed')
    shutil.copy2(source,destination)


def prepare_mini(job,audit):
    db=audit_code.connect(audit)
    rows=[json.loads(r[0]) for r in db.execute("SELECT row_json FROM images WHERE decision='eligible' ORDER BY n")]
    db.close()
    packet=audit/'mini-packet';packet.mkdir(exist_ok=True)
    manifest={'schema':1,'originals':json.loads((job/'manifest.json').read_text())['originals'],
              'images':[{'n':i,'file':r['file'],'sha256':r['source_sha256'],'bytes':r['source_bytes']} for i,r in enumerate(rows,1)]}
    path=packet/'manifest.json'
    if path.exists() and json.loads(path.read_text())!=manifest:raise ValueError('Eligible allowlist changed')
    atomic_json(path,manifest)
    if not rows:
        atomic_json(audit/'mini-status.json',{'state':'complete','done':0,'total':0,'failed':0})
        return False
    config=json.loads((job/'config.json').read_text());config['manifest_sha256']=sha256(path)
    atomic_json(packet/'config.json',config)
    worker=Path(__file__).with_name('white_jpeg_worker.py')
    shutil.copy2(worker,packet/worker.name)
    spec={'Label':LABEL,'ProgramArguments':['/usr/bin/caffeinate','-i',REMOTE_PYTHON,'-B',str(REMOTE/worker.name),'run','--job',str(REMOTE)],
          'RunAtLoad':True,'KeepAlive':{'SuccessfulExit':False},'ThrottleInterval':300,'ExitTimeOut':60,
          'WorkingDirectory':str(REMOTE),'EnvironmentVariables':{'PYTHONDONTWRITEBYTECODE':'1','NUMBA_CACHE_DIR':str(REMOTE/'numba-cache')},
          'StandardOutPath':str(REMOTE/'worker.log'),'StandardErrorPath':str(REMOTE/'worker-error.log')}
    (packet/'worker.plist').write_bytes(plistlib.dumps(spec))
    remote(['mkdir','-p',REMOTE])
    sync(str(packet)+'/',TARGET+':'+str(REMOTE)+'/')
    loaded=remote(['/bin/launchctl','print','gui/501/'+LABEL],check=False)
    if loaded.returncode:
        agent=Path('/Users/matt/Library/LaunchAgents')/(LABEL+'.plist')
        remote(['/usr/bin/install','-m','600',REMOTE/'worker.plist',agent])
        remote(['/bin/launchctl','bootstrap','gui/501',agent])
    atomic_json(audit/'mini-config.json',{'target':TARGET,'remote_job':str(REMOTE),'remote_python':REMOTE_PYTHON,
                'remote_worker':str(REMOTE/worker.name),'eligible_count':len(rows),'manifest_sha256':config['manifest_sha256']})
    print(json.dumps({'mini_eligible_allowlist':len(rows),'remote_job':str(REMOTE)}),flush=True)
    return True


def mini_status(audit):
    result=remote([REMOTE_PYTHON,'-B',REMOTE/'white_jpeg_worker.py','status','--job',REMOTE,'--json'],retries=3)
    state=json.loads(result.stdout)
    expected=json.loads((audit/'mini-config.json').read_text())['manifest_sha256']
    if state['manifest_sha256']!=expected:raise ValueError('Mini status belongs to another allowlist')
    atomic_json(audit/'mini-status.json',state);return state


def import_finished(job,audit):
    destination=audit/'finished-mini';destination.mkdir(exist_ok=True)
    sync(TARGET+':'+str(REMOTE)+'/media/',str(destination/'media')+'/')
    sync(TARGET+':'+str(REMOTE)+'/mapping.csv',destination/'mapping.csv')
    db=audit_code.connect(audit)
    originals=Path(json.loads((job/'manifest.json').read_text())['originals'])
    with (destination/'mapping.csv').open() as stream:
        results=list(csv.DictReader(stream))
    expected={r['file'] for r in json.loads((audit/'mini-packet/manifest.json').read_text())['images']}
    if len(results)!=len(expected) or {r['original_file'] for r in results}!=expected:
        db.close();raise ValueError('Mini results differ from its pinned allowlist')
    updates=[]
    try:
        for result in results:
            record=db.execute('SELECT * FROM images WHERE file=?',(result['original_file'],)).fetchone()
            if not record or record['decision']!='eligible':raise ValueError('Mini returned an image outside its allowlist')
            row=json.loads(record['row_json'])
            if result['original_sha256']!=row['source_sha256']:raise ValueError('Mini original identity changed')
            if result['state']=='done':
                row.update(output_file=result['output_file'],output_sha256=result['output_sha256'],
                           output_bytes=int(result['output_bytes']),warning=result['warning'] or None,
                           output_path=str(destination/'media/wands-expanded'/result['output_file']),
                           audit_new_conversion=True)
                n,m=audit_code.inspect_row(row,originals,destination/'media/wands-expanded')
                kind,reason=audit_code.decision(row,m,json.loads(record['scores']))
                updates.append((json.dumps(row),json.dumps(m),kind,reason,n))
            else:
                updates.append((record['row_json'],record['metrics'],'original','new_cutout_failed_keep_original',record['n']))
        # Validate every source and candidate before committing any imported decision.
        with db:
            db.executemany('UPDATE images SET row_json=?,metrics=?,decision=?,reason=? WHERE n=?',updates)
            if db.execute("SELECT count(*) FROM images WHERE decision='eligible'").fetchone()[0]:
                raise ValueError('Eligible images missing from Mini results')
        atomic_json(audit/'mini-imported.json',{'state':'complete','verified_at':time.time(),
                    'count':len(updates),'manifest_sha256':sha256(audit/'mini-packet/manifest.json'),
                    'mapping_sha256':sha256(destination/'mapping.csv')})
    finally:db.close()


def verify_source_csv(path,expected=None):
    actual=sha256(path)
    if expected is not None and actual!=expected:raise ValueError('Original media CSV changed during audit')
    return actual


def select(job,audit,review_method=None,progress_callback=None,expected_original_csv_sha256=None):
    db=audit_code.connect(audit);started=time.time()
    rows=db.execute('SELECT * FROM images ORDER BY n').fetchall()
    if len(rows)!=95401 or any(r['decision'] not in {'original','white'} for r in rows):raise ValueError('Audit selection is incomplete')
    originals=Path(json.loads((job/'manifest.json').read_text())['originals'])
    replacements_path=job/'audit-20261017/replacements/replacements.json'
    replacements={r['original_file']:r for r in json.loads(replacements_path.read_text())}
    if len(replacements)!=2:raise ValueError('Expected exactly two explicit mirror replacements')
    output=audit/'selected-media/wands-expanded';output.mkdir(parents=True,exist_ok=True)
    mappings=[];counts={'original':0,'white_reused':0,'white_new':0,'mirror_replacement':0};reasons={}
    for i,record in enumerate(rows,1):
        row=json.loads(record['row_json']);original=originals/row['file']
        if sha256(original)!=row['source_sha256']:raise ValueError('Original changed: '+row['file'])
        if row['file'] in replacements:
            replacement=replacements[row['file']];source=Path(replacement['replacement_file']);expected=replacement['sha256']
            action='mirror_replacement';reason='explicitly_authorized_new_mirror_on_white'
        elif record['decision']=='white':
            source=Path(row.get('output_path') or job/'media/wands-expanded'/row['output_file']);expected=row['output_sha256']
            action='white_new' if row.get('audit_new_conversion') else 'white_reused';reason=record['reason']
        else:
            source=original;expected=row['source_sha256'];action='original';reason=record['reason']
        if sha256(source)!=expected:raise ValueError('Selected source content changed')
        target=output/(expected+'.jpg');clone_copy(source,target)
        if sha256(target)!=expected:raise ValueError('Selected copy hash mismatch')
        counts[action]+=1;reasons[reason]=reasons.get(reason,0)+1
        mappings.append({'original_file':row['file'],'original_sha256':row['source_sha256'],
                         'selected_file':target.name,'selected_sha256':expected,'action':action,'reason':reason})
        if i%4096==0:
            if progress_callback:progress_callback(i)
            else:audit_code.progress(audit,db,'building_verified_selection',started)
    csv_path=audit/'selection.csv'
    with csv_path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(mappings[0]));writer.writeheader();writer.writerows(mappings)
    by_original={r['original_file']:r for r in mappings}
    accepted=originals.parent.parent
    source_csv=accepted/'data/4-media.csv';before=verify_source_csv(source_csv,expected_original_csv_sha256)
    data=audit/'selected-data';data.mkdir(exist_ok=True)
    assignments=0
    with source_csv.open(newline='') as stream,(data/'4-media.csv').open('w',newline='') as destination:
        reader=csv.DictReader(stream);writer=csv.DictWriter(destination,fieldnames=reader.fieldnames);writer.writeheader()
        for row in reader:
            for field in ('base_image','small_image','thumbnail'):
                value=row.get(field)
                if value:
                    mapping=by_original[Path(value).name]
                    row[field]=str(Path(value).with_name(mapping['selected_file']))
                    if not (output/mapping['selected_file']).is_file():raise ValueError('CSV references missing selected media')
            writer.writerow(row);assignments+=1
    if sha256(source_csv)!=before:raise ValueError('Original media CSV changed')
    report={'state':'complete','verified_at':time.time(),'images_audited':len(rows),'selection_mappings':len(mappings),
            'originals_hash_verified':len(rows),'selected_hashes_verified':len(mappings),'counts':counts,'reasons':reasons,
            'media_assignments':assignments,'selection_csv_sha256':sha256(csv_path),'media_csv_sha256':sha256(data/'4-media.csv'),
            'original_csv_sha256':before,'originals_modified':False,'catalog_imported':False,'published':False,
            'identity_sha256':sha256(audit/'identity.json'),'review_method':review_method or 'conservative background, product-preservation, and local SigLIP scene checks; uncertain results retain originals',
            'selected_media':str(output),'selected_data':str(data),'mirror_replacements':replacements}
    atomic_json(audit/'verification.json',report)
    if not progress_callback:audit_code.progress(audit,db,'complete',started)
    db.close()
    print(json.dumps(report,indent=2),flush=True)
    return report


def run(job,audit):
    audit.mkdir(parents=True,exist_ok=True)
    if (audit/'verification.json').exists():
        print('The audited selection is already complete; results remain preserved.',flush=True);return
    db=audit_code.initialize(job,audit);started=time.time()
    try:
        audit_code.measure(job,audit)
        audit_code.classify(job,audit,pending_only=True)
        has_mini=prepare_mini(job,audit)
        audit_code.classify(job,audit)
        if has_mini:
            while True:
                state=mini_status(audit)
                if state['state'] in {'complete','complete_with_errors'}:break
                if state['state'] not in {'running','loading_model','verifying'}:raise RuntimeError('Mini needs attention: '+state['state'])
                audit_code.progress(audit,db,'finishing_remaining_product_shots',started)
                time.sleep(30)
            import_finished(job,audit)
        select(job,audit)
    except BaseException as error:
        audit_code.progress(audit,db,'needs_attention',started,str(error));raise
    finally:db.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--job',type=Path,required=True);parser.add_argument('--audit',type=Path,required=True)
    args=parser.parse_args();run(args.job.resolve(),args.audit.resolve())


if __name__=='__main__':main()
