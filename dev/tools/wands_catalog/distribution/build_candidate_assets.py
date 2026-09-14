"""Prepare enriched medium/full release assets locally; never publish or install."""
import argparse
import json
import logging
from pathlib import Path
import re
import shutil

from build_handoff import encoded
from release import digest, verify_release, write_archive

HERE = Path(__file__).resolve().parent
SCRIPTS = ['release.py', 'download.py', 'github_download.py']
DOCS = ['README.md', 'ACCEPTANCE.md', 'HYVA_ACCEPTANCE.md', 'DOWNLOADS.md',
        'GITHUB_RELEASE.md', 'DATA_CARD.md', 'TERMS.md', 'WANDS-LICENSE.txt',
        'CITATION.bib', 'CC0-1.0.txt']


def instructions(profiles, tag):
    lines = ['# Enriched WANDS catalog candidate', '',
        'Versioned catalog assets for dedicated labs. Packaging does not establish Magento runtime acceptance.',
        'Compare the exact pins below with `docs/ENRICHED_ACCEPTANCE.md` in the extracted toolkit.',
        'Older rc2 acceptance results do not qualify these enriched catalog bytes.', '',
        'Choose one profile for a separate empty Mage-OS 3.5 lab:', '']
    for profile, row in sorted(profiles.items()):
        lines.append(f'- {profile}: {row["counts"]["products"]:,} products; manifest `{row["manifest_sha256"]}`.')
    lines += ['', '## Offline verification', '',
        'Obtain each manifest pin and the verifier hash through a trusted channel.',
        'With the authenticated verifier, place the chosen profile assets in a new',
        'directory and remove only their `medium-` or `full-` filename prefix.',
        'For example, `medium-manifest.json` becomes `manifest.json`. Leave the',
        'archive bytes unchanged. Verify and extract into a new staging directory:', '',
        '```sh', 'python3 release.py ./profile --manifest-sha256 TRUSTED_PROFILE_PIN \\',
        '  --extract ./wands-staging', '```', '',
        'Similarly, place `toolkit-manifest.json` and `toolkit-tools.tar` into a new',
        '`toolkit-cache` directory as `manifest.json` and `tools.tar`. Use the toolkit',
        'pin from the authenticated release inventory:', '', '```sh',
        'python3 release.py ./toolkit-cache --manifest-sha256 TRUSTED_TOOLKIT_PIN \\',
        '  --extract ./toolkit', '```', '',
        'Verification is offline and does not install into Magento. Output goes to',
        '`verification.log` in the verified directory. Use `tail -f` to watch it.', '',
        '## Optional GitHub download after publication', '',
        f'The proposed tag is `{tag}`. Building these assets does not create that release.',
        'After a maintainer publishes and supplies trusted hashes, the companion',
        '`github_download.py` supports `--profile medium`, `full`, `toolkit` and `gallery`.',
        'Keep all three authenticated Python scripts together. Download logs go to',
        '`wands-download.log`; interrupted downloads can resume. Imports cannot.', '',
        '## Installation and acceptance', '',
        'Follow `toolkit/docs/README.md` for the fresh-install procedure only.',
        'The separate rc2 acceptance documents describe the older release.',
        'Use this candidate\'s pins and module archive, not a published rc2 module.',
        'Run the current `toolkit/tools/preflight.php` before any installation writes.',
        'Retain an empty-baseline backup and restore it before retrying an interrupted import.',
        'Never layer medium and full onto the same populated database.', '',
        'Check specifications and synthetic disclosures, related products, filters,',
        'configurable choices, bundles, stock, media and search on the installed theme.',
        'Commerce scenario specifications require separate runtime execution.',
        'Gallery additions are a separate optional package, not part of either baseline profile.',
        'Follow `toolkit/docs/GALLERIES.md` after a successful full-profile import.',
        'No checkout, payment or search-ranking improvement is claimed.', '',
        '## Notices', '',
        'Retain the WANDS license and citation, Rocket Web MIT notice and generated-media',
        'CC0 notice where rights are held. Synthetic facts are lab data, not manufacturer',
        'claims. No GPU, API key, theme package or original development checkout is needed.', '']
    return '\n'.join(lines).encode()


def build_assets(profile_dirs, pins, output, *, tag, gallery=None, gallery_pin=None):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError('Asset output must be a new directory')
    if (set(profile_dirs) != {'medium', 'full'} or set(pins) != set(profile_dirs)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', tag)
            or tag == 'catalog-2026.09.12-rc2'):
        raise ValueError('Use medium/full profiles and a new candidate tag')
    sources, profiles = {}, {}
    for profile, root in sorted(profile_dirs.items()):
        root = Path(root)
        if not re.fullmatch('[0-9a-f]{64}', pins[profile]):
            raise ValueError('Invalid manifest pin')
        verify_release(root, pins[profile])
        manifest = json.loads((root / 'manifest.json').read_bytes())
        if manifest.get('profile') != profile or 'enriched' not in manifest.get('release', ''):
            raise ValueError('Unexpected candidate profile identity')
        sources[profile + '-manifest.json'] = root / 'manifest.json'
        for artifact in manifest['artifacts']:
            if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*\.tar', artifact['path'])
                    or artifact['bytes'] >= 2 ** 31):
                raise ValueError('Asset path or size incompatible with GitHub')
            sources[profile + '-' + artifact['path']] = root / artifact['path']
        profiles[profile] = {'manifest_sha256': pins[profile], 'release': manifest['release'],
                             'counts': manifest['counts']}
    if (gallery is None) != (gallery_pin is None):
        raise ValueError('Gallery directory and pin must be supplied together')
    if gallery is not None:
        gallery=Path(gallery)
        verify_release(gallery,gallery_pin)
        manifest=json.loads((gallery/'manifest.json').read_bytes())
        if manifest.get('profile')!='gallery-additions' or manifest.get('products')!=7 or manifest.get('images')!=14:
            raise ValueError('Unexpected gallery scope')
        sources['gallery-manifest.json']=gallery/'manifest.json'
        for artifact in manifest['artifacts']:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*\.tar',artifact['path']) or artifact['bytes']>=2**31:
                raise ValueError('Invalid gallery release asset')
            sources['gallery-'+artifact['path']]=gallery/artifact['path']
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < sum(p.stat().st_size for p in sources.values()) + 64 * 1024 ** 2:
        raise ValueError('Insufficient space for candidate assets')
    # Copies isolate candidate assets from immutable source archives and hard links.
    output.mkdir()
    for name, source in sources.items():
        shutil.copyfile(source, output / name)
        if digest(output / name) != digest(source):
            raise ValueError('Asset changed during copy')
    files = {'tools/' + name: HERE / name for name in SCRIPTS + ['preflight.php']}
    for name in DOCS:
        data = (HERE / name).read_bytes()
        if name.endswith('.md'):
            if name in ('ACCEPTANCE.md','HYVA_ACCEPTANCE.md'):
                data = (b'> Historical rc2 evidence. These results do not qualify other profile pins.\n\n' + data)
            data = data.replace(b'dev/tools/wands_catalog/distribution/', b'tools/')
            data = data.replace(b'php ./wands-staging/tools/preflight.php', b'php tools/preflight.php')
            data = data.replace(b'../../../../app/code/RocketWeb/LabCatalog/view/frontend/layout/', b'source/')
            data = data.replace(b'../docs/screenshots/README.md', b'screenshots/README.md')
        files['docs/' + name] = data
    repository = HERE.parents[3]
    layout = 'hyva_catalogsearch_result_index.xml'
    files['docs/source/' + layout] = repository / 'app/code/RocketWeb/LabCatalog/view/frontend/layout' / layout
    files['docs/screenshots/README.md'] = (HERE.parent / 'docs/screenshots/README.md').read_bytes().replace(
        b'../../distribution/HYVA_ACCEPTANCE.md', b'../HYVA_ACCEPTANCE.md')
    files['docs/ROCKET-WEB-LICENSE.txt'] = HERE.parent / 'LICENSE.txt'
    files['docs/BULK_ENRICHMENT.md'] = (HERE.parent / 'BULK_ENRICHMENT.md').read_bytes().replace(
        b'(distribution/ENRICHED_ACCEPTANCE.md)', b'(ENRICHED_ACCEPTANCE.md)')
    files['docs/ENRICHED_ACCEPTANCE.md'] = HERE / 'ENRICHED_ACCEPTANCE.md'
    files['docs/GALLERIES.md'] = HERE / 'GALLERIES.md'
    files['README.md'] = instructions(profiles, tag)
    artifact = write_archive(output / 'toolkit-tools.tar', files)
    artifact['path'] = 'tools.tar'
    manifest = {'schema': 1, 'release': tag, 'profile': 'toolkit', 'artifacts': [artifact],
                'magento_runtime_verified': False}
    (output / 'toolkit-manifest.json').write_bytes(encoded(manifest))
    toolkit_pin = digest(output / 'toolkit-manifest.json')
    for name in SCRIPTS:
        shutil.copyfile(HERE / name, output / name)
    (output / 'README.md').write_bytes(files['README.md'])
    assets = {p.name: {'bytes': p.stat().st_size, 'sha256': digest(p)} for p in sorted(output.iterdir())}
    inventory = {'schema': 1, 'repository': 'rocketweb/mageos-large-demo-catalog', 'tag': tag,
                 'profile_pins': pins, 'profiles': profiles, 'toolkit_pin': toolkit_pin,
                 'status': 'local candidate; not published', 'magento_runtime_verified': False,
                 'assets': assets}
    if gallery is not None:
        inventory['gallery_pin']=gallery_pin
    (output / 'release-inventory.json').write_bytes(encoded(inventory))
    (output / 'SHA256SUMS').write_text(''.join(digest(p) + '  ' + p.name + '\n' for p in sorted(output.iterdir())))
    logging.info('COMPLETE inventory_sha256=%s assets=%d toolkit_pin=%s',
                 digest(output / 'release-inventory.json'), len(assets) + 2, toolkit_pin)
    return inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for profile in ('medium', 'full'):
        parser.add_argument('--' + profile, type=Path, required=True)
        parser.add_argument('--' + profile + '-sha256', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gallery',type=Path)
    parser.add_argument('--gallery-sha256')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output.with_suffix('.log'), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        build_assets({'medium': args.medium, 'full': args.full},
                     {'medium': args.medium_sha256, 'full': args.full_sha256}, args.output, tag=args.tag,
                     gallery=args.gallery,gallery_pin=args.gallery_sha256)
    except Exception:
        logging.exception('Candidate asset preparation failed')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
