#!/usr/bin/env python3
"""Finish the approved two-store expansion after the accepted export exists.

No additional approval, provisioning, publication or Git operation is performed.
Image readiness is an artifact requirement. Failed imports retain the exact
partial state and row inverse; they are never blindly retried.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import base64
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit, urlencode

from bulk_expansion_images import atomic_json, lock
from build_expanded_catalog import csv_rows, variations
from build_expansion_inverse import build as build_inverse
from expansion_module import FILES
from prepare_catalog import sha256
from prepare_expansion_deployment import verified_export, prepare_deployment, CANDIDATE_SHA256
from run_expansion_native_imports import execute as native_execute
from verify_expansion_install import compare

SOURCE = Path(__file__).resolve().parent
LOCAL = Path('/Users/matt/code/mageos-latest')
REMOTE = Path('/opt/comtom/stores/relevance/src')
RUNTIME = Path('/var/www/html')
SSH = ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=30',
       '-o','ControlMaster=auto','-o','ControlPersist=600','-o','ControlPath=/tmp/codex-wands-comtom-%C']
TOOLS = ('expansion_store_snapshot.php','expansion_catalog_journal.php','expansion_database_backup.php',
         'restore_expansion_catalog.php','expansion_media.php','expansion_setup.php','expansion_live_probe.php',
         'run_expansion_native_imports.py','expansion_module.py')


def private_json(path, value):
    atomic_json(path,value);path.chmod(0o600)


def stage_images(package, root, manifest):
    if root != LOCAL:raise ValueError('Local media staging requires the existing Studio store')
    target=root/'pub/media/import/wands-expanded'
    if target.resolve()!=root.resolve()/'pub/media/import/wands-expanded':
        raise ValueError('Unexpected symlink in the media staging directory')
    target.mkdir(parents=True,exist_ok=True)
    count=0
    for name,info in manifest['files'].items():
        if not name.startswith('media/'):continue
        relative=Path(name)
        if relative.parts[:2]!=('media','wands-expanded') or len(relative.parts)!=3 or relative.name!=info['sha256']+'.jpg':
            raise ValueError('Only accepted hash-named image files may be staged')
        source=package/relative;dest=target/relative.name
        if sha256(source)!=info['sha256']:raise ValueError('Accepted source image changed')
        if dest.exists():
            if dest.is_symlink() or sha256(dest)!=info['sha256']:raise ValueError('Existing staged image differs; no overwrite')
        else:
            # Same-volume immutable hardlinks avoid another full media copy.
            # Native Magento import still makes its own gallery file.
            try:os.link(source,dest)
            except OSError:
                with tempfile.NamedTemporaryFile(dir=target,delete=False) as out:
                    with source.open('rb') as incoming:shutil.copyfileobj(incoming,out)
                    temporary=Path(out.name)
                try:os.link(temporary,dest)
                finally:temporary.unlink()
            if sha256(dest)!=info['sha256']:raise ValueError('Staged image hash mismatch')
        count+=1
    return count


def probe_cases(package):
    products={r['sku']:r for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv') for r in csv_rows(package/'data'/name)}
    result=[];departments=set()
    for row in products.values():
        if not row['sku'].startswith('WANDS-SYN-') or row['product_type']!='simple' or row['product_online']!='1' or row['visibility']=='Not Visible Individually':continue
        parts=row['categories'].split(',')[0].split('/');department=parts[1] if len(parts)>1 else ''
        if department in departments:continue
        departments.add(department);result.append({'sku':row['sku'],'name':row['name'],'selected_sku':row['sku'],'type':'simple',
            'options':{},'price':float(row.get('special_price') or row['price']),'department':department})
    config_departments=set()
    for row in products.values():
        if row['product_type']!='configurable' or not row['sku'].startswith('WANDS-SYN-'):continue
        department=row['categories'].split(',')[0].split('/')[1]
        if department in config_departments:continue
        config_departments.add(department)
        eligible=[g for g in variations(row) if products[g['sku']]['product_online']=='1']
        if not eligible:raise ValueError('Configurable family has no healthy choices')
        group=eligible[0];child=products[group['sku']]
        result.append({'sku':row['sku'],'name':row['name'],'selected_sku':child['sku'],'type':'configurable',
            'options':{k:v for k,v in group.items() if k!='sku'},'price':float(child.get('special_price') or child['price']),
            'department':'configurable'})
        if len(config_departments)==3:break
    for row in products.values():
        if row['product_type']!='configurable' or row['sku'].startswith('WANDS-SYN-'):continue
        extended=[g for g in variations(row) if g['sku'].startswith('WANDS-SYN-') and products[g['sku']]['product_online']=='1']
        if not extended:continue
        group=extended[0];child=products[group['sku']]
        result.append({'sku':row['sku'],'name':row['name'],'selected_sku':child['sku'],'type':'configurable',
            'options':{k:v for k,v in group.items() if k!='sku'},'price':float(child.get('special_price') or child['price']),
            'department':'extended-existing-family'})
        break
    if len(departments)!=11 or len(result)!=15:raise ValueError('Expected eleven departments and four configurable cart samples')
    return result


class Destination:
    def __init__(self,root,output,token):
        if root not in (LOCAL,REMOTE):raise ValueError('Only the two existing stores are supported')
        self.root=root;self.runtime=LOCAL if root==LOCAL else RUNTIME
        self.name='local' if root==LOCAL else 'comtom';self.output=output/self.name
        self.output.mkdir(mode=0o700);self.stage=root/'var'/('catalog-expansion-install-'+token)
        self.log=self.output/'commands.log';self.counter=0

    def command(self,args,*,capture=None):
        self.counter+=1
        argv=[str(x) for x in args]
        if self.root==REMOTE:argv=[*SSH,'comtom',shlex.join(argv)]
        with self.log.open('ab') as log:
            stream=capture.open('xb') if capture else log
            if capture:capture.chmod(0o600)
            try:p=subprocess.run(argv,cwd=self.root if self.root==LOCAL else SOURCE,stdout=stream,stderr=log)
            finally:
                if capture:stream.close()
        if p.returncode:raise RuntimeError(self.name+' command '+str(self.counter)+' failed; inspect its private log')

    def php(self,tool,*args,capture=None):
        prefix=['/opt/homebrew/bin/php','-d','memory_limit=3G'] if self.root==LOCAL else [
            'docker','exec','--user','www-data','-w','/var/www/html','farm-relevance-php-1','php','-d','memory_limit=3G']
        script=self.runtime/'bin/magento' if tool=='magento' else self.runtime/self.stage.relative_to(self.root)/'tools'/tool
        self.command([*prefix,script,*args],capture=capture)

    def sync(self,source,dest,*,immutable=False):
        if self.root==LOCAL:
            if immutable:raise ValueError('Use verified local immutable media staging')
            if source.is_dir():shutil.copytree(source,dest)
            else:shutil.copy2(source,dest)
        else:
            with self.log.open('ab') as log:
                p=subprocess.run(['rsync','-a' if immutable else '-az','--partial-dir=.rsync-partial',*(['--ignore-existing'] if immutable else []),'-e',shlex.join(SSH),str(source)+('/' if source.is_dir() else ''),
                    'comtom:'+str(dest)+('/' if source.is_dir() else '')],stdout=log,stderr=log)
            if p.returncode:raise RuntimeError('Comtom transfer failed; no import retried')

    def fetch(self,source,dest):
        if self.root==LOCAL:
            if source.is_dir():shutil.copytree(source,dest)
            else:shutil.copy2(source,dest)
        else:
            with self.log.open('ab') as log:
                p=subprocess.run(['rsync','-az','-e',shlex.join(SSH),'comtom:'+str(source)+('/' if source.suffix=='' else ''),
                                  str(dest)+('/' if source.suffix=='' else '')],stdout=log,stderr=log)
            if p.returncode:raise RuntimeError('Private Comtom evidence transfer failed')
        if dest.is_file():dest.chmod(0o600)

    def runtime_path(self,name):return self.runtime/self.stage.relative_to(self.root)/name

    def snapshot(self,name):
        path=self.output/name
        self.php('expansion_store_snapshot.php','--root='+str(self.runtime),capture=path)
        return path

    def journal(self,name):
        self.php('expansion_catalog_journal.php','--root='+str(self.runtime),'--output='+str(self.runtime_path(name)))
        self.fetch(self.stage/name,self.output/name)
        return self.output/name

    def stage_inverse(self,inverse,side):
        self.sync(inverse,self.stage/inverse.name);self.sync(side,self.stage/side.name)
        if self.root==REMOTE:
            self.command(['chown','33:33',self.stage/inverse.name,self.stage/side.name])


def verify_module(target):
    expected={name:sha256(SOURCE.parents[2]/'app/code/RocketWeb/LabCatalog'/name) for name in FILES}
    code=('import json,hashlib;from pathlib import Path;root=Path('+repr(str(target.root/'app/code/RocketWeb/LabCatalog'))+');'
          'names='+repr(list(FILES))+';print(json.dumps({n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}))')
    path=target.output/'module-current.json';target.command(['python3','-c',code],capture=path)
    if json.loads(path.read_text())!=expected:raise ValueError(target.name+' module bytes drifted from the verified implementation')


def complete_store(target,package,candidate,run,manifest,cases,reconciliation=None,media_resume=None):
    target.command(['python3','-c','from pathlib import Path;import os;p=Path('+repr(str(target.stage))+');p.mkdir(mode=0o700);(p/"tools").mkdir(mode=0o700)'])
    for name in TOOLS:target.sync(SOURCE/name,target.stage/'tools'/name)
    target.sync(package/'data/media-lineage.json',target.stage/'media-lineage.json')
    target.sync(package/'data/attribute-options.json',target.stage/'attribute-options.json')
    if manifest.get('catalog_quarantine_sha256'):target.sync(package/'catalog-quarantine.json',target.stage/'catalog-quarantine.json')
    request=target.output/'probe-request.json';private_json(request,cases);target.sync(request,target.stage/request.name)
    verify_module(target)
    if target.root==LOCAL:
        stage_images(package,target.root,manifest)
    else:
        media_directory=target.root/'pub/media/import/wands-expanded'
        target.command(['python3','-c','from pathlib import Path;p=Path('+repr(str(media_directory))+');'
            'assert p.resolve()==p,"Unexpected symlink in the media staging directory";p.mkdir(parents=True,exist_ok=True)'])
        target.sync(package/'media/wands-expanded',media_directory,immutable=True)
    # Verify remote bytes as well, before any database mutation.
    inventory={Path(n).name:p['sha256'] for n,p in manifest['files'].items() if n.startswith('media/')}
    inv=target.output/'accepted-media-hashes.json';private_json(inv,inventory);target.sync(inv,target.stage/inv.name)
    code=('import json,hashlib;from pathlib import Path;p=Path('+repr(str(target.stage/inv.name))+');'
        'd=Path('+repr(str(target.root/'pub/media/import/wands-expanded'))+');'
        'assert all(not (d/n).is_symlink() and hashlib.sha256((d/n).read_bytes()).hexdigest()==h for n,h in json.loads(p.read_text()).items());print("All staged accepted media hashes match")')
    target.command(['python3','-c',code])
    # Root stages over SSH, while container PHP runs as www-data. Assign only
    # this exact private stage before the first PHP snapshot can traverse it.
    if target.root==REMOTE:target.command(['chown','-R','33:33',target.stage])
    before=target.snapshot('before.json');deployment=target.output/'deployment'
    if media_resume:
        from media_tail_reconciliation import prepare_tail
        reconciliation=prepare_tail(package,before,deployment,media_resume)
    else:prepare_deployment(package,candidate,before,deployment,run=run,reconciliation=reconciliation)
    target.sync(deployment,target.stage/'deployment')
    # Comtom's PHP process runs as www-data. Keep private files private and
    # assign this exact new staging directory to its existing service owner.
    if target.root==REMOTE:target.command(['chown','-R','33:33',target.stage])
    options_pin=sha256(package/'data/attribute-options.json')
    target.php('expansion_setup.php','--root='+str(target.runtime),'--options='+str(target.runtime_path('attribute-options.json')),
        '--options-sha256='+options_pin,'--action=inspect','--output='+str(target.runtime_path('setup-preview.json')))
    target.fetch(target.stage/'setup-preview.json',target.output/'setup-preview.json')
    setup=json.loads((target.output/'setup-preview.json').read_text())['scope']
    if setup['pending_patches'] or setup['missing_options']:raise ValueError('Installed WANDS schema drifted from the completed setup')
    # Back up immediately before native import, after the media transfer.
    backup_args=['--root='+str(target.runtime),'--output='+str(target.runtime_path('database-before.sql.gz'))]
    if reconciliation:
        rec=target.output/'reconciliation.json';private_json(rec,reconciliation);target.sync(rec,target.stage/rec.name)
        backup_args+=['--reconciliation='+str(target.runtime_path(rec.name)),'--reconciliation-sha256='+sha256(rec)]
    target.php('expansion_database_backup.php',*backup_args)
    target.command(['tar','-czf',target.stage/'module-before.tar.gz','-C',target.root/'app/code/RocketWeb','LabCatalog'])
    target.command(['chmod','600',target.stage/'module-before.tar.gz'])
    before_journal=target.journal('catalog-before')
    recipe=target.output/'inverse-plan.json';private_json(recipe,{'before_journal_sha256':sha256(before_journal/'manifest.json'),
        'restore_tool_sha256':sha256(SOURCE/'restore_expansion_catalog.php'),'journal_tool_sha256':sha256(SOURCE/'expansion_catalog_journal.php'),
        'operation':'Capture exact after tables on success or failure, build changed-primary-key inverse, and use the tested conflict-checked transactional restore tool. Never restore protected rows or blindly retry a partial import.'})
    target.sync(recipe,target.stage/recipe.name)
    artifacts={}
    for kind,name in [('database','database-before.sql.gz'),('module','module-before.tar.gz'),('inverse',recipe.name)]:
        receipt=target.output/(kind+'-hash.json')
        target.command(['python3','-c','import json,hashlib;from pathlib import Path;p=Path('+repr(str(target.stage/name))+');assert p.stat().st_mode&0o077==0;print(json.dumps({"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}))'],capture=receipt)
        artifacts[kind]={'path':str(target.stage/name),'sha256':json.loads(receipt.read_text())['sha256']}
    backup=target.output/'backup-receipt.json';private_json(backup,{'target_root':str(target.runtime),
        'before_snapshot_sha256':sha256(before),'created_at':datetime.now(timezone.utc).isoformat(),**artifacts})
    target.sync(backup,target.stage/backup.name)
    if target.root==REMOTE:target.command(['chown','-R','33:33',target.stage])
    plan_pin=sha256(deployment/'deployment.json');mutations_started=False
    try:
        mutations_started=True
        if target.root==LOCAL:
            native_execute(LOCAL,target.stage/'deployment',plan_pin,target.stage/'native-receipts',before,
                target.stage/'tools/expansion_store_snapshot.php',target.stage/backup.name,True)
        else:
            target.sync(before,target.stage/'before.json');target.command(['chown','33:33',target.stage/'before.json'])
            target.command(['python3',target.stage/'tools/run_expansion_native_imports.py','--root',REMOTE,
                '--plan-dir',target.stage/'deployment','--plan-sha256',plan_pin,'--output',target.stage/'native-receipts',
                '--before-snapshot',target.stage/'before.json','--snapshot-tool',target.stage/'tools/expansion_store_snapshot.php',
                '--backups',target.stage/backup.name,'--apply'])
        for action,filename in [('inspect','media-preview.json'),('apply','media-applied.json')]:
            args=['--root='+str(target.runtime),'--lineage='+str(target.runtime_path('media-lineage.json')),
                  '--action='+action,'--output='+str(target.runtime_path(filename))]
            if manifest.get('catalog_quarantine_sha256'):
                args+=['--quarantine='+str(target.runtime_path('catalog-quarantine.json')),
                       '--quarantine-sha256='+sha256(package/'catalog-quarantine.json')]
            if action=='apply':args+=['--plan='+str(target.runtime_path('media-preview.json'))]
            target.php('expansion_media.php',*args)
        target.php('magento','lab:wands:curate-navigation')
        target.php('magento','indexer:reindex')
        target.php('magento','cache:clean','config','eav','block_html','full_page')
        after=target.snapshot('after.json')
        rows={r['sku']:r for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv') for r in csv_rows(package/'data'/name)}
        links={(sku,g['sku']) for sku,row in rows.items() if row['product_type']=='configurable' for g in variations(row)}
        verification_before=Path(reconciliation['original_snapshot']) if reconciliation else before
        result=compare(json.loads(verification_before.read_text()),json.loads(after.read_text()),rows,links)
        private_json(target.output/'database-acceptance.json',result)
        if not result['passed']:raise ValueError('Installed product identity, links, stock or protected data verification failed')
        probe_args=['--root='+str(target.runtime),'--request='+str(target.runtime_path(request.name)),
            '--request-sha256='+sha256(request),'--output='+str(target.runtime_path('cart-model-acceptance.json'))]
        if manifest.get('catalog_quarantine_sha256'):
            probe_args+=['--quarantine='+str(target.runtime_path('catalog-quarantine.json')),
                         '--quarantine-sha256='+sha256(package/'catalog-quarantine.json')]
        target.php('expansion_live_probe.php',*probe_args)
        target.fetch(target.stage/'cart-model-acceptance.json',target.output/'cart-model-acceptance.json')
        return result
    finally:
        if mutations_started:
            # An inverse is formed for the actual state, including a failed
            # partial import. No database restore is executed automatically.
            after_journal=target.journal('catalog-after')
            inverse=target.output/'catalog-inverse.jsonl.gz'
            build_inverse(before_journal,after_journal,inverse,
                evidence_paths=(target.stage/'catalog-before',target.stage/'catalog-after') if target.root==REMOTE else None)
            # Build on Studio, then bind the remote restore paths to Comtom's
            # container filesystem rather than the local evidence copies.
            side=inverse.with_suffix('.gz.json');record=json.loads(side.read_text())
            record['before']=str(target.runtime_path('catalog-before'));record['after']=str(target.runtime_path('catalog-after'))
            private_json(side,record);target.stage_inverse(inverse,side)


def finish(run,package,output,watch=False,apply=False,reconciliation=None,media_resume=None):
    desc=json.loads((run/'run.json').read_text());candidate=Path(desc['candidate'])
    if desc['candidate_sha256']!=CANDIDATE_SHA256:raise ValueError('Only the approved expansion run may finish')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    with lock(run,'installation'),(output/'coordinator.lock').open('w') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while not (package/'manifest.json').is_file():
            private_json(output/'state.json',{'state':'waiting_for_accepted_export','run':str(run),'export':str(package),'updated':time.time(),'store_imports_started':False})
            if not watch:return {'state':'waiting_for_accepted_export','store_imports_started':False}
            time.sleep(30)
        manifest=verified_export(package,candidate,run)
        cases=probe_cases(package)
        if not apply:return {'state':'accepted_export_verified; installation_not_applied','cases':len(cases)}
        token=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');results={}
        for root in (LOCAL,REMOTE):
            target=Destination(root,output,token)
            private_json(output/'state.json',{'state':'installing','target':target.name,'completed_targets':list(results),'updated':time.time()})
            results[target.name]=complete_store(target,package,candidate,run,manifest,cases,reconciliation if root==LOCAL else None,media_resume if root==LOCAL else None)
            from verify_expansion_browser import browser_acceptance
            observed=json.loads((target.output/'cart-model-acceptance.json').read_text())['cases']
            browser_acceptance(root,observed,target.output)
        result={'state':'complete; both_existing_catalogs_installed_and_verified','targets':results,
            'updated':time.time(),'git_operations':0,'new_installations':0}
        private_json(output/'state.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('run','package','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--reconcile-local',type=Path);p.add_argument('--resume-local-media',type=Path);p.add_argument('--watch',action='store_true');p.add_argument('--apply',action='store_true');a=p.parse_args()
    try:print(json.dumps(finish(a.run.resolve(),a.package.resolve(),a.output.resolve(),a.watch,a.apply,json.loads(a.reconcile_local.read_text()) if a.reconcile_local else None,json.loads(a.resume_local_media.read_text()) if a.resume_local_media else None),indent=2))
    except Exception as error:
        if a.output.is_dir():private_json(a.output/'state.json',{'state':'needs_attention; no blind retry','error_type':type(error).__name__,'message':str(error),'updated':time.time()})
        raise
