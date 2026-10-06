#!/usr/bin/env python3
"""Run verified expansion batches in one existing installation; no provisioning."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix=path.name + '.', delete=False) as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    os.replace(temporary, path)

TARGETS = {
    '/Users/matt/code/mageos-latest': ('/Users/matt/code/mageos-latest', ['/opt/homebrew/bin/php', '-d', 'memory_limit=3G']),
    '/opt/comtom/stores/relevance/src': ('/var/www/html', ['docker', 'exec', '--user', 'www-data', '-w', '/var/www/html',
                                                       'farm-relevance-php-1', 'php', '-d', 'memory_limit=3G']),
}
CANDIDATE_SHA256 = '921e5e1a0d8a386c93bf0f80dd6543c9d3561e5ad27e31df5b80b9d3e0d8502e'


def read_plan(root, plan_dir, pin):
    if str(root) not in TARGETS:
        raise ValueError('Only the existing local and Comtom installations are supported')
    if not plan_dir.is_relative_to(root):
        raise ValueError('Native import files must be staged inside the existing installation')
    path = plan_dir / 'deployment.json'
    if sha256(path) != pin:
        raise ValueError('Deployment plan changed')
    plan = json.loads(path.read_text())
    if plan['target_root'] != TARGETS[str(root)][0] or plan['website_code'] != 'wands':
        raise ValueError('Wrong destination plan')
    if plan.get('candidate_sha256') != CANDIDATE_SHA256:
        raise ValueError('Unapproved expansion candidate')
    baseline = 42994 if plan['target_root'] == '/Users/matt/code/mageos-latest' else 53844
    delta = plan['delta']
    reconciliation=plan.get('reconciliation')
    if reconciliation:
        if ((plan['target_root']!='/Users/matt/code/mageos-latest' and not plan.get('media_tail_reconciliation')) or reconciliation.get('schema')!=1
                or reconciliation.get('candidate_sha256')!=CANDIDATE_SHA256
                or reconciliation.get('original_before_wands_products')!=baseline
                or reconciliation.get('before_wands_products')!=baseline+len(set(reconciliation['already_imported_skus']))):
            raise ValueError('Invalid reconciled native scope')
        for path,pin in reconciliation['source_pins'].items():
            if sha256(Path(path))!=pin:raise ValueError('Reconciliation evidence changed')
        baseline=reconciliation['before_wands_products']
    if (delta.get('before_wands_products') != baseline or delta.get('after_wands_products') != 107688
            or delta.get('product_inserts') != 107688 - baseline or delta.get('products_deleted') != 0):
        raise ValueError('Unexpected catalog mutation scope')
    tail=plan.get('media_tail_reconciliation')
    if tail:
        if (not tail.get('database_acceptance',{}).get('passed') or tail['database_acceptance'].get('wands_products')!=107688
                or sum(a.get('rows',0) for a in plan['actions'])!=107455-tail['completed_media_rows']
                or any(a['action']!='native-import' or not Path(a['file']).name.endswith('-media.csv') for a in plan['actions'])):
            raise ValueError('Media tail may only apply exact remaining accepted assignments')
    for name, expected in plan['files'].items():
        path = (plan_dir / name).resolve()
        if not path.is_relative_to(plan_dir) or sha256(path) != expected:
            raise ValueError('Deployment file changed or escaped its directory: ' + name)
    return plan


def commands(root, plan_dir, plan):
    prefix = TARGETS[str(root)][1] + ['bin/magento']
    result = []
    for action in plan['actions']:
        path = (plan_dir / action['file']).resolve()
        if not path.is_relative_to(plan_dir) or action['file'] not in plan['files']:
            raise ValueError('Unverified action file')
        relative = str(path.relative_to(root))
        if action['action'] == 'native-import':
            if action.get('preserve_existing_stock') is not True or action.get('validate_before_apply') is not True:
                raise ValueError('Native import must preserve stock and validate before applying')
            if not 1 <= action['rows'] <= 2000:
                raise ValueError('Unbounded native import')
            base = prefix + ['lab:wands:import', '--file=' + relative, '--preserve-existing-stock']
            result.extend([{'kind': 'validate', 'argv': base + ['--validate-only']}, {'kind': 'import', 'argv': base}])
        elif action['action'] == 'convert-parents':
            if (str(root) != '/Users/matt/code/mageos-latest' or not action.get('dry_run_before_apply')
                    or not 1 <= action['limit'] <= 100 or action['offset'] < 0):
                raise ValueError('Unexpected parent conversion scope')
            base = prefix + ['lab:wands:convert-parents', '--file=' + relative,
                             '--offset=' + str(action['offset']), '--limit=' + str(action['limit'])]
            result.extend([{'kind': 'validate-conversion', 'argv': base + ['--dry-run']}, {'kind': 'convert', 'argv': base}])
        else:
            raise ValueError('Unknown deployment action')
    return result


def verify_backups(path, root, plan):
    receipt = json.loads(path.read_text())
    if receipt.get('target_root') != plan['target_root'] or receipt.get('before_snapshot_sha256') != plan['snapshot_sha256']:
        raise ValueError('Backup belongs to another target or before-state')
    captured = datetime.fromisoformat(receipt['created_at'])
    if captured.tzinfo is None:
        raise ValueError('Backup timestamp must include its timezone')
    age = datetime.now(timezone.utc).timestamp() - captured.timestamp()
    if not 0 <= age <= 3600:
        raise ValueError('Fresh backup and inverse evidence required')
    for kind in ('database', 'module', 'inverse'):
        item = receipt[kind]
        file = Path(item['path']).resolve()
        if file.is_relative_to(root / 'pub') or not file.is_file() or file.stat().st_size == 0:
            raise ValueError('Missing or publicly staged backup/inverse')
        if file.stat().st_mode & 0o077 or sha256(file) != item['sha256']:
            raise ValueError('Backup must be private and unchanged')
    return receipt


def execute(root, plan_dir, pin, output, before_snapshot, snapshot_tool, backups=None, apply=False):
    plan = read_plan(root, plan_dir, pin)
    actions = commands(root, plan_dir, plan)
    if output.exists():
        raise ValueError('Choose a fresh execution receipt directory; partial imports require explicit reconciliation')
    if sha256(before_snapshot) != plan['snapshot_sha256']:
        raise ValueError('Wrong before snapshot')
    if not apply:
        return {'state': 'prepared; no store commands run', 'target_root': plan['target_root'],
                'commands': len(actions), 'native_batches': len(plan['actions']), 'plan_sha256': pin}
    if backups is None:
        raise ValueError('Verified private backups and an exact inverse must exist before applying')
    verify_backups(backups, root, plan)
    if not snapshot_tool.resolve().is_relative_to(root):
        raise ValueError('Snapshot tool must be staged inside the installation')
    expected_tool = Path(__file__).with_name('expansion_store_snapshot.php')
    if sha256(snapshot_tool) != sha256(expected_tool):
        raise ValueError('Snapshot tool changed')
    output.mkdir(mode=0o700, parents=True)
    os.chmod(output, 0o700)
    target_root, php = TARGETS[str(root)]
    def snapshot(destination):
        runtime_path = target_root + '/' + str(snapshot_tool.relative_to(root))
        with destination.open('xb') as stream:
            os.chmod(destination, 0o600)
            process = subprocess.run(php + [runtime_path, '--root=' + target_root], cwd=root,
                                     stdout=stream, stderr=subprocess.PIPE)
        if process.returncode:
            raise RuntimeError('Read-only target snapshot failed; inspect the installation privately')
        return json.loads(destination.read_text())
    current = snapshot(output / 'immediate-before.json')
    if current != json.loads(before_snapshot.read_text()):
        raise ValueError('Destination changed since the reviewed plan; no import performed')
    state = output / 'state.json'
    atomic_json(state, {'state': 'preflight_passed', 'plan_sha256': pin, 'commands': len(actions), 'updated': time.time()})
    for index, action in enumerate(actions):
        atomic_json(state, {'state': 'running', 'index': index, 'kind': action['kind'], 'plan_sha256': pin, 'updated': time.time()})
        with (output / f'{index:04d}-{action["kind"]}.log').open('xb') as log:
            result = subprocess.run(action['argv'], cwd=root, stdout=log, stderr=log)
        validation_failed=False
        if not result.returncode and action['kind']=='validate':
            try:
                evidence=json.loads((output/f'{index:04d}-validate.log').read_text())
                validation_failed=(evidence.get('validated_only') is not True or evidence.get('errors')!=0 or evidence.get('invalid_rows')!=0)
            except (ValueError,TypeError):validation_failed=True
        if result.returncode or validation_failed:
            atomic_json(state, {'state': 'failed; reconcile partial state before retry', 'index': index,
                                'exit_code': result.returncode, 'plan_sha256': pin, 'updated': time.time()})
            raise RuntimeError('Native import stage failed; retained receipts identify the exact stage')
        atomic_json(output / f'{index:04d}-completed.json', {'action': action, 'exit_code': 0, 'plan_sha256': pin})
    snapshot(output / 'after-native-import.json')
    result = {'state': 'native_import_complete; gallery_navigation_reindex_and_live_verification_pending',
              'target_root': plan['target_root'], 'plan_sha256': pin, 'commands_completed': len(actions), 'updated': time.time()}
    atomic_json(state, result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'plan-dir', 'output', 'before-snapshot', 'snapshot-tool'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--plan-sha256', required=True)
    p.add_argument('--backups', type=Path)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    print(json.dumps(execute(a.root.resolve(), a.plan_dir.resolve(), a.plan_sha256, a.output.resolve(),
                             a.before_snapshot.resolve(), a.snapshot_tool.resolve(),
                             a.backups.resolve() if a.backups else None, a.apply), indent=2))
