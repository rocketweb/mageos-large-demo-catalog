"""Verify and import the starter into the newly created, isolated acceptance lab."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/opt/comtom/wands-lab35-acceptance')
PIN = '42bd8400415204b8bc6b8f5ed5cf8adb8156185eca92ff156cd54285bb68b40f'


def main():
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError('Wrong target root')
    state = ROOT / 'starter-state.json'
    if state.exists():
        raise RuntimeError('Starter already attempted; inspect state before resuming')
    compose = ['docker', 'compose', '-f', str(ROOT / 'compose.yaml')]
    def run(stage, command, stdout=None):
        state.write_text(json.dumps({'stage': stage, 'status': 'running'}))
        with (ROOT / 'receipts' / ('starter-' + stage + '.log')).open('a') as log:
            result = subprocess.run(command, stdout=stdout or log, stderr=log)
        if result.returncode:
            state.write_text(json.dumps({'stage': stage, 'status': 'failed', 'exit_code': result.returncode}))
            raise RuntimeError('Stage failed: ' + stage)
        state.write_text(json.dumps({'stage': stage, 'status': 'complete'}))
    package = ROOT / 'packages/starter'
    manifest = (package / 'manifest.json').read_bytes()
    if hashlib.sha256(manifest).hexdigest() != PIN:
        raise RuntimeError('Manifest mismatch')
    source_sha = json.loads(manifest)['source_files']['dev/tools/wands_catalog/distribution/release.py']
    if hashlib.sha256((package / 'release.py').read_bytes()).hexdigest() != source_sha:
        raise RuntimeError('Verifier source mismatch')
    run('verify', [sys.executable, str(package / 'release.py'), str(package), '--manifest-sha256', PIN,
                   '--extract', str(ROOT / 'packages/starter-staged')])
    cli = compose + ['exec', '-T', '--user', 'www-data', 'php', 'php', '-d', 'memory_limit=3G']
    run('preflight', cli + ['/packages/starter-staged/tools/preflight.php', '--magento-root=/var/www/html',
                          '--data-dir=/packages/starter-staged/data', '--log-file=/var/www/html/var/log/starter-preflight.log'])
    credentials = dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines())
    backup = ROOT / 'receipts/empty-before-module.sql'
    with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as output:
        run('empty-backup', compose + ['exec', '-T', '-e', 'MYSQL_PWD=' + credentials['LAB_DB_ROOT_PASSWORD'],
                  'db', 'mariadb-dump', '-uroot', '--single-transaction', '--routines', '--triggers', 'lab_starter'], stdout=output)
    if backup.stat().st_size < 10000:
        raise RuntimeError('Empty baseline backup unexpectedly small')
    stage = ROOT / 'packages/starter-staged'
    shutil.copytree(stage / 'module', ROOT / 'src/app/code/RocketWeb/LabCatalog')
    shutil.copytree(stage / 'data', ROOT / 'src/var/wands-lab/data')
    shutil.copytree(stage / 'media/wands-lab', ROOT / 'src/pub/media/import/wands-lab')
    run('prepare-permissions', compose + ['exec', '-T', 'php', 'chown', '-R', 'www-data:www-data', '/var/www/html'])
    run('module-enable', cli + ['bin/magento', 'module:enable', 'RocketWeb_LabCatalog'])
    run('module-setup', cli + ['bin/magento', 'setup:upgrade'])
    run('provision', cli + ['bin/magento', 'lab:wands:provision', '--base-url=http://127.0.0.1:18035/', '--theme=frontend/Magento/luma'])
    for name in ['1-simple', '2-configurable', '3-bundle', '4-media']:
        run(name, cli + ['bin/magento', 'lab:wands:import', '--file=var/wands-lab/data/' + name + '.csv'])
    run('navigation', cli + ['bin/magento', 'lab:wands:curate-navigation'])
    run('reindex', cli + ['bin/magento', 'indexer:reindex'])
    run('static', cli + ['bin/magento', 'setup:static-content:deploy', '-f', '--jobs=2', 'en_US'])
    run('permissions', compose + ['exec', '-T', 'php', 'chown', '-R', 'www-data:www-data', '/var/www/html'])
    run('cache-clean', cli + ['bin/magento', 'cache:clean'])
    run('web', compose + ['up', '-d', 'web'])
    state.write_text(json.dumps({'stage': 'starter-imported', 'status': 'complete', 'manifest_sha256': PIN}))


if __name__ == '__main__':
    main()
