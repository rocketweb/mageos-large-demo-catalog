#!/usr/bin/env python3
"""Prepare bounded native-import batches from the fully accepted expansion export."""
from __future__ import annotations
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from build_expanded_catalog import csv_rows, write_csv, write_json
from prepare_catalog import sha256
from prepare_expansion_update import prepare

CANDIDATE_SHA256 = '921e5e1a0d8a386c93bf0f80dd6543c9d3561e5ad27e31df5b80b9d3e0d8502e'


def check_media_coverage(products, media, excluded, quarantined=frozenset()):
    exclusions=set(excluded)
    if len(exclusions)!=len(excluded) or not exclusions.issubset(products):
        raise ValueError('Invalid explicit media exclusions')
    for sku in exclusions:
        row=products[sku]
        if ((sku.startswith('WANDS-SYN-') and sku not in quarantined) or row['product_online']!='2'
                or row['visibility']!='Not Visible Individually'):
            raise ValueError('Only retained disabled hidden records may remain imageless')
    expected=set(products)-exclusions
    if len(media)!=len(expected) or {r['sku'] for r in media}!=expected:
        raise ValueError('Media assignments must cover every non-excluded target exactly once')


def verified_product_data(package, candidate, manifest, run=None):
    """Rebuild expected product bytes from frozen input and the trusted correction ledger."""
    from feedback_reprocessing import apply_catalog_patches, has_table
    names=('1-simple.csv','2-configurable.csv','3-bundle.csv')
    pins=manifest.get('human_correction_manifests',[])
    if (pins or manifest.get('catalog_quarantine_sha256')) and run is None:raise ValueError('Product corrections require the trusted run')
    rows={r['sku']:r for name in names for r in csv_rows(candidate/'data'/name)}
    if run is not None:
        run=Path(run).resolve();desc=json.loads((run/'run.json').read_text())
        if (Path(desc['candidate']).resolve()!=candidate.resolve()
                or desc['candidate_sha256']!=CANDIDATE_SHA256
                or manifest.get('source_run_sha256')!=sha256(run/'run.json')):
            raise ValueError('Export belongs to another trusted run')
        with closing(sqlite3.connect(f'file:{run / "ledger.sqlite"}?mode=ro',uri=True)) as db:
            db.row_factory=sqlite3.Row
            current=sorted(r[0] for r in db.execute('SELECT DISTINCT manifest_sha256 FROM feedback_reprocessing WHERE active=1')) if has_table(db) else []
            if pins!=current:raise ValueError('Correction receipts differ from trusted run')
            apply_catalog_patches(db,rows)
    from catalog_quarantine import verified_package,apply_fields
    quarantine=verified_package(package,manifest,run)
    apply_fields(rows,quarantine)
    from native_metadata import normalize
    normalizations=normalize(rows)
    if manifest.get('native_metadata_normalizations',[])!=normalizations:raise ValueError('Native metadata normalization evidence changed')
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            expected=candidate/'data'/name
            if pins or quarantine or normalizations:
                expected=Path(tmp)/name
                write_csv(expected,[rows[r['sku']] for r in csv_rows(candidate/'data'/name)])
            if sha256(package/'data'/name)!=sha256(expected):
                raise ValueError('Export product data differs from frozen candidate and approved corrections')
    return rows


def verified_export(package: Path, candidate: Path, run=None):
    if sha256(candidate / 'manifest.json') != CANDIDATE_SHA256:
        raise ValueError('Unapproved candidate')
    for name,pin in json.loads((candidate/'manifest.json').read_text())['outputs'].items():
        if sha256(candidate/name)!=pin:raise ValueError('Frozen candidate bytes changed')
    manifest = json.loads((package / 'manifest.json').read_text())
    if (manifest.get('profile') != 'expanded-measurement-free'
            or manifest.get('source_candidate_sha256') != CANDIDATE_SHA256
            or manifest.get('products') != 107688):
        raise ValueError('Wrong expansion export')
    for name, pin in manifest['files'].items():
        path = package / name
        if Path(name).is_absolute() or '..' in Path(name).parts or not path.resolve().is_relative_to(package.resolve()):
            raise ValueError('Export path escapes package')
        if not path.is_file() or path.stat().st_size != pin['bytes'] or sha256(path) != pin['sha256']:
            raise ValueError('Export bytes changed: ' + name)
    required = {'visual-acceptance.json', 'data/4-media.csv', 'data/media-lineage.json', 'data/attribute-options.json',
                'data/1-simple.csv','data/2-configurable.csv','data/3-bundle.csv'}
    if not required.issubset(manifest['files']):
        raise ValueError('Incomplete export manifest')
    acceptance = json.loads((package / 'visual-acceptance.json').read_text())
    completion=acceptance.get('completion_policy')
    if completion is not None:
        from build_expanded_catalog import digest
        from authorized_completion import AUTHORIZATION
        pin=digest(completion)
        if (completion.get('authorization')!=AUTHORIZATION or completion.get('schema')!=1
                or completion.get('candidate_sha256')!=CANDIDATE_SHA256
                or completion.get('review_identity')!=manifest.get('review_identity')
                or pin!=acceptance.get('completion_policy_sha256')
                or pin!=manifest.get('completion_policy_sha256')):
            raise ValueError('Completion policy differs from export evidence')
    elif manifest.get('completion_policy_sha256'):
        raise ValueError('Completion policy evidence is missing')
    from catalog_quarantine import verified_package,skus,all_quarantined
    quarantine=verified_package(package,manifest,run)
    required_new=48844;required_retained=46602
    if quarantine:
        from export_expanded_catalog import inspect
        _,live,_,_=inspect(Path(run))
        if not live['ready'] or acceptance!=live:raise ValueError('Quarantine acceptance differs from current trusted coverage')
        required_new=live['new_images_required'];required_retained=live['retained_images_expected']
    if (acceptance.get('ready') is not True or acceptance.get('pilot_accepted') is not True
            or acceptance.get('accepted_new_images') != required_new
            or acceptance.get('unresolved_new_images') or acceptance.get('unresolved_retained_briefs')
            or acceptance.get('retained_conflicts')
            or acceptance.get('retained_images_resolved') != required_retained):
        raise ValueError('Image acceptance incomplete')
    verified_product_data(package,candidate,manifest,run)
    return manifest


def prepare_deployment(package, candidate, snapshot, output, batch_size=1000, run=None,reconciliation=None):
    if not 1 <= batch_size <= 2000:
        raise ValueError('Batch size must be 1..2000')
    manifest = verified_export(package, candidate, run)
    products={r['sku']:r for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv')
              for r in csv_rows(package/'data'/name)}
    if output.exists():
        raise ValueError('Choose a fresh deployment directory')
    live = json.loads(snapshot.read_text())
    if live.get('schema') != 2 or 'existing_wands_stock' not in live:
        raise ValueError('Fresh stock-aware destination snapshot required')
    delta = output / 'delta'
    # The exact scope, collisions, website membership and baseline counts are
    # checked before any batch is constructed. No store connection is made.
    plan = prepare(candidate, snapshot, delta, desired_rows=products,reconciliation=reconciliation)
    local = live['root'] == '/Users/matt/code/mageos-latest'
    batches = output / 'batches'
    batches.mkdir()
    actions = []

    def add(kind, rows, **flags):
        for offset in range(0, len(rows), batch_size):
            selected = rows[offset:offset + batch_size]
            filename = f'{len(actions) + 1:04d}-{kind}.csv'
            write_csv(batches / filename, selected)
            actions.append({'action': 'native-import', 'file': 'batches/' + filename,
                            'rows': len(selected), 'preserve_existing_stock': True,
                            'validate_before_apply': True, **flags})

    add('new-simple', csv_rows(delta / 'new-simple.csv'))
    if (delta/'existing-simple.csv').exists():
        add('existing-simple',csv_rows(delta/'existing-simple.csv'))
    if local:
        conversions = [json.loads(line) for line in (delta / 'type-conversions.jsonl').read_text().splitlines()]
        for offset in range(0, len(conversions), 100):
            actions.append({'action': 'convert-parents', 'file': 'delta/type-conversions.jsonl',
                            'offset': offset, 'limit': min(100, len(conversions) - offset),
                            'dry_run_before_apply': True})
    add('new-configurable', csv_rows(delta / 'new-configurable.csv'))
    add('existing-configurable', csv_rows(delta / 'existing-configurable.csv'))
    if (delta / 'new-bundle.csv').exists():
        add('new-bundle', csv_rows(delta / 'new-bundle.csv'))
    if (delta/'existing-bundle.csv').exists():
        add('existing-bundle',csv_rows(delta/'existing-bundle.csv'))
    media = csv_rows(package / 'data/4-media.csv')
    lineage = json.loads((package / 'data/media-lineage.json').read_text())
    from catalog_quarantine import verified_package,skus
    quarantine=verified_package(package,manifest,run)
    check_media_coverage(products, media, lineage.get('excluded_disabled_skus', []),skus(quarantine))
    for row in media:
        for role in ('base_image', 'small_image', 'thumbnail'):
            name = 'media' + row[role]
            if name not in manifest['files'] or not row[role].startswith('/wands-expanded/'):
                raise ValueError('Media assignment lacks accepted image bytes')
    add('media', media)
    write_json(output / 'attribute-options.json', json.loads((package / 'data/attribute-options.json').read_text()))
    current = {sku for sku, row in live['products'].items() if row['wands']}
    options = json.loads((package / 'data/attribute-options.json').read_text())
    write_json(output / 'snapshot-request.json', {
        'version': 1, 'expected_host': 'relevance.comtom.lab', 'packet_sha256': sha256(package / 'manifest.json'),
        'skus': sorted(current), 'bundle_skus': sorted(sku for sku in current if live['products'][sku]['type'] == 'bundle'),
        'attributes': sorted(set(options) | {'image', 'small_image', 'thumbnail', 'name', 'description', 'status', 'price', 'special_price'})})
    result = {'schema': 1, 'state': 'prepared; not applied', 'target_root': live['root'],
              'website_code': 'wands', 'website_id': live['website_id'], 'store_id': live['store_id'],
              'candidate_sha256': CANDIDATE_SHA256, 'export_manifest_sha256': sha256(package / 'manifest.json'),
              'snapshot_sha256': sha256(snapshot), 'delta': plan, 'reconciliation': reconciliation, 'actions': actions,
              'media_assignments': len(media), 'excluded_disabled_skus': lineage.get('excluded_disabled_skus', []),
              'required_before_apply': ['Refresh and compare destination snapshot',
                  'Private verified database, catalog-row and module backups with tested inverse',
                  'Install only the reviewed LabCatalog module changes',
                  'Compile dependency injection and clear config/EAV caches after module changes, even in developer mode when old compiled metadata exists',
                  'Add missing WANDS attribute options with reversible journal',
                  'Stage and verify accepted media bytes in pub/media/import/wands-expanded'],
              'required_after_apply': ['Verify exact 107688 WANDS product identity and 27736 configurable links',
                  'Verify existing stock and unrelated-data fingerprints',
                  'Verify all three media roles against accepted hashes and hide old WANDS gallery views',
                  'Curate navigation, reindex and clean relevant caches',
                  'Verify live categories, product options, images, cart and search behavior'],
              'files': {str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    write_json(output / 'deployment.json', result)
    return {key: result[key] for key in ('state', 'target_root', 'candidate_sha256', 'export_manifest_sha256')} | {'actions': len(actions)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('package', 'candidate', 'snapshot', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--batch-size', type=int, default=1000)
    p.add_argument('--run',type=Path,help='Trusted local run required for approved product corrections')
    a = p.parse_args()
    print(json.dumps(prepare_deployment(a.package.resolve(), a.candidate.resolve(), a.snapshot.resolve(), a.output.resolve(), a.batch_size,a.run), indent=2))
