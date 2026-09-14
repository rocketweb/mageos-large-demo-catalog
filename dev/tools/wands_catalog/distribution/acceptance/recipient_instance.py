"""One-use, remote-only public-download acceptance. Not a recipient installer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

ROOT = Path('/opt/comtom/wands-lab35-recipient-v2')
SOURCE = Path('/opt/comtom/wands-lab35-acceptance/src')
TAG = 'catalog-2026.09.13-enriched-v2'
PINS = {'medium': '93256f50f6a1e5070eab18dee3e28b2b348b5e92aba0fa35e3a5b22cb4aaa07a',
        'toolkit': '93c3e983328ca2aa97050b4f9b5022eb4fa8d50681a725b167d724c56f156e9f'}
HELPERS = {'github_download.py': '40d0f3ad8fd6bc3f61ffe2ba2d25e880e6e6f7cdf899083fc5f4ef3cadb36aff',
           'download.py': '1af4c6d081383d0b3401e7ad0630eea69888f6fd8179c73f29ccea3925f63e08',
           'release.py': '9d0d17e2ef4e201e93ef717fee65017f5c83e151df7b73c3d5c1de057460b14b'}
COMPOSE = ['docker', 'compose', '-f', str(ROOT/'compose.yaml')]
CLI = COMPOSE + ['exec', '-T', '--user', 'www-data', 'php', 'php', '-d', 'memory_limit=3G']


def run(stage, command, *, input=None, output=None):
    state = ROOT/'state.json'
    state.write_text(json.dumps({'stage': stage, 'status': 'running'}))
    with (ROOT/'receipts'/f'{stage}.log').open('ab') as log:
        result = subprocess.run(command, input=input, stdout=output or log, stderr=log)
    state.write_text(json.dumps({'stage': stage, 'status': 'complete' if result.returncode == 0 else 'failed',
                                'exit_code': result.returncode}))
    if result.returncode:
        raise RuntimeError('Stage failed: '+stage)


def backup(name):
    command = COMPOSE + ['exec', '-T', 'db', 'sh', '-c',
        'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb-dump -uroot --single-transaction --routines --triggers lab_recipient']
    with os.fdopen(os.open(ROOT/'receipts'/name, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as output:
        run('backup-'+name, command, output=output)


def prepare():
    (ROOT/'prepare-started').touch(exist_ok=False)
    for name in ('src', 'db', 'search', 'receipts'):
        (ROOT/name).mkdir()
    os.chown(ROOT/'search', 1000, 1000)
    credentials = {key: 'Lab35-'+secrets.token_urlsafe(28) for key in
                   ('LAB_DB_ROOT_PASSWORD', 'LAB_DB_PASSWORD', 'LAB_ADMIN_PASSWORD')}
    with os.fdopen(os.open(ROOT/'.env', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'w') as output:
        output.write(''.join(k+'='+v+'\n' for k, v in credentials.items()))
    assert hashlib.sha256((SOURCE/'composer.lock').read_bytes()).hexdigest() == '8674885f1a076ed4f875d729cd7cf45ad54c474240a73bc15f208d6b9f8e4e7d'
    for name in ('app', 'bin', 'lib', 'setup', 'vendor'):
        run('copy-'+name, ['rsync', '-a', '--exclude=env.php', '--exclude=auth.json', '--exclude=.env',
            '--exclude=LabCatalog', str(SOURCE/name), str(ROOT/'src')+'/'])
    assert not (ROOT/'src/app/code/RocketWeb/LabCatalog').exists()
    for name in ('composer.json', 'composer.lock', 'nginx.conf.sample', '.htaccess'):
        shutil.copyfile(SOURCE/name, ROOT/'src'/name)
    (ROOT/'src/pub').mkdir()
    for name in ('index.php', 'get.php', 'static.php', 'errors', '.htaccess', 'health_check.php', 'opt'):
        path = SOURCE/'pub'/name
        if path.is_dir():
            shutil.copytree(path, ROOT/'src/pub'/name)
        elif path.is_file():
            shutil.copyfile(path, ROOT/'src/pub'/name)
    for name in ('var', 'generated', 'pub/static', 'pub/media'):
        (ROOT/'src'/name).mkdir(exist_ok=True)
    for name in ('static', 'media'):
        shutil.copyfile(SOURCE/'pub'/name/'.htaccess', ROOT/'src/pub'/name/'.htaccess')
    run('permissions', ['chown', '-R', '33:33', str(ROOT/'src')])
    run('dependencies', COMPOSE+['up', '-d', 'db', 'search', 'php'])
    for attempt in range(90):
        db = subprocess.run(COMPOSE+['exec', '-T', 'db', 'sh', '-c',
            'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb -uroot -e "SELECT 1"'], capture_output=True)
        search = subprocess.run(COMPOSE+['exec', '-T', 'php', 'curl', '-fsS',
                                        'http://search:9200/_cluster/health'], capture_output=True)
        if db.returncode == 0 and search.returncode == 0:
            break
        time.sleep(2)
    else:
        raise RuntimeError('Dependencies did not start')
    # Only the new copied config is edited. Source fixtures are never mutated.
    run('exclude-catalog-module', CLI+['-r', "$f='app/etc/config.php';$c=require $f;unset($c['modules']['RocketWeb_LabCatalog']);file_put_contents($f,'<?php return '.var_export($c,true).';');"])
    run('install-empty', CLI+['/packages/recipient_install.php'], input=json.dumps(credentials).encode())
    run('protect-env', ['chmod', '600', str(ROOT/'src/app/etc/env.php')])
    backup('empty-before-module.sql')
    (ROOT/'prepare-complete').touch(exist_ok=False)


def install():
    if not (ROOT/'prepare-complete').exists():
        raise RuntimeError('Empty installation not complete')
    (ROOT/'install-started').touch(exist_ok=False)
    packages = ROOT/'packages'
    for name, pin in HELPERS.items():
        run('download-'+name, ['curl', '-fLsS', '--proto', '=https', '--proto-redir', '=https',
            f'https://github.com/rocketweb/mageos-large-demo-catalog/releases/download/{TAG}/{name}',
            '-o', str(packages/name)])
        if hashlib.sha256((packages/name).read_bytes()).hexdigest() != pin:
            raise RuntimeError('Public helper checksum mismatch: '+name)
    for profile, pin in PINS.items():
        run('download-'+profile, [sys.executable, str(packages/'github_download.py'), '--anonymous',
            '--repo', 'rocketweb/mageos-large-demo-catalog', '--tag', TAG, '--profile', profile,
            '--cache-dir', str(packages/profile), '--manifest-sha256', pin,
            '--log-file', str(ROOT/'receipts/public-download.log')])
        run('extract-'+profile, [sys.executable, str(packages/'release.py'), str(packages/profile/pin),
            '--manifest-sha256', pin, '--extract', str(packages/(profile+'-staged'))])
    staged = packages/'medium-staged'
    run('preflight', CLI+['/packages/toolkit-staged/tools/preflight.php', '--magento-root=/var/www/html',
        '--data-dir=/packages/medium-staged/data', '--log-file=/var/www/html/var/preflight.log'])
    shutil.copytree(staged/'module', ROOT/'src/app/code/RocketWeb/LabCatalog')
    run('module-permissions', ['chown', '-R', '33:33', str(ROOT/'src/app/code/RocketWeb/LabCatalog')])
    run('enable-module', CLI+['bin/magento', 'module:enable', 'RocketWeb_LabCatalog'])
    run('setup-upgrade', CLI+['bin/magento', 'setup:upgrade'])
    run('provision', CLI+['bin/magento', 'lab:wands:provision', '--base-url=http://127.0.0.1:18037/',
                        '--theme=frontend/Hyva/default'])
    shutil.copytree(staged/'data', ROOT/'src/var/wands-lab/data')
    shutil.copytree(staged/'media/wands-lab', ROOT/'src/pub/media/import/wands-lab')
    run('data-permissions', ['chown', '-R', '33:33', str(ROOT/'src/var/wands-lab'),
                            str(ROOT/'src/pub/media/import/wands-lab')])
    for name in ('1-simple', '2-configurable', '3-bundle', '4-media', '5-merchandising'):
        run(name, CLI+['bin/magento', 'lab:wands:import', '--file=var/wands-lab/data/'+name+'.csv'])
    run('navigation', CLI+['bin/magento', 'lab:wands:curate-navigation'])
    run('reindex', CLI+['bin/magento', 'indexer:reindex'])
    run('static', CLI+['bin/magento', 'setup:static-content:deploy', '-f', '--jobs=2', '--theme', 'Hyva/default', 'en_US'])
    run('cache', CLI+['bin/magento', 'cache:clean'])
    run('web', COMPOSE+['up', '-d', 'web'])
    run('verify', CLI+['/packages/verify_profile.php', '/packages/medium-staged/data',
                     '/var/www/html/var/recipient-verification.json'])
    backup('medium-after-verification.sql')
    (ROOT/'install-complete').touch(exist_ok=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'install'])
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.is_symlink():
        raise RuntimeError('Wrong target root')
    {'prepare': prepare, 'install': install}[args.action]()


if __name__ == '__main__':
    main()
