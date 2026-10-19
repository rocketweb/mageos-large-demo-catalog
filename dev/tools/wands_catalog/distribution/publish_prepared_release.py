"""Check a prepared local release; publish only with an explicit --publish flag."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def local_plan(root):
    if (root / 'PUBLICATION_BLOCKED.json').exists():
        raise ValueError('Publication blocked: rebuild the catalog with current exclusions before publishing')
    plan = json.loads((root / 'publication-plan.json').read_text())
    assets = root / 'assets'
    if set(p.name for p in assets.iterdir()) != set(plan['assets']):
        raise ValueError('Asset directory differs from the reviewed publication plan')
    for name, info in plan['assets'].items():
        if Path(name).name != name:
            raise ValueError('Unsafe asset name')
        path = assets / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != info['bytes'] or digest(path) != info['sha256']:
            raise ValueError('Prepared asset changed: ' + name)
    if digest(root / 'release-notes.md') != plan['release_notes_sha256']:
        raise ValueError('Release notes changed after preparation')
    return plan


def remote_assets(remote, plan, complete=False):
    files = {item['name']: item for item in remote['assets']}
    if not files.keys() <= plan['assets'].keys():
        raise ValueError('Existing release contains unexpected assets')
    for name, info in files.items():
        expected = plan['assets'][name]
        if info['size'] != expected['bytes'] or info.get('digest') != 'sha256:' + expected['sha256']:
            raise ValueError('GitHub asset differs from prepared bytes: ' + name)
    if complete and files.keys() != plan['assets'].keys():
        raise ValueError('GitHub release is missing assets')
    return sorted(plan['assets'].keys() - files.keys())


def gh(arguments):
    return subprocess.run(['gh', *arguments], check=True)


def inspect_remote(plan):
    result = subprocess.run(['gh', 'release', 'view', plan['tag'], '--repo', plan['repository'],
        '--json', 'tagName,isDraft,targetCommitish,assets,body,url'], capture_output=True, text=True)
    if result.returncode == 0:
        return json.loads(result.stdout)
    if 'release not found' in result.stderr.lower():
        return None
    raise RuntimeError('Could not inspect the target release; check GitHub authentication')


def publish(root, plan):
    remote = inspect_remote(plan)
    if remote:
        if not remote['isDraft']:
            raise ValueError('Target release is already public; refusing to change it')
        if remote['targetCommitish'] != plan['source_target_commit']:
            raise ValueError('Existing draft points to a different source commit')
        if remote['body'].replace('\r\n', '\n').strip() != (root / 'release-notes.md').read_text().strip():
            raise ValueError('Existing draft release notes differ from the prepared notes')
        missing = remote_assets(remote, plan)
    else:
        gh(['release', 'create', plan['tag'], '--repo', plan['repository'], '--target', plan['source_target_commit'],
            '--draft', '--title', plan['title'], '--notes-file', str(root / 'release-notes.md')])
        missing = sorted(plan['assets'])
    if missing:
        gh(['release', 'upload', plan['tag'], '--repo', plan['repository'],
            *[str(root / 'assets' / name) for name in missing]])
    # Remain a draft unless every GitHub size and digest matches the local plan.
    remote_assets(inspect_remote(plan), plan, complete=True)
    gh(['release', 'edit', plan['tag'], '--repo', plan['repository'], '--draft=false', '--latest'])
    final = inspect_remote(plan)
    remote_assets(final, plan, complete=True)
    if final['isDraft']:
        raise ValueError('Release remains a draft')
    receipt = {'published': True, 'url': final['url'], 'tag': plan['tag'],
               'all_asset_sizes_and_sha256_verified': True, 'assets': len(plan['assets'])}
    (root / 'publication-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true', help='Create/upload a draft, verify it, then publish as Latest')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.root.resolve();plan = local_plan(root)
    if args.publish:
        publish(root, plan)
    else:
        print(json.dumps({'local_assets_verified': True, 'tag': plan['tag'], 'assets': len(plan['assets']),
                          'published': False, 'publication_requires': '--publish'}, indent=2))


if __name__ == '__main__':
    main()
