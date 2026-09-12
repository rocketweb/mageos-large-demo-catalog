"""Prepare flat GitHub release assets from the unchanged, accepted rc2 profiles."""
import argparse
import json
import logging
from pathlib import Path
import shutil

from build_handoff import DOCS, PROFILE_PINS, encoded
from release import digest, verify_release, write_archive

HERE = Path(__file__).resolve().parent
REPOSITORY = 'rocketweb/mageos-large-demo-catalog'
TAG = 'catalog-2026.09.12-rc2'
HOSTING_COMMIT = 'd1cd3749074761f00b62d8584f443046eba3e619'
SCRIPTS = ['release.py', 'download.py', 'github_download.py']


def release_notes(toolkit_pin, scripts):
    hashes = '\n'.join(digest(HERE / name) + '  ' + name for name in scripts)
    return f'''# WANDS catalog for Mage-OS Lab: rc2

27-product starter and 53,844-product full catalog, tested on fresh Mage-OS 3.5.0
with Luma and OpenSearch 3.1.0. The full profile includes 1,995 configurable parents,
50 bundles and 46,602 distinct synthetic images. All 616,053 full-profile data/media
checks passed in the recorded installation test.

This repository is private. Recipients need repository access. No repository
visibility change is part of this release. This is lab test data, not an official
Mage-OS or Wayfair release, and not intended for customer stores.

## Start here

Download the attached `github_download.py`, `download.py` and `release.py` into a
new directory. Authenticate their SHA-256 values before executing them:

```text
{hashes}
```

Run `shasum -a 256 github_download.py download.py release.py` and compare with
the values above. Use an existing `gh auth login` session for private access.
Alternatively, supply `GH_TOKEN` or `GITHUB_TOKEN` through a credential manager.
Never put a token in a command argument, URL or log.

Download the small current toolkit, then extract it:

```sh
python3 github_download.py --repo {REPOSITORY} \\
  --tag {TAG} --profile toolkit --cache-dir ./cache \\
  --manifest-sha256 {toolkit_pin}
python3 release.py ./cache/{toolkit_pin} \\
  --manifest-sha256 {toolkit_pin} --extract ./toolkit
```

Choose the starter first, or substitute `--profile full` and the full pin below:

```sh
python3 github_download.py --repo {REPOSITORY} \\
  --tag {TAG} --profile starter --cache-dir ./cache \\
  --manifest-sha256 {PROFILE_PINS['starter']}
python3 release.py ./cache/{PROFILE_PINS['starter']} \\
  --manifest-sha256 {PROFILE_PINS['starter']} --extract ./wands-staging
```

```text
starter {PROFILE_PINS['starter']}
full    {PROFILE_PINS['full']}
toolkit {toolkit_pin}
```

The terminal stays quiet. Use `tail -f wands-download.log` for progress. Rerun the
same download command after interruption. Checksums and archive-member verification
must pass before extraction; extraction always requires a new directory.

Use `toolkit/tools/preflight.php` with `--data-dir=./wands-staging/data` and an
explicit `--magento-root` for the empty destination. Then follow the current
`toolkit/docs/README.md` installation guide. In that guide, the current preflight
is at `toolkit/tools/preflight.php`; do not use the older preflight nested in rc2.
Run PHP in the recipient's Mage-OS environment as its web filesystem owner.
Retain an empty-baseline backup before installation writes. Starter and full must
not be installed over each other. No automatic import resume or live-store updater
is included. Mage-OS 3.4, clean-install Hyvä and checkout/payment are not qualified.

## Packaging and provenance

The `starter-` and `full-` prefixes only distinguish asset filenames. The downloader
restores original filenames locally, preserving the exact rc2 manifest pins and
archive bytes used in the Mage-OS acceptance run. Individual assets fit GitHub's
2 GiB limit. Images are release attachments, not Git objects or Git LFS files.

`SHA256SUMS` and `release-inventory.json` list asset hashes. Checksums beside the
files do not independently establish authenticity; retain trusted pins separately.
The toolkit includes current source, notices, installation docs and acceptance
details. Original WANDS data retains its MIT notice and requested paper citation;
authored code/data uses MIT and generated media uses CC0 where rights are held.
Per-image provenance limitations and inherited family illustrations are disclosed.

This is an asset-only prerelease. Its tag anchors the hosting repository's existing
main commit `{HOSTING_COMMIT}`. The automatically generated GitHub source ZIP is
not the catalog installer or the current toolkit. Use the attached assets. No
unpublished source branch history or deployment is included in this operation.
'''.encode()


def build_assets(profile_dirs, output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError('Asset output must be a new directory')
    if set(profile_dirs) != set(PROFILE_PINS):
        raise ValueError('Both accepted profiles are required')
    sources = {}
    for profile, pin in sorted(PROFILE_PINS.items()):
        root = Path(profile_dirs[profile])
        verify_release(root, pin)
        manifest = json.loads((root / 'manifest.json').read_bytes())
        if manifest.get('profile') != profile or manifest.get('release') != '2026.09.11-rc2':
            raise ValueError('Unexpected profile identity')
        sources[profile + '-manifest.json'] = root / 'manifest.json'
        for artifact in manifest['artifacts']:
            if Path(artifact['path']).name != artifact['path'] or artifact['bytes'] >= 2 ** 31:
                raise ValueError('Asset path or size incompatible with GitHub')
            sources[profile + '-' + artifact['path']] = root / artifact['path']
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < sum(path.stat().st_size for path in sources.values()) + 64 * 1024 ** 2:
        raise ValueError('Insufficient space for release assets')
    output.mkdir()
    for name, source in sources.items():
        shutil.copyfile(source, output / name)
        if digest(output / name) != digest(source):
            raise ValueError('Asset changed during copy')
    toolkit_files = {'tools/' + name: HERE / name for name in SCRIPTS + ['preflight.php']}
    for name in DOCS + ['GITHUB_RELEASE.md']:
        data = (HERE / name).read_bytes()
        data = data.replace(b'dev/tools/wands_catalog/distribution/', b'tools/')
        data = data.replace(b'php ./wands-staging/tools/preflight.php', b'php tools/preflight.php')
        toolkit_files['docs/' + name] = data
    toolkit_files['docs/ROCKET-WEB-LICENSE.txt'] = HERE.parent / 'LICENSE.txt'
    artifact = write_archive(output / 'toolkit-tools.tar', toolkit_files)
    artifact['path'] = 'tools.tar'
    toolkit_manifest = {'schema': 1, 'release': TAG, 'profile': 'toolkit', 'artifacts': [artifact]}
    (output / 'toolkit-manifest.json').write_bytes(encoded(toolkit_manifest))
    toolkit_pin = digest(output / 'toolkit-manifest.json')
    for name in SCRIPTS:
        shutil.copyfile(HERE / name, output / name)
    (output / 'README.md').write_bytes(release_notes(toolkit_pin, SCRIPTS))
    assets = {p.name: {'bytes': p.stat().st_size, 'sha256': digest(p)} for p in sorted(output.iterdir())}
    if any(row['bytes'] >= 2 ** 31 for row in assets.values()):
        raise ValueError('GitHub asset limit exceeded')
    inventory = {'repository': REPOSITORY, 'tag': TAG, 'hosting_commit': HOSTING_COMMIT,
                 'profile_pins': PROFILE_PINS, 'toolkit_pin': toolkit_pin, 'assets': assets}
    (output / 'release-inventory.json').write_bytes(encoded(inventory))
    (output / 'SHA256SUMS').write_text(''.join(digest(p) + '  ' + p.name + '\n' for p in sorted(output.iterdir())))
    logging.info('COMPLETE %s', json.dumps({'asset_count': len(assets) + 2,
                 'toolkit_pin': toolkit_pin, 'profile_pins': PROFILE_PINS}, sort_keys=True))
    return inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--starter', type=Path, required=True)
    parser.add_argument('--full', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output.with_suffix('.log'), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        build_assets({'starter': args.starter, 'full': args.full}, args.output)
    except Exception:
        logging.exception('GitHub asset preparation failed')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
