"""Create the explicitly approved, remote-only, disposable Mage-OS 3.5 lab."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path('/opt/comtom/wands-lab35-acceptance')


def main():
    if Path.cwd().resolve() != ROOT or ROOT.is_symlink():
        raise RuntimeError('Wrong acceptance root')
    log = ROOT / 'bootstrap.log'
    with log.open('a') as output:
        def run(command, **kwargs):
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, **kwargs)
            if result.returncode:
                raise RuntimeError('Lab command failed; inspect bootstrap.log. Exit code: ' + str(result.returncode))
            return result

        state = ROOT / 'bootstrap-state.json'
        if state.exists():
            raise RuntimeError('Bootstrap already started; inspect state before resuming')
        state.write_text(json.dumps({'stage': 'created', 'existing_target_products': 0}))
        for name in ['src', 'packages', 'db', 'search', 'receipts']:
            (ROOT / name).mkdir(exist_ok=True)
        os.chown(ROOT / 'search', 1000, 1000)
        env = ROOT / '.env'
        if env.exists():
            raise RuntimeError('Do not overwrite existing lab credentials')
        values = {key: 'Lab35-' + secrets.token_urlsafe(28) for key in ['LAB_DB_ROOT_PASSWORD', 'LAB_DB_PASSWORD', 'LAB_ADMIN_PASSWORD']}
        fd = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(''.join(key + '=' + value + '\n' for key, value in values.items()))
        compose = ['docker', 'compose', '-f', str(ROOT / 'compose.yaml')]
        run(compose + ['up', '-d', 'db', 'search', 'php'])
        state.write_text(json.dumps({'stage': 'dependencies-started'}))
        run(compose + ['exec', '-T', 'php', 'composer', 'create-project', '--repository-url=https://repo.mage-os.org/',
                       'mage-os/project-community-edition', '/var/www/html', '3.5.0', '--no-interaction', '--no-dev'])
        state.write_text(json.dumps({'stage': 'composer-complete'}))
        for attempt in range(60):
            result = subprocess.run(compose + ['exec', '-T', 'php', 'curl', '-fsS', 'http://search:9200/_cluster/health'], capture_output=True)
            if result.returncode == 0:
                break
            time.sleep(2)
        else:
            raise RuntimeError('Private search did not start')
        run(compose + ['exec', '-T', 'php', 'php', '-d', 'memory_limit=3G', 'bin/magento', 'setup:install',
                       '--base-url=http://127.0.0.1:18035/', '--db-host=db', '--db-name=lab_starter',
                       '--db-user=lab_catalog', '--db-password=' + values['LAB_DB_PASSWORD'],
                       '--admin-firstname=Lab', '--admin-lastname=Operator', '--admin-email=lab@example.test',
                       '--admin-user=labadmin', '--admin-password=' + values['LAB_ADMIN_PASSWORD'],
                       '--language=en_US', '--currency=USD', '--timezone=America/Indiana/Indianapolis',
                       '--use-rewrites=1', '--search-engine=opensearch', '--opensearch-host=search',
                       '--opensearch-port=9200', '--opensearch-index-prefix=wands_lab35', '--backend-frontname=labadmin'])
        run(compose + ['exec', '-T', 'php', 'chown', '-R', 'www-data:www-data', '/var/www/html'])
        run(compose + ['up', '-d', 'web'])
        state.write_text(json.dumps({'stage': 'empty-mageos-installed', 'version': '3.5.0', 'profile': 'none'}))


if __name__ == '__main__':
    main()
