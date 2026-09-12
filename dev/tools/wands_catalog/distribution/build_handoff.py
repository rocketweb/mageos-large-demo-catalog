"""Build an offline recipient handoff around the immutable, accepted rc2 profiles."""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import shutil

from release import digest, verify_release, write_archive

HERE = Path(__file__).resolve().parent
PROFILE_PINS = {
    'starter': '42bd8400415204b8bc6b8f5ed5cf8adb8156185eca92ff156cd54285bb68b40f',
    'full': '9bf76000f3de8816459638ba2f396af805eaaa83c504886000e1b3c32adcf19d',
}
DOCS = ['README.md', 'ACCEPTANCE.md', 'DOWNLOADS.md', 'DATA_CARD.md',
        'TERMS.md', 'WANDS-LICENSE.txt', 'CITATION.bib', 'CC0-1.0.txt']
TOOLS = ['release.py', 'download.py', 'preflight.php']


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def instructions(profiles):
    return f'''# WANDS catalog: start here

Private Mage-OS Lab handoff. This is test data, not an official Mage-OS or Wayfair
release. The enclosed catalog profiles are the unchanged `2026.09.11-rc2` bytes
tested on Mage-OS 3.5.0. The companion tools and instructions are newer.

Starter: {profiles['starter']['counts']['products']:,} products.
Full: {profiles['full']['counts']['products']:,} products.
Product images are included as separate nested media archives, never as Git files.
No GPU, API key, SSH access or original development checkout is needed.
Verification needs Python 3.11+. The optional downloader supports macOS and Linux.

## 1. Authenticate the package and verifier

Obtain the handoff manifest SHA-256 from the maintainer through a separately
trusted channel. Do not trust the adjacent checksum file by itself. Run these
commands from the directory containing `manifest.json`, `release.py` and
`handoff.tar`, replacing `TRUSTED_HANDOFF_PIN` with that exact hash.

First authenticate the manifest and the standalone verifier before executing it:

```sh
python3 -c 'import hashlib,json,pathlib,sys; p=pathlib.Path("manifest.json"); hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[1] or sys.exit("Manifest pin mismatch"); m=json.loads(p.read_bytes()); hashlib.sha256(pathlib.Path("release.py").read_bytes()).hexdigest()==m["bootstrap"]["sha256"] or sys.exit("Verifier checksum mismatch")' TRUSTED_HANDOFF_PIN
```

Only after that succeeds, verify and extract into a new directory:

```sh
python3 release.py . --manifest-sha256 TRUSTED_HANDOFF_PIN --extract ./recipient
```

Success is exit zero, with details in `verification.log`. Normal verification
output stays out of the terminal. To watch it, use `tail -f verification.log` in
another terminal. Allow room for both archives and extracted files. The package
manifest records byte counts; the installed Mage-OS media cache needs extra space.

## 2. Choose and verify one catalog profile

```sh
cd recipient
python3 tools/release.py profiles/starter \\
  --manifest-sha256 {profiles['starter']['manifest_sha256']} \\
  --extract ./starter-staging
```

For the full profile instead:

```sh
python3 tools/release.py profiles/full \\
  --manifest-sha256 {profiles['full']['manifest_sha256']} \\
  --extract ./full-staging
```

These operations are offline. They do not install anything into Magento.
Do not install starter and full into the same populated database.

## 3. Install into an empty Mage-OS lab

Use this handoff's current preflight, not the older copy nested inside rc2. From
`recipient`, for the starter profile:

```sh
php tools/preflight.php --magento-root=/path/to/empty/mageos \\
  --data-dir=./starter-staging/data --log-file=./preflight.log
```

For the full profile, use `--data-dir=./full-staging/data` instead. It checks
product, website, store-view and store-group collisions before provisioning.
Then follow [the installation guide](docs/README.md), retaining an empty-baseline
backup before any installation writes. Run PHP commands in the recipient's own
Mage-OS environment as its web filesystem owner. Provisioning uses an explicit
recipient URL; DNS, TLS and web-server configuration are separate.

The immutable rc2 archives retain their original preparation-era documentation.
Use this handoff's `docs/README.md` for the updated ownership and navigation steps,
and [the acceptance summary](docs/ACCEPTANCE.md) for the 3.5.0 result and limits.

Imports are fresh-install-only. An interrupted import requires restoring the
empty baseline before retrying; download resume is not import resume. No existing
store updater, checkout/payment test, or 3.4/Hyvä compatibility result is claimed.

## Notices and optional downloads

Retain [the terms](docs/TERMS.md), original WANDS MIT notice and citation. Tooling
and authored additions use MIT; generated images use CC0 only where rights are
held. Synthetic media, dimensions and stock are lab illustrations and scenarios,
not manufacturer claims. Per-image provenance limits remain in the catalog data.

The included downloader is optional because both profiles are already present.
See [download instructions](docs/DOWNLOADS.md) when a direct HTTPS mirror becomes
available. No public download service has been published by this handoff build.
'''.encode()


def build_handoff(profile_dirs, output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError('Handoff output must be a new directory')
    if set(profile_dirs) != set(PROFILE_PINS):
        raise ValueError('Both accepted profiles are required')
    files, profiles = {}, {}
    for profile, pin in sorted(PROFILE_PINS.items()):
        root = Path(profile_dirs[profile])
        verify_release(root, pin)
        manifest = json.loads((root / 'manifest.json').read_bytes())
        if manifest.get('profile') != profile or manifest.get('release') != '2026.09.11-rc2':
            raise ValueError('Unexpected profile identity')
        profiles[profile] = {'path': 'profiles/' + profile, 'manifest_sha256': pin, 'counts': manifest['counts']}
        # Only the pinned manifest and explicitly declared archives are copied.
        files[f'profiles/{profile}/manifest.json'] = root / 'manifest.json'
        for artifact in manifest['artifacts']:
            files[f'profiles/{profile}/{artifact["path"]}'] = root / artifact['path']
    for name in DOCS:
        data = (HERE / name).read_bytes()
        if name.endswith('.md'):
            data = data.replace(b'dev/tools/wands_catalog/distribution/', b'tools/')
            data = data.replace(b'python3 release.py ', b'python3 tools/release.py ')
            data = data.replace(b'php ./wands-staging/tools/preflight.php', b'php tools/preflight.php')
        files['docs/' + name] = data
    files['docs/ROCKET-WEB-LICENSE.txt'] = HERE.parent / 'LICENSE.txt'
    for name in TOOLS:
        files['tools/' + name] = HERE / name
    start_here = instructions(profiles)
    files['README.md'] = start_here
    total = sum(value.stat().st_size if isinstance(value, Path) else len(value) for value in files.values())
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < total + 64 * 1024 * 1024:
        raise ValueError('Insufficient handoff output space')
    output.mkdir()
    artifact = write_archive(output / 'handoff.tar', files)
    bootstrap = {'path': 'release.py', 'sha256': digest(HERE / 'release.py')}
    manifest = {'schema': 1, 'release': '2026.09.12-handoff-v3', 'profiles': profiles,
                'status': 'private offline handoff; not published', 'bootstrap': bootstrap,
                'artifacts': [artifact]}
    data = encoded(manifest)
    pin = hashlib.sha256(data).hexdigest()
    (output / 'manifest.json').write_bytes(data)
    (output / 'manifest.sha256').write_text(pin + '  manifest.json\n')
    (output / 'release.py').write_bytes((HERE / 'release.py').read_bytes())
    (output / 'START_HERE.md').write_bytes(start_here.replace(b'(docs/', b'(recipient/docs/'))
    result = verify_release(output, pin)
    result.update(manifest_sha256=pin, archive_bytes=artifact['bytes'])
    (output / 'build-summary.json').write_bytes(encoded(result))
    logging.info('COMPLETE %s', json.dumps(result, sort_keys=True))
    return result


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
        build_handoff({'starter': args.starter, 'full': args.full}, args.output)
    except Exception:
        logging.exception('Handoff build failed')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
