"""Build a private media update from a pinned release and verified image selection.

Preserves the published module, product CSVs, QA media and download helpers.
No GitHub, Magento, Git mutation or model calls.
"""
import argparse
from collections import Counter
import csv
import hashlib
from itertools import zip_longest
import json
import logging
from pathlib import Path
import re
import shutil
import sqlite3
import tarfile

from release import digest, safe_path, verify_release, write_archive
from download import MANIFEST_LIMIT

BASE_FULL_PIN = 'ec5c1763aea94535d1bacc44db2d2ac76131c4eca3763e257ebab677accaf958'
BASE_TOOLKIT_PIN = '299ed4a97b83b2d796b8310cb2f09e55e6d67187f494dbe8d213f829736f3ac8'
BASE_COMMIT = '45ff3dcf2a591fd79a2519b8d8af8fd3e4844707'
ROLES = ('base_image', 'small_image', 'thumbnail', 'thumbnail_image')
HERE = Path(__file__).resolve().parent


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def extract_subset(root, manifest, output, include):
    """Only copy declared, regular members after archive and member hash checks."""
    result = {}
    for artifact in manifest['artifacts']:
        wanted = {name for name in artifact['files'] if include(name)}
        if not wanted:
            continue
        source = root / artifact['path']
        if digest(source) != artifact['sha256']:
            raise ValueError('Baseline archive changed after verification')
        with tarfile.open(source, 'r:') as archive:
            for member in archive:
                if member.name not in wanted:
                    continue
                safe_path(member.name)
                if not member.isfile() or member.name in result:
                    raise ValueError('Invalid baseline member')
                target = output / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as stream, target.open('xb') as destination:
                    shutil.copyfileobj(stream, destination)
                info = artifact['files'][member.name]
                if target.stat().st_size != info['bytes'] or digest(target) != info['sha256']:
                    raise ValueError('Baseline member changed')
                result[member.name] = target
        if wanted - result.keys():
            raise ValueError('Missing baseline members')
    return result


def read_mapping(path, expected=95401):
    result = {}
    with path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            for field, sha_field in [('original_file', 'original_sha256'), ('selected_file', 'selected_sha256')]:
                if not re.fullmatch(r'[0-9a-f]{64}\.jpg', row[field]) or row[field][:-4] != row[sha_field]:
                    raise ValueError('Invalid content-addressed selection')
            if row['original_file'] in result or row['action'] not in ['original', 'white_reused', 'white_new', 'mirror_replacement']:
                raise ValueError('Duplicate or invalid selection action')
            if row['action'] == 'original' and row['selected_sha256'] != row['original_sha256']:
                raise ValueError('Retained original must preserve exact bytes')
            result[row['original_file']] = row
    if len(result) != expected:
        raise ValueError('Incomplete image selection')
    return result


def check_media_csv(original, selected, mappings):
    """Require exactly the original rows, labels and roles, with mapped images."""
    count = 0
    with original.open(newline='') as old, selected.open(newline='') as new:
        before, after = csv.DictReader(old), csv.DictReader(new)
        if before.fieldnames != after.fieldnames:
            raise ValueError('Media CSV schema changed')
        for a, b in zip_longest(before, after):
            if a is None or b is None:
                raise ValueError('Media CSV row count changed')
            for field in a:
                expected = a[field]
                if field in ROLES and expected:
                    name = Path(expected).name
                    if str(Path(expected).parent) != '/wands-expanded' or name not in mappings:
                        raise ValueError('Unknown original media reference')
                    expected = '/wands-expanded/' + mappings[name]['selected_file']
                if b[field] != expected:
                    raise ValueError('Media CSV changed outside its verified image mapping: ' + field)
            count += 1
    return count


def rewrite_inventory(original, mappings, media_root, verification_sha):
    result, images = {}, {}
    if set(original) != {'media/wands-expanded/' + name for name in mappings}:
        raise ValueError('Selection does not cover baseline image inventory')
    for file, row in mappings.items():
        prior = original['media/wands-expanded/' + file]
        if prior['sha256'] != row['original_sha256']:
            raise ValueError('Selection source hash differs from published baseline')
        path = media_root / row['selected_file']
        if path.is_symlink() or not path.is_file() or digest(path) != row['selected_sha256']:
            raise ValueError('Selected JPEG changed')
        name = 'media/wands-expanded/' + row['selected_file']
        item = {'sha256': row['selected_sha256'], 'bytes': path.stat().st_size,
                'selection_verification_sha256': verification_sha,
                'background_action': row['action'], 'selection_reason': row['reason']}
        if name in result:
            result[name]['source_sha256s'].append(row['original_sha256'])
        else:
            item['source_sha256s'] = [row['original_sha256']]
            result[name] = item
        images[name] = path
    return result, images


def rewrite_lineage(original, mappings):
    for assignment in original['assignments'].values():
        row = mappings[Path(assignment['file']).name]
        if assignment['sha256'] != row['original_sha256']:
            raise ValueError('Baseline lineage disagrees with selection source')
        assignment.update(file='media/wands-expanded/' + row['selected_file'],
                          sha256=row['selected_sha256'], source_sha256=row['original_sha256'])
    return original


def check_references(data, images):
    assignments = roles = 0
    for name in ['data/4-media.csv', 'data/6-qa.csv']:
        with data[name].open(newline='') as stream:
            for row in csv.DictReader(stream):
                assigned = False
                for field in ROLES:
                    value = row.get(field)
                    if value:
                        if 'media/' + value.lstrip('/') not in images:
                            raise ValueError('CSV references missing release media: ' + value)
                        roles += 1
                        assigned = True
                assignments += assigned
    return {'media_assignments': assignments, 'media_roles': roles}


def media_archives(output, files):
    result, chunk, size = [], {}, 0
    for name, path in sorted(files.items()):
        member_size = 512 + ((path.stat().st_size + 511) // 512) * 512
        if chunk and size + member_size + 10240 > 512 * 1024**2:
            result.append(write_archive(output / f'media-{len(result)+1:03d}.tar', chunk))
            logging.info('Archived media chunk %d', len(result))
            chunk, size = {}, 0
        if member_size + 10240 > 512 * 1024**2:
            raise ValueError('JPEG exceeds media chunk size')
        chunk[name] = path
        size += member_size
    if chunk:
        result.append(write_archive(output / f'media-{len(result)+1:03d}.tar', chunk))
    return result


def guide(tag, counts, summary):
    white = sum(summary['counts'][key] for key in ['white_reused', 'white_new', 'mirror_replacement'])
    return f'''# Mage-OS catalog: white backgrounds

`{tag}` contains 107,815 synthetic product records, all six core Mage-OS product
types and 127 QA fixtures. Of the 95,401 catalog image selections, {white:,}
use white-background JPGs and {summary['counts']['original']} retain original
images. The physical package contains {counts['image_files']:,} JPEG files,
including 16 unchanged QA images, plus three fictional PDF/ZIP downloads.

Minor cutout changes are accepted. Room Bundles, failed glass outlines, likely
scenes and pending or uncertain reviews retain originals. The image review is
incomplete; this is a verified selection with original-image fallbacks.

## Download and verify

Use Python 3.11 or newer. Authenticate `github_download.py`, `download.py` and
`release.py` with the hashes in the release notes before executing them. Keep all
three files together. Get the full and toolkit pins from those same notes:

```sh
python3 github_download.py --anonymous --repo rocketweb/mageos-large-demo-catalog \\
  --tag {tag} --profile toolkit --cache-dir ./cache --manifest-sha256 TRUSTED_TOOLKIT_PIN
python3 release.py ./cache/TRUSTED_TOOLKIT_PIN \\
  --manifest-sha256 TRUSTED_TOOLKIT_PIN --extract ./toolkit
python3 github_download.py --anonymous --repo rocketweb/mageos-large-demo-catalog \\
  --tag {tag} --profile full --cache-dir ./cache --manifest-sha256 TRUSTED_FULL_PIN
python3 release.py ./cache/TRUSTED_FULL_PIN \\
  --manifest-sha256 TRUSTED_FULL_PIN --extract ./wands-staging
```

Replace each pin placeholder with the matching SHA-256 from the release notes.
The attached assets contain the media. GitHub's automatic source archives do not.
Downloads resume; imports do not. Use the portable module and tools packaged with
this release. No model, GPU, API key or theme package is needed by recipients.

## Install into an empty dedicated lab

Back up the empty database and application configuration first. Run PHP in the
destination environment as its web filesystem owner. Make staging and toolkit
directories available inside any container. Stop after any nonzero command and
restore the empty baseline before retrying an interrupted import.

```sh
php ./toolkit/tools/preflight.php --magento-root=/path/to/empty/mageos \\
  --data-dir=./wands-staging/data --log-file=./preflight.log
```

Then change to the Mage-OS root and replace the staging path and base URL:

```sh
set -e
WANDS_STAGE=/path/to/wands-staging
test ! -e app/code/RocketWeb/LabCatalog
mkdir -p app/code/RocketWeb/LabCatalog
cp -R "$WANDS_STAGE/module/." app/code/RocketWeb/LabCatalog/
php bin/magento module:enable RocketWeb_LabCatalog
php bin/magento setup:upgrade
php bin/magento lab:wands:provision --base-url=https://catalog.example.test/
mkdir -p var/wands-lab/data pub/media/import
cp -R "$WANDS_STAGE/data/." var/wands-lab/data/
cp -R "$WANDS_STAGE/media/." pub/media/import/
for phase in 1-simple 2-configurable 3-bundle 4-media 5-merchandising; do
  php bin/magento lab:wands:import --file="var/wands-lab/data/$phase.csv"
done
php bin/magento lab:wands:curate-navigation
php bin/magento lab:wands:import --file=var/wands-lab/data/6-qa.csv
php bin/magento indexer:reindex
php bin/magento cache:clean
```

Configure the web server for `MAGE_RUN_TYPE=website` and `MAGE_RUN_CODE=wands`.
Provisioning does not configure DNS, TLS or routing. Production mode needs its
normal compilation and static-content deployment. Use USD and the standard tax
classes `None` and `Taxable Goods`. Keep `wands-expanded`, `wands-qa` and
`wands-qa-downloads` directories intact. With this baseline module, curate
navigation before phase 6 so the QA Fixtures menu remains visible.

This full profile is for a fresh lab. Applying it over an existing full catalog
requires a separate migration and rollback plan.

## Verification and acceptance scope

The product CSVs, portable module, QA media, download payloads and executable
download helpers are unchanged from `catalog-2026.10.06`. Catalog image bytes,
the image-role CSV, image inventories and image lineage have new checksums.
Archives, members and media assignments are checked offline. The original media
CSV and every original image remain unchanged on the build machine.

Historical native/runtime acceptance in `INSTALLATION_ACCEPTANCE.json` belongs
to `catalog-2026.10.06`. This exact media update has not been imported into an
empty Mage-OS store or qualified on a live storefront. Checkout, payments, real
browser uploads and post-order download access remain unqualified. Hash checks
prove artifact integrity, not visual perfection or live-store acceptance.

## Data and rights

Prices, inventory, specifications, descriptions and images are synthetic lab data.
Image geometry is illustrative. Retain the MIT, WANDS citation and CC0 notices.
CC0 applies only to rights held by Rocket Web; third-party rights are not waived.
Historical model and reference provenance is incomplete. The derived catalog is
not the original WANDS search benchmark. See `DATA_CARD.md` and `TERMS.md`.
'''


def build(base, selection, output, tag):
    base, selection, output = map(lambda p: Path(p).resolve(), [base, selection, output])
    if not re.fullmatch(r'catalog-\d{4}\.\d{2}\.\d{2}(?:-[a-z0-9-]+)?', tag):
        raise ValueError('Use a dated catalog release tag')
    if output.exists():
        raise FileExistsError('Use a new private release directory')
    logging.info('Verifying immutable published baseline')
    verify_release(base / 'full', BASE_FULL_PIN)
    verify_release(base / 'toolkit', BASE_TOOLKIT_PIN)
    baseline = json.loads((base / 'full/manifest.json').read_bytes())
    toolkit_baseline = json.loads((base / 'toolkit/manifest.json').read_bytes())
    report = json.loads((selection / 'verification.json').read_bytes())
    safety = json.loads((selection / 'overnight-safety.json').read_bytes())
    if (report.get('state') != 'complete' or not report.get('category_policy_verified') or report['originals_hash_verified'] != 95401
            or report['selected_hashes_verified'] != 95401 or report['originals_modified']
            or safety['held_glass_selected_white'] or safety['room_bundle_originals'] != 50):
        raise ValueError('Image selection is not qualified')
    with sqlite3.connect((selection / 'audit.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
        if (db.execute('SELECT count(*) FROM images').fetchone()[0] != 95401
                or db.execute('SELECT count(*) FROM images WHERE decision IS NULL').fetchone()[0]
                or db.execute("SELECT count(*) FROM images JOIN glass_outline_checks USING(file) WHERE decision='white' AND verdict!='preserved'").fetchone()[0]
                or db.execute("SELECT count(*) FROM images WHERE decision='original' AND reason='room_bundle_preserve_scene'").fetchone()[0] != 50):
            raise ValueError('Snapshot database does not preserve required originals')
    verification_sha = digest(selection / 'verification.json')
    for name, key in [('selection.csv', 'selection_csv_sha256'), ('selected-data/4-media.csv', 'media_csv_sha256')]:
        if digest(selection / name) != report[key]:
            raise ValueError('Selection CSV checksum changed')
    mappings = read_mapping(selection / 'selection.csv')
    if dict(Counter(row['action'] for row in mappings.values())) != report['counts']:
        raise ValueError('Selection action counts disagree with verification')
    full, toolkit, assets, stage = [output / name for name in ['full', 'toolkit', 'assets', 'build-inputs']]
    for path in [full, toolkit, assets, stage]:
        path.mkdir(parents=True)
    data = extract_subset(base / 'full', baseline, stage / 'full', lambda n: n.startswith(('data/', 'docs/')))
    qa_media = extract_subset(base / 'full', baseline, stage / 'qa', lambda n: n.startswith(('media/wands-qa/', 'media/wands-qa-downloads/')))
    tools = extract_subset(base / 'toolkit', toolkit_baseline, stage / 'toolkit', lambda n: True)
    if digest(data['data/4-media.csv']) != report['original_csv_sha256']:
        raise ValueError('Selection was not built from the published media CSV')
    selected_csv = selection / 'selected-data/4-media.csv'
    if check_media_csv(data['data/4-media.csv'], selected_csv, mappings) != report['media_assignments']:
        raise ValueError('Media assignment count differs from image verification')
    selected_inventory, images = rewrite_inventory(json.loads(data['data/media-inventory.json'].read_bytes()),
        mappings, selection / 'selected-media/wands-expanded', verification_sha)
    images.update(qa_media)
    lineage = rewrite_lineage(json.loads(data['data/media-lineage.json'].read_bytes()), mappings)
    counts = dict(baseline['counts'])
    jpeg_paths = [path for name, path in images.items() if name.endswith('.jpg')]
    counts.update(image_files=len(jpeg_paths), distinct_image_hashes=len({path.stem for path in jpeg_paths}),
                  white_background_selections=95401-report['counts']['original'],
                  original_background_selections=report['counts']['original'])
    public_summary = {'schema': 1, 'base_release': baseline['release'], 'source_images': 95401,
        'counts': report['counts'], 'pending_reviews_kept_original': report['pending_reviews_kept_original'],
        'individual_visual_audit_complete': False, 'room_bundle_originals': 50,
        'held_glass_selected_white': 0, 'originals_hash_verified': 95401,
        'selected_hashes_verified': 95401, 'original_csv_sha256': report['original_csv_sha256'],
        'selection_csv_sha256': report['selection_csv_sha256'], 'media_csv_sha256': report['media_csv_sha256'],
        'selection_verification_sha256': verification_sha, 'policy_identity': report['policy_identity'],
        'expanded_policy_identity': report['expanded_policy_identity'],
        'originals_modified': False, 'new_media_runtime_acceptance': 'not performed'}
    for name, value in [('data/media-inventory.json', selected_inventory), ('data/media-lineage.json', lineage),
                        ('data/counts.json', counts), ('docs/WHITE_BACKGROUND_SELECTION.json', public_summary)]:
        path = stage / 'updated' / name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(encoded(value));data[name] = path
    data['data/4-media.csv'] = selected_csv
    data['data/background-selection.csv'] = selection / 'selection.csv'
    actual_refs = check_references(data, images)
    if any(actual_refs[key] != baseline['counts'][key] for key in actual_refs):
        raise ValueError('Release media references differ from baseline coverage')
    # QA source_file values name the previous release; their packaged bytes stay intact.
    qa_lineage = json.loads(data['data/qa/media-lineage.json'].read_bytes())
    for item in qa_lineage.values():
        item.update(source_release=baseline['release'], packaged_file='media/wands-qa/' + item['sha256'] + '.jpg')
        if item['packaged_file'] not in images:
            raise ValueError('QA lineage references missing retained media')
    qa_lineage_path = stage / 'updated/data/qa/media-lineage.json';qa_lineage_path.parent.mkdir(parents=True, exist_ok=True)
    qa_lineage_path.write_bytes(encoded(qa_lineage));data['data/qa/media-lineage.json'] = qa_lineage_path
    acceptance = json.loads(data['docs/INSTALLATION_ACCEPTANCE.json'].read_bytes())
    acceptance.update(applies_to_release=baseline['release'], new_media_runtime_acceptance='not performed')
    acceptance_path = stage / 'updated/docs/INSTALLATION_ACCEPTANCE.json';acceptance_path.write_bytes(encoded(acceptance))
    data['docs/INSTALLATION_ACCEPTANCE.json'] = acceptance_path
    guide_bytes = guide(tag, counts, public_summary).encode()
    data['docs/PRODUCTION_RELEASE.md'] = guide_bytes
    card = data['docs/DATA_CARD.md'].read_text().replace('catalog-2026.10.06', tag)
    card = card.replace('Source image bytes are preserved.', 'Original images remain intact; packaged image selections include white-background derivatives.')
    card = card.replace('| Distinct accepted JPEG contents | 95,401 |', f"| Distinct packaged JPEG contents | {counts['distinct_image_hashes']:,} |")
    card = '# White-background media update\n\nSee `WHITE_BACKGROUND_SELECTION.json` for counts and review limits.\nNative runtime acceptance is inherited from the base catalog and does not qualify this media update.\n\n' + card
    data['docs/DATA_CARD.md'] = card.encode()
    data['docs/build_media_release.py'] = Path(__file__).resolve()
    preserved = {}
    original_files = {n: info for a in baseline['artifacts'] for n, info in a['files'].items()}
    for name, path in data.items():
        if name in original_files and isinstance(path, Path) and digest(path) == original_files[name]['sha256']:
            preserved[name] = digest(path)
    required = [f'data/{name}.csv' for name in ['1-simple', '2-configurable', '3-bundle', '5-merchandising', '6-qa']]
    if not set(required) <= preserved.keys():
        raise ValueError('Non-media product data changed')
    logging.info('Writing release archives')
    artifacts = [write_archive(full / 'catalog.tar', data)]
    old_module = next(a for a in baseline['artifacts'] if a['path'] == 'module.tar')
    shutil.copy2(base / 'full/module.tar', full / 'module.tar')
    if digest(full / 'module.tar') != old_module['sha256']:
        raise ValueError('Published module changed')
    artifacts.append(old_module)
    artifacts += media_archives(full, images)
    for artifact in artifacts:
        if artifact['bytes'] >= 2**31:
            raise ValueError('Release asset exceeds GitHub size limit')
    manifest = {**baseline, 'release': tag, 'counts': counts, 'artifacts': artifacts,
                'inputs': {**baseline['inputs'], 'base_full_manifest': BASE_FULL_PIN,
                           'base_toolkit_manifest': BASE_TOOLKIT_PIN, 'image_selection_verification': verification_sha},
                'media_update_source': {'builder_sha256': digest(Path(__file__)),
                                      'selection_csv_sha256': report['selection_csv_sha256']},
                'runtime_scope': 'Base module/product-data acceptance inherited; new media has offline verification only'}
    content = encoded(manifest)
    if len(content) > MANIFEST_LIMIT:
        raise ValueError('Release manifest exceeds downloader limit')
    (full / 'manifest.json').write_bytes(content);full_pin = digest(full / 'manifest.json')
    full_verification = verify_release(full, full_pin)
    tools.update({'README.md': guide_bytes, 'docs/PRODUCTION_RELEASE.md': guide_bytes,
                  'docs/DATA_CARD.md': data['docs/DATA_CARD.md'], 'docs/INSTALLATION_ACCEPTANCE.json': acceptance_path,
                  'docs/WHITE_BACKGROUND_SELECTION.json': data['docs/WHITE_BACKGROUND_SELECTION.json']})
    artifact = write_archive(toolkit / 'tools.tar', tools)
    (toolkit / 'manifest.json').write_bytes(encoded({'schema': 1, 'release': tag, 'profile': 'toolkit', 'artifacts': [artifact]}))
    toolkit_pin = digest(toolkit / 'manifest.json');toolkit_verification = verify_release(toolkit, toolkit_pin)
    for profile, folder in [('full', full), ('toolkit', toolkit)]:
        for path in folder.iterdir():
            (assets / (profile + '-' + path.name)).hardlink_to(path)
    helper_hashes = {}
    for name in ['github_download.py', 'download.py', 'release.py']:
        source = tools['tools/' + name]
        shutil.copy2(source, assets / name);helper_hashes[name] = digest(assets / name)
    (assets / 'README.md').write_bytes(guide_bytes)
    inventory = {'schema': 1, 'repository': 'rocketweb/mageos-large-demo-catalog', 'tag': tag,
        'source_target_commit': BASE_COMMIT, 'profile_pins': {'full': full_pin, 'toolkit': toolkit_pin},
        'counts': counts, 'image_selection': public_summary, 'offline_verification': full_verification,
        'toolkit_verification': toolkit_verification, 'preserved_nonmedia_members': preserved,
        'module_archive_unchanged': True, 'helper_sha256': helper_hashes,
        'assets': {p.name: {'bytes': p.stat().st_size, 'sha256': digest(p)} for p in sorted(assets.iterdir())}}
    (assets / 'release-inventory.json').write_bytes(encoded(inventory))
    (assets / 'SHA256SUMS').write_text(''.join(digest(p) + '  ' + p.name + '\n' for p in sorted(assets.iterdir())))
    (output / 'prepublication-verification.json').write_bytes(encoded({'prepared': True, 'published': False,
        'full': full_verification, 'toolkit': toolkit_verification, 'profile_pins': inventory['profile_pins'],
        'media_references': actual_refs, 'module_archive_unchanged': True,
        'product_csvs_unchanged': required, 'selection_verification_sha256': verification_sha}))
    logging.info('Prepared %s: %s', tag, inventory['profile_pins'])
    return inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['base', 'selection', 'output']:
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    inventory = build(args.base, args.selection, args.output, args.tag)
    print(json.dumps({'tag': inventory['tag'], 'counts': inventory['counts'], 'pins': inventory['profile_pins']}))


if __name__ == '__main__':
    main()
