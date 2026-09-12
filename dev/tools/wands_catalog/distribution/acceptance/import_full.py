"""Test the full profile in a second private database, preserving starter results."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/opt/comtom/wands-lab35-acceptance')
PIN = '9bf76000f3de8816459638ba2f396af805eaaa83c504886000e1b3c32adcf19d'


def main():
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError('Wrong target root')
    if json.loads((ROOT / 'starter-state.json').read_text())['stage'] != 'starter-imported':
        raise RuntimeError('Starter import must finish first')
    state = ROOT / 'full-state.json'
    if state.exists():
        raise RuntimeError('Full import already attempted; inspect receipts before resuming')
    compose = ['docker', 'compose', '-f', str(ROOT / 'compose.yaml')]
    def run(stage, command, stdin=None, input=None):
        state.write_text(json.dumps({'stage': stage, 'status': 'running'}))
        with (ROOT / 'receipts' / ('full-' + stage + '.log')).open('a') as log:
            result = subprocess.run(command, stdin=stdin, input=input, stdout=log, stderr=log)
        if result.returncode:
            state.write_text(json.dumps({'stage': stage, 'status': 'failed', 'exit_code': result.returncode}))
            raise RuntimeError('Full stage failed: ' + stage)
        state.write_text(json.dumps({'stage': stage, 'status': 'complete'}))
    package = ROOT / 'packages/full'
    manifest = (package / 'manifest.json').read_bytes()
    if hashlib.sha256(manifest).hexdigest() != PIN:
        raise RuntimeError('Manifest mismatch')
    source_sha = json.loads(manifest)['source_files']['dev/tools/wands_catalog/distribution/release.py']
    if hashlib.sha256((package / 'release.py').read_bytes()).hexdigest() != source_sha:
        raise RuntimeError('Verifier mismatch')
    run('verify', [sys.executable, str(package / 'release.py'), str(package), '--manifest-sha256', PIN,
                   '--extract', str(ROOT / 'packages/full-staged')])
    credentials = dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines())
    sql = compose + ['exec', '-T', '-e', 'MYSQL_PWD=' + credentials['LAB_DB_ROOT_PASSWORD'], 'db', 'mariadb', '-uroot']
    run('create-database', sql, input=b"CREATE DATABASE lab_full; GRANT ALL ON lab_full.* TO 'lab_catalog'@'%';")
    with (ROOT / 'receipts/empty-before-module.sql').open('rb') as source:
        run('restore-empty-baseline', sql + ['lab_full'], stdin=source)
    old_env = ROOT / 'receipts/starter-env.php'
    fd = os.open(old_env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as output, (ROOT / 'src/app/etc/env.php').open('rb') as source:
        shutil.copyfileobj(source, output)
    cli = compose + ['exec', '-T', '--user', 'www-data', 'php', 'php', '-d', 'memory_limit=3G']
    switch = """$file='app/etc/env.php'; $env=require $file;
if ($env['db']['connection']['default']['dbname'] !== 'lab_starter' || $env['db']['connection']['default']['host'] !== 'db') { exit(2); }
$env['db']['connection']['default']['dbname']='lab_full';
file_put_contents($file, '<?php return '.var_export($env,true).';');"""
    run('switch-database', cli + ['-r', switch])
    run('cache-flush', cli + ['bin/magento', 'cache:flush'])
    stage = ROOT / 'packages/full-staged'
    run('preflight', cli + ['/packages/full-staged/tools/preflight.php', '--magento-root=/var/www/html',
                          '--data-dir=/packages/full-staged/data', '--log-file=/var/www/html/var/log/full-preflight.log'])
    shutil.copytree(stage / 'data', ROOT / 'src/var/wands-full/data')
    shutil.copytree(stage / 'media/wands-lab', ROOT / 'src/pub/media/import/wands-lab', dirs_exist_ok=True)
    run('prepare-permissions', compose + ['exec', '-T', 'php', 'chown', '-R', 'www-data:www-data', '/var/www/html'])
    run('module-setup', cli + ['bin/magento', 'setup:upgrade'])
    run('provision', cli + ['bin/magento', 'lab:wands:provision', '--base-url=http://127.0.0.1:18035/', '--theme=frontend/Magento/luma'])
    for name in ['1-simple', '2-configurable', '3-bundle', '4-media']:
        run(name, cli + ['bin/magento', 'lab:wands:import', '--file=var/wands-full/data/' + name + '.csv'])
    run('navigation', cli + ['bin/magento', 'lab:wands:curate-navigation'])
    run('reindex', cli + ['bin/magento', 'indexer:reindex'])
    run('permissions', compose + ['exec', '-T', 'php', 'chown', '-R', 'www-data:www-data', '/var/www/html'])
    run('cache-clean', cli + ['bin/magento', 'cache:clean'])
    run('restart-php', compose + ['restart', 'php'])
    state.write_text(json.dumps({'stage': 'full-imported', 'status': 'complete', 'manifest_sha256': PIN}))


if __name__ == '__main__':
    main()
