"""Approved remote-only enriched acceptance fixture; refuses automatic reruns."""
import argparse
import csv
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

ROOT = Path('/opt/comtom/wands-lab35-enriched')
SOURCE = Path('/opt/comtom/wands-lab35-acceptance/src')
PINS = {'medium':'6e83c128538a3c0bf336c06c4135aa2b19ad01abcd8754d707e9bedc62f6ef68',
        'full':'9ad4b9ed1a65d6253db2119f61a11e20eb6e3e1cec55da5a8519fd43d157fe8c'}
COMPOSE = ['docker','compose','-f',str(ROOT/'compose.yaml')]
CLI = COMPOSE + ['exec','-T','--user','www-data','php','php','-d','memory_limit=3G']
DB = COMPOSE + ['exec','-T','db','sh','-c', 'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb -uroot "$@"','db-client']
DUMP = COMPOSE + ['exec','-T','db','sh','-c',
    'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb-dump -uroot --single-transaction --routines --triggers "$@"','db-dump']


def run(stage, command, *, input=None, output=None):
    state = ROOT/'state.json'
    state.write_text(json.dumps({'stage':stage,'status':'running'}))
    with (ROOT/'receipts'/f'{stage}.log').open('ab') as log:
        result = subprocess.run(command,input=input,stdout=output or log,stderr=log)
    state.write_text(json.dumps({'stage':stage,'status':'complete' if result.returncode==0 else 'failed',
                                'exit_code':result.returncode}))
    if result.returncode:
        raise RuntimeError('Stage failed: '+stage)


def backup(database, name):
    with os.fdopen(os.open(ROOT/'receipts'/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as output:
        run('backup-'+database,DUMP+[database],output=output)


def merchandising(profile):
    data=ROOT/'src/var'/('wands-'+profile)/'data'
    destination=data/'5-merchandising.csv'
    if destination.exists(): raise RuntimeError('Merchandising phase already prepared')
    with destination.open('x',newline='') as output:
        writer=csv.DictWriter(output,fieldnames=['sku','related_skus','crosssell_skus'])
        writer.writeheader()
        for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv'):
            with (data/name).open() as source:
                for row in csv.DictReader(source):
                    if row.get('related_skus') or row.get('crosssell_skus'):
                        writer.writerow({k:row.get(k,'') for k in writer.fieldnames})
    os.chown(destination,33,33)
    run(profile+'-5-merchandising',CLI+['bin/magento','lab:wands:import',
        '--file=var/wands-'+profile+'/data/5-merchandising.csv'])


def bootstrap():
    if (ROOT/'bootstrap-started').exists():
        raise RuntimeError('Bootstrap already attempted; inspect receipts')
    (ROOT/'bootstrap-started').touch(exist_ok=False)
    for name in ('src','db','search','receipts'):
        (ROOT/name).mkdir()
    os.chown(ROOT/'search',1000,1000)
    credentials={key:'Lab35-'+secrets.token_urlsafe(28) for key in
                 ('LAB_DB_ROOT_PASSWORD','LAB_DB_PASSWORD','LAB_ADMIN_PASSWORD')}
    with os.fdopen(os.open(ROOT/'.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as output:
        output.write(''.join(k+'='+v+'\n' for k,v in credentials.items()))
    # Explicit code directories only. No source env.php, auth.json, runtime data or database.
    for name in ('app','bin','lib','setup','vendor'):
        run('copy-'+name,['rsync','-a','--exclude=env.php','--exclude=auth.json','--exclude=.env',
                         str(SOURCE/name),str(ROOT/'src')+'/'])
    for name in ('composer.json','composer.lock','nginx.conf.sample','.htaccess'):
        shutil.copyfile(SOURCE/name,ROOT/'src'/name)
    (ROOT/'src/pub').mkdir()
    for name in ('index.php','get.php','static.php','errors','.htaccess','health_check.php','opt'):
        path=SOURCE/'pub'/name
        if path.is_dir(): shutil.copytree(path,ROOT/'src/pub'/name)
        elif path.is_file(): shutil.copyfile(path,ROOT/'src/pub'/name)
    for name in ('var','generated','pub/static','pub/media'):
        (ROOT/'src'/name).mkdir(exist_ok=True)
    shutil.copyfile(SOURCE/'pub/static/.htaccess',ROOT/'src/pub/static/.htaccess')
    shutil.copyfile(SOURCE/'pub/media/.htaccess',ROOT/'src/pub/media/.htaccess')
    run('verify-medium',[sys.executable,str(ROOT/'packages/release.py'),str(ROOT/'packages/medium'),
        '--manifest-sha256',PINS['medium'],'--extract',str(ROOT/'packages/medium-staged')])
    shutil.copytree(ROOT/'packages/medium-staged/module',ROOT/'src/app/code/RocketWeb/LabCatalog',dirs_exist_ok=True)
    run('permissions',['chown','-R','33:33',str(ROOT/'src')])
    run('dependencies',COMPOSE+['up','-d','db','search','php'])
    for attempt in range(90):
        db=subprocess.run(DB,input=b'SELECT 1;',capture_output=True)
        search=subprocess.run(COMPOSE+['exec','-T','php','curl','-fsS','http://search:9200/_cluster/health'],capture_output=True)
        if db.returncode==0 and search.returncode==0: break
        time.sleep(2)
    else: raise RuntimeError('Dependencies did not start')
    run('install-empty',CLI+['/packages/enriched_install.php'],input=json.dumps(credentials).encode())
    run('protect-env',['chmod','600',str(ROOT/'src/app/etc/env.php')])
    backup('lab_empty','empty.sql')
    (ROOT/'bootstrap-complete').touch(exist_ok=False)


def import_profile(profile):
    if not (ROOT/'bootstrap-complete').exists() or (ROOT/f'{profile}-started').exists():
        raise RuntimeError('Bootstrap missing or profile already attempted')
    (ROOT/f'{profile}-started').touch(exist_ok=False)
    staged=ROOT/'packages'/f'{profile}-staged'
    if profile=='full':
        run('verify-full',[sys.executable,str(ROOT/'packages/release.py'),str(ROOT/'packages/full'),
            '--manifest-sha256',PINS['full'],'--extract',str(staged)])
    database='lab_enriched_'+profile
    run('create-'+profile,DB,input=f"CREATE DATABASE {database}; GRANT ALL ON {database}.* TO 'lab_catalog'@'%';".encode())
    with (ROOT/'receipts/empty.sql').open('rb') as source:
        run('restore-empty-'+profile,DB+[database],input=source.read())
    switch="""$f='app/etc/env.php';$e=require $f;
if($e['db']['connection']['default']['host']!=='db'||!in_array($e['db']['connection']['default']['dbname'],['lab_empty','lab_enriched_medium'])){exit(2);}
$e['db']['connection']['default']['dbname']=$argv[1];
file_put_contents($f,'<?php return '.var_export($e,true).';');"""
    run('switch-'+profile,CLI+['-r',switch,database])
    run('cache-'+profile,CLI+['bin/magento','cache:flush'])
    run('preflight-'+profile,CLI+['/packages/preflight.php','--magento-root=/var/www/html',
        '--data-dir=/packages/'+profile+'-staged/data','--log-file=/var/www/html/var/log/'+profile+'-preflight.log'])
    shutil.copytree(staged/'data',ROOT/'src/var'/('wands-'+profile)/'data')
    shutil.copytree(staged/'media/wands-lab',ROOT/'src/pub/media/import/wands-lab',dirs_exist_ok=True)
    run('permissions-'+profile,['chown','-R','33:33',str(ROOT/'src')])
    run('provision-'+profile,CLI+['bin/magento','lab:wands:provision','--base-url=http://127.0.0.1:18036/',
                               '--theme=frontend/Hyva/default'])
    for name in ('1-simple','2-configurable','3-bundle','4-media'):
        run(profile+'-'+name,CLI+['bin/magento','lab:wands:import','--file=var/wands-'+profile+'/data/'+name+'.csv'])
    merchandising(profile)
    run('navigation-'+profile,CLI+['bin/magento','lab:wands:curate-navigation'])
    run('reindex-'+profile,CLI+['bin/magento','indexer:reindex'])
    run('static-'+profile,CLI+['bin/magento','setup:static-content:deploy','-f','--jobs=2','--theme','Hyva/default','en_US'])
    run('cache-final-'+profile,CLI+['bin/magento','cache:clean'])
    run('web-'+profile,COMPOSE+['up','-d','web'])
    run('verify-installed-'+profile,CLI+['/packages/verify_profile.php','/packages/'+profile+'-staged/data',
                                       '/var/www/html/var/'+profile+'-verification.json'])
    backup(database,profile+'-baseline.sql')
    (ROOT/f'{profile}-complete').touch(exist_ok=False)


def retry_empty_install():
    state=json.loads((ROOT/'state.json').read_text())
    if state != {'stage':'install-empty','status':'failed','exit_code':1}:
        raise RuntimeError('Not the inspected installer validation failure')
    result=subprocess.run(DB+['-N'],input=b"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='lab_empty';",capture_output=True)
    if result.returncode or result.stdout.strip()!=b'0':
        raise RuntimeError('Retry refused: new database is not empty')
    credentials=dict(line.split('=',1) for line in (ROOT/'.env').read_text().splitlines())
    run('install-empty',CLI+['/packages/enriched_install.php'],input=json.dumps(credentials).encode())
    run('protect-env',['chmod','600',str(ROOT/'src/app/etc/env.php')])
    backup('lab_empty','empty.sql')
    (ROOT/'bootstrap-complete').touch(exist_ok=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['bootstrap','retry-empty-install','medium','full'])
    args=parser.parse_args()
    if Path.cwd().resolve()!=ROOT or ROOT.is_symlink(): raise RuntimeError('Wrong target root')
    if args.action=='bootstrap': bootstrap()
    elif args.action=='retry-empty-install': retry_empty_install()
    else: import_profile(args.action)


if __name__=='__main__': main()
