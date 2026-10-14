"""Install and update a pinned WANDS catalog in a dedicated existing test installation."""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlsplit

from github_download import GitHubAssets
from download import fetch_release
from release import digest, safe_path, verify_release

HERE = Path(__file__).resolve().parent
DEFAULT_TAG = 'catalog-2026.10.06'
TRUSTED_RELEASES = {DEFAULT_TAG: 'ec5c1763aea94535d1bacc44db2d2ac76131c4eca3763e257ebab677accaf958'}
SUPPORTED_VERSIONS = {'mage-os': {'3.5.0', '3.6.0'}, 'magento': {'2.4.9'}}
CANDIDATE_VERSIONS = {}
PHASES = ('1-simple', '2-configurable', '3-bundle', '4-media', '5-merchandising', '6-qa')
PRODUCT_PHASES = ('1-simple', '2-configurable', '3-bundle', '6-qa')
STOCK_FIELDS = {'qty', 'is_in_stock', 'manage_stock', 'use_config_manage_stock', 'out_of_stock_qty',
                'use_config_min_qty', 'min_cart_qty', 'use_config_min_sale_qty', 'max_cart_qty',
                'use_config_max_sale_qty', 'backorders', 'use_config_backorders', 'notify_on_stock_below',
                'use_config_notify_stock_qty', 'qty_increments', 'use_config_qty_increments',
                'enable_qty_increments', 'use_config_enable_qty_inc', 'is_qty_decimal', 'inventory_source'}
STRUCTURAL_FIELDS = {'product_type', 'attribute_set_code', 'product_websites', 'categories',
                     'configurable_variations', 'configurable_variation_labels', 'custom_options',
                     'associated_skus', 'related_skus', 'upsell_skus', 'crosssell_skus',
                     'additional_attributes'}
MEDIA_FIELDS = {'base_image', 'small_image', 'thumbnail_image', 'swatch_image', 'base_image_label',
                'small_image_label', 'thumbnail_image_label', 'swatch_image_label',
                'additional_images', 'additional_image_labels'}
EMPTY = '__EMPTY__VALUE__'
BACKUP_PATHS = ('app/etc/config.php', 'app/etc/env.php', 'app/code/RocketWeb/LabCatalog', 'pub/media',
                'var/wands-lab/data', 'var/wands-installer/current')


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('wb') as output:
        os.chmod(temporary, 0o600)
        output.write(encoded(value))
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def tree_inventory(root, exclude=()):
    root = Path(root)
    if root.is_symlink():
        raise ValueError('Symlinked catalog paths are unsupported: ' + str(root))
    if not root.exists():
        return {}
    if root.is_file():
        return {'.': digest(root)}
    result = {}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if any(name == prefix or name.startswith(prefix + '/') for prefix in exclude):
            continue
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('Only regular files/directories are supported: ' + str(path))
        if path.is_file():
            result[name] = digest(path)
    return result


def validate_destination(root):
    for name in (*BACKUP_PATHS, 'var/wands-installer', 'pub/media/import'):
        path = root / name
        for item in (path, *path.parents):
            if item == root:
                break
            if item.is_symlink():
                raise ValueError('Destination symlink refused: ' + str(item))


def catalog_media_inventory(root):
    result = {}
    for name in ('pub/media/catalog/product', 'pub/media/downloadable'):
        result.update({name + '/' + file: sha for file, sha in tree_inventory(root / name, exclude=('cache',)).items()})
    return result


def read_rows(path):
    if not path.exists():
        return {}
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or reader.fieldnames[0] != 'sku' or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('Invalid CSV header: ' + path.name)
        result = {}
        for row in reader:
            sku = row.get('sku', '')
            if not sku.startswith('WANDS-') or sku in result or None in row or None in row.values():
                raise ValueError('Invalid or duplicate WANDS row: ' + path.name)
            result[sku] = row
        return result


def catalog_data(data):
    phases = {phase: read_rows(data / (phase + '.csv')) for phase in PHASES}
    products = {}
    for phase in PRODUCT_PHASES:
        for sku, row in phases[phase].items():
            if sku in products or not row.get('product_type'):
                raise ValueError('Duplicate or incomplete product definition: ' + sku)
            products[sku] = row['product_type']
    counts = json.loads((data / 'counts.json').read_bytes())
    if len(products) != counts['products'] or dict(Counter(products.values())) != counts['product_types']:
        raise ValueError('Product CSVs disagree with release counts')
    effective, owners = {}, {}
    for phase, rows in phases.items():
        for sku, row in rows.items():
            if sku not in products:
                raise ValueError('Import phase refers to an undeclared product: ' + sku)
            effective.setdefault(sku, {}).update(row)
            owners.setdefault(sku, {}).update({field: phase for field in row})
    return phases, products, effective, owners


def image_names(row):
    names = set()
    for field in ('base_image', 'small_image', 'thumbnail_image', 'swatch_image', 'additional_images'):
        for name in row.get(field, '').split(','):
            if name and name != 'no_selection':
                names.add(safe_path(name.lstrip('/')).as_posix())
    return sorted(names)


def update_delta(before, after, output):
    """Emit minimal CSVs; refuse operations that append imports cannot safely express."""
    _, old_products, old, _ = catalog_data(before)
    phases, products, new, owners = catalog_data(after)
    removed = sorted(set(old_products) - set(products))
    if removed:
        raise ValueError(f'Update removes {len(removed)} products. Use an explicitly approved reset/reinstall.')
    groups = defaultdict(list)
    added = set(products) - set(old_products)
    changed = set()
    before_values = {}
    before_gallery = {}
    for phase, rows in phases.items():
        for sku in sorted(added & rows.keys()):
            row = rows[sku]
            groups[(phase, tuple(row))].append(row)
    for sku in sorted(set(old_products) & set(products)):
        fields = set(old[sku]) | set(new[sku])
        differences = {field for field in fields if old[sku].get(field, '') != new[sku].get(field, '')}
        for field in differences:
            if field in STRUCTURAL_FIELDS or field.startswith(('bundle_', 'downloadable_')):
                raise ValueError(f'Unsupported structural update for {sku}: {field}. Reset/reinstall is available.')
            if field not in new[sku]:
                raise ValueError(f'Update removes a column for {sku}: {field}')
        differences -= STOCK_FIELDS | {'sku'}
        if differences & MEDIA_FIELDS:
            before_gallery[sku] = image_names(old[sku])
            differences |= MEDIA_FIELDS & new[sku].keys()
        for phase in PHASES:
            selected = sorted(field for field in differences if owners[sku][field] == phase)
            if selected:
                header = ('sku', *selected)
                row = {'sku': sku}
                for field in selected:
                    value = new[sku][field]
                    if not value and field in MEDIA_FIELDS:
                        if field in ('base_image', 'small_image', 'thumbnail_image', 'swatch_image'):
                            value = 'no_selection'
                        else:
                            continue
                    row[field] = value or EMPTY
                header = tuple(row)
                groups[(phase, header)].append(row)
                changed.add(sku)
                before_values.setdefault(sku, {}).update({field: old[sku].get(field, '') for field in selected if field not in MEDIA_FIELDS})
    output.mkdir(parents=True, exist_ok=False)
    files = []
    for index, ((phase, header), rows) in enumerate(sorted(groups.items()), 1):
        name = f'{index:03d}-{phase}.csv'
        with (output / name).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)
        files.append(name)
    write_json(output / 'before-values.json', before_values)
    write_json(output / 'before-gallery.json', before_gallery)
    return {'added_products': len(added), 'changed_products': len(changed), 'removed_products': 0,
            'preserves_existing_stock': True, 'csv_files': files,
            'gallery_reset_products': len(before_gallery), 'gallery_checks_sha256': digest(output / 'before-gallery.json'),
            'csv_sha256': {name: digest(output / name) for name in files}}


def prepare_release(args):
    pin = args.manifest_sha256 or TRUSTED_RELEASES.get(args.tag)
    if not pin or not re.fullmatch('[0-9a-f]{64}', pin):
        raise ValueError('Supply a trusted --manifest-sha256 for this exact release tag')
    work = args.work_dir.resolve()
    if work == args.magento_root or work.is_relative_to(args.magento_root):
        raise ValueError('--work-dir must be outside the Magento root')
    work.mkdir(parents=True, exist_ok=True)
    os.chmod(work, 0o700)
    if args.release_dir:
        cache = args.release_dir.resolve()
    else:
        print('Downloading and verifying ' + args.tag + ' (verified transfers resume).', flush=True)
        client = GitHubAssets('rocketweb/mageos-large-demo-catalog', args.tag, args.profile, token='')
        cache = fetch_release(client.base_url, work / 'cache', pin, opener=client)
        # The downloader returns a manifest; its cache location is keyed by the trusted pin.
        cache = work / 'cache' / pin
    verify_release(cache, pin)
    manifest = json.loads((cache / 'manifest.json').read_bytes())
    if manifest.get('release') != args.tag or manifest.get('profile') != args.profile:
        raise ValueError('Manifest release/profile differs from requested destination')
    stage = work / ('stage-' + pin)
    if stage.exists():
        expected = {name: entry for artifact in manifest['artifacts'] for name, entry in artifact['files'].items()}
        actual = tree_inventory(stage)
        if actual != {name: entry['sha256'] for name, entry in expected.items()}:
            raise ValueError('Previously extracted stage changed; use a new --work-dir')
    else:
        unpacked = sum(artifact['unpacked_bytes'] for artifact in manifest['artifacts'])
        if shutil.disk_usage(work).free < unpacked + 32 * 1024 ** 2:
            raise ValueError('Insufficient disk space for release extraction')
        verify_release(cache, pin, stage)
    catalog_data(stage / 'data')
    if not (stage / 'module/registration.php').is_file():
        raise ValueError('Release has no portable catalog module')
    return pin, manifest, stage


class Runtime:
    def __init__(self, args):
        self.args = args
        self.root = args.magento_root
        self.runtime_root = args.runtime_root or str(self.root)
        self.php = json.loads(args.php_command)
        if not isinstance(self.php, list) or not self.php or not all(isinstance(item, str) and item for item in self.php):
            raise ValueError('--php-command must be a JSON array of executable arguments')
        self.program = __loader__.get_data(str(Path(__file__).parent / 'catalog_runtime.php')).decode().removeprefix('<?php')

    def path(self, path):
        relative = Path(path).relative_to(self.root).as_posix()
        return self.runtime_root.rstrip('/') + '/' + relative

    def request(self, action, **kwargs):
        result = subprocess.run([*self.php, '-d', 'memory_limit=4G', '-d', 'display_errors=0', '-d', 'xdebug.mode=off', '-r', self.program], cwd=self.root,
                                input=encoded({'action': action, 'root': self.runtime_root, **kwargs}),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            # Runtime deliberately returns only sanitized errors, never DB credentials.
            raise RuntimeError(result.stdout.decode(errors='replace').strip() or 'Runtime failed; inspect the protected log')
        try:
            return json.loads(result.stdout)
        except ValueError as error:
            raise RuntimeError('Runtime did not return a clean JSON result') from error

    def check_mount(self):
        directory = self.root / 'var/wands-installer'
        with tempfile.NamedTemporaryFile(prefix='mount-probe-', dir=directory) as probe:
            value = secrets.token_bytes(32)
            probe.write(value)
            probe.flush()
            result = self.request('probe', path=self.path(Path(probe.name)), sha256=hashlib.sha256(value).hexdigest())
            if result.get('passed') is not True:
                raise ValueError('Host and PHP runtime paths do not share the same store files')

    def magento(self, receipt, *arguments):
        print('Running ' + ' '.join(arguments[:1]), flush=True)
        with (receipt / 'magento.log').open('ab') as log:
            os.chmod(receipt / 'magento.log', 0o600)
            result = subprocess.run([*self.php, self.runtime_root.rstrip('/') + '/bin/magento', *arguments],
                                    cwd=self.root, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError('Magento command failed; see ' + str(receipt / 'magento.log'))


def check_platform(snapshot, allow_unverified=False):
    php_supported = snapshot['php'].startswith('8.4.')
    tested = snapshot['version'] in SUPPORTED_VERSIONS.get(snapshot['edition'], set()) and php_supported
    candidate = snapshot['version'] in CANDIDATE_VERSIONS.get(snapshot['edition'], set()) and php_supported
    if not tested and not (candidate and allow_unverified):
        raise ValueError('Platform not qualified: ' + snapshot['edition'] + ' ' + snapshot['version']
                         + ' / PHP ' + snapshot['php'] + '. Add a version only after isolated runtime qualification.')
    return 'Native fixture acceptance: install, adopt, update, reset and restore' if tested else 'unverified platform candidate'


def build_plan(args, runtime, pin, stage, delta_dir):
    snapshot = runtime.request('inspect')
    qualification = check_platform(snapshot, args.allow_unverified_platform)
    current = args.magento_root / 'var/wands-installer/current'
    baseline = json.loads((current / 'receipt.json').read_bytes()) if (current / 'receipt.json').is_file() else None
    _, products, _, _ = catalog_data(stage / 'data')
    file_backup_bytes = sum(path.stat().st_size for name in BACKUP_PATHS
                            for path in ([args.magento_root / name] if (args.magento_root / name).is_file()
                                         else (args.magento_root / name).rglob('*')) if path.is_file())
    incoming_bytes = sum(path.stat().st_size for path in stage.rglob('*') if path.is_file())
    # Reserve the apply backup and an inverse backup if recovery is needed.
    reserve = 3 * file_backup_bytes + 4 * incoming_bytes + 4 * snapshot.get('database_bytes', 0) + 64 * 1024 ** 2
    if args.apply and args.operation != 'adopt' and shutil.disk_usage(args.magento_root).free < reserve:
        raise ValueError('Insufficient disk reserve for backup, import and recovery: ' + str(reserve) + ' bytes')
    if snapshot.get('running_cron'):
        raise ValueError('Magento cron jobs are currently running; stop and drain them before planning')
    if snapshot.get('remote_storage'):
        raise ValueError('Remote media storage needs a separate backup adapter')
    if args.operation == 'install':
        if snapshot.get('catalog_products', 0) and not args.reset_existing_catalog:
            raise ValueError('Existing WANDS products detected. Use update/adopt, or explicitly select --reset-existing-catalog.')
        if snapshot['wands_collision'] and not args.reset_existing_catalog:
            raise ValueError('Existing WANDS website/store detected; use update/adopt or explicit reset.')
        if (args.magento_root / 'app/code/RocketWeb/LabCatalog').exists() and not args.reset_existing_catalog:
            raise ValueError('Existing catalog module detected; reset/adopt must be explicit')
        if args.reset_existing_catalog and not args.dedicated_test_installation:
            raise ValueError('Reset requires --dedicated-test-installation for the whole Magento installation')
        if args.reset_existing_catalog and snapshot.get('wands_structure_valid') is False:
            raise ValueError('Existing WANDS website/store codes have conflicting assignments; repair their hierarchy before resetting')
        delta = {'added_products': len(products), 'changed_products': 0,
                 'removed_products': snapshot['products'] if args.reset_existing_catalog else 0,
                 'removed_categories': snapshot['deletable_categories'] if args.reset_existing_catalog else 0,
                 'preserved_existing_products': 0 if args.reset_existing_catalog else snapshot['products']}
        delta['removed_reservations'] = snapshot.get('reservations', 0) if args.reset_existing_catalog else 0
    elif args.operation == 'adopt':
        runtime.request('verify', data=runtime.path(stage / 'data') if stage.is_relative_to(args.magento_root) else None,
                        expected=verification_payload(stage / 'data'), preserve_stock=True)
        delta = {'adopt_existing_products': len(products)}
    else:
        if not baseline:
            raise ValueError('No installer receipt. Adopt the exact installed release before updating.')
        if baseline['identity'] != snapshot['identity'] or baseline['catalog_sha256'] != snapshot['catalog_sha256']:
            raise ValueError('Installed catalog changed since its receipt. Local edits require review before update.')
        if baseline['module_sha256'] != tree_inventory(args.magento_root / 'app/code/RocketWeb/LabCatalog'):
            raise ValueError('Installed catalog module has local edits')
        if baseline['input_sha256'] != tree_inventory(current / 'data'):
            raise ValueError('Installed baseline inputs changed')
        if baseline['media_sha256'] != catalog_media_inventory(args.magento_root):
            raise ValueError('Installed product/download media has local edits')
        if baseline['manifest_sha256'] == pin:
            delta = {'added_products': 0, 'changed_products': 0, 'removed_products': 0, 'csv_files': [], 'csv_sha256': {}}
        else:
            delta = update_delta(current / 'data', stage / 'data', delta_dir)
            runtime.request('check-fields', expected=json.loads((delta_dir / 'before-values.json').read_bytes()),
                            media_sha256=baseline['release_media_sha256'])
            runtime.request('check-gallery', expected=json.loads((delta_dir / 'before-gallery.json').read_bytes()),
                            media_sha256=baseline['release_media_sha256'], guard_scopes=True)
    plan = {'schema': 1, 'operation': args.operation, 'target_root': str(args.magento_root),
            'target_identity': snapshot['identity'], 'database': snapshot['database'],
            'websites': snapshot['websites'], 'edition': snapshot['edition'], 'version': snapshot['version'],
            'php': snapshot['php'], 'qualification': qualification,
            'mode': snapshot['mode'], 'existing_test_records': snapshot.get('test_records', {}),
            'release': args.tag, 'profile': args.profile, 'manifest_sha256': pin,
            'reset_existing_catalog': args.reset_existing_catalog, 'before_catalog_sha256': snapshot['catalog_sha256'],
            'base_url': args.base_url, 'locales': args.locales,
            'make_wands_default': args.operation == 'install' and not args.keep_default_website,
            'existing_products': snapshot['products'], 'existing_categories': snapshot['categories'],
            'retained_category_roots': snapshot['retained_category_roots'], 'changes': delta,
            'module_sha256': tree_inventory(stage / 'module'),
            'composer_lock_sha256': digest(args.magento_root / 'composer.lock') if (args.magento_root / 'composer.lock').is_file() else None,
            'previous_release': baseline['release'] if baseline else None,
            'stage_sha256': hashlib.sha256(encoded(tree_inventory(stage))).hexdigest()}
    token = ('RESET' if args.reset_existing_catalog else args.operation.upper()) + ':' + hashlib.sha256(encoded(plan)).hexdigest()[:20]
    plan['confirmation'] = token
    plan['estimated_disk_reserve_bytes'] = reserve
    return plan, snapshot


def verification_payload(data):
    _, products, effective, _ = catalog_data(data)
    # Core persisted values and complete SKU/type/relationship inventory; no stock changes on updates.
    keys = ('name', 'price', 'special_price', 'product_online', 'base_image', 'small_image', 'thumbnail_image', 'swatch_image', 'additional_images',
            'configurable_variations', 'bundle_values', 'associated_skus', 'categories')
    images = {}
    for row in effective.values():
        for name in image_names(row):
            if name not in images:
                images[name] = digest(data.parent / 'media' / name)
    return {'counts': json.loads((data / 'counts.json').read_bytes()), 'image_sha256': images,
            'products': {sku: {'product_type': kind, **{key: effective[sku][key] for key in keys if key in effective[sku]}}
                         for sku, kind in products.items()}}


def save_baseline(root, plan, snapshot, stage):
    current = root / 'var/wands-installer/current'
    if current.exists():
        shutil.rmtree(current)
    current.mkdir(mode=0o700)
    shutil.copytree(stage / 'data', current / 'data')
    write_json(current / 'receipt.json', {'schema': 1, 'release': plan['release'], 'profile': plan['profile'],
        'manifest_sha256': plan['manifest_sha256'], 'identity': snapshot['identity'],
        'catalog_sha256': snapshot['catalog_sha256'],
        'module_sha256': tree_inventory(root / 'app/code/RocketWeb/LabCatalog'),
        'media_sha256': catalog_media_inventory(root),
        'release_media_sha256': tree_inventory(stage / 'media'),
        'input_sha256': tree_inventory(current / 'data')})


def backup_files(root, receipt):
    inventories = {name: tree_inventory(root / name) for name in BACKUP_PATHS}
    with tarfile.open(receipt / 'files.tar', 'w') as archive:
        for name, inventory in inventories.items():
            path = root / name
            if path.exists():
                archive.add(path, arcname=name, recursive=True)
    expected = {name if file == '.' else name + '/' + file: sha
                for name, inventory in inventories.items() for file, sha in inventory.items()}
    actual = {}
    with tarfile.open(receipt / 'files.tar', 'r:') as archive:
        for member in archive:
            safe_path(member.name)
            if member.isfile():
                with archive.extractfile(member) as stream:
                    actual[member.name] = hashlib.file_digest(stream, 'sha256').hexdigest()
            elif not member.isdir():
                raise ValueError('Backup contains a nonregular member')
    if actual != expected:
        raise ValueError('Files changed while preparing the backup')
    # Include existence independently from an empty directory's file inventory.
    return {'file_sha256': digest(receipt / 'files.tar'), 'file_inventory': inventories,
            'existing_paths': [name for name in BACKUP_PATHS if (root / name).exists()]}


def copy_verified_tree(source, destination):
    inventory = tree_inventory(source)
    destination.mkdir(parents=True, exist_ok=True)
    for name, sha in inventory.items():
        target = destination / name
        if any(parent.is_symlink() for parent in (target, *target.parents)):
            raise ValueError('Destination symlink refused: ' + str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or digest(target) != sha:
            shutil.copyfile(source / name, target)
        if digest(target) != sha:
            raise ValueError('Copied file failed verification: ' + name)


@contextmanager
def installation_lock(root):
    directory = root / 'var/wands-installer'
    if directory.is_symlink():
        raise ValueError('Installer state cannot be symlinked')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    if (directory / 'lock').is_symlink():
        raise ValueError('Installer lock cannot be symlinked')
    with (directory / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('Another catalog operation holds this installation lock') from error
        yield


def apply(args, runtime, plan, snapshot, stage, delta_dir):
    if not args.jobs_stopped:
        raise ValueError('--jobs-stopped is required after stopping cron, consumers and other catalog writers')
    receipt = args.magento_root / 'var/wands-installer' / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + plan['confirmation'].split(':')[1])
    receipt.mkdir(mode=0o700)
    write_json(receipt / 'plan.json', plan)
    write_json(receipt / 'status.json', {'state': 'backing-up'})
    if args.operation == 'adopt':
        confirmation = args.confirm or input('Type ' + plan['confirmation'] + ' to register this baseline: ')
        if confirmation != plan['confirmation']:
            raise ValueError('Confirmation does not match this exact plan')
        if runtime.request('inspect') != snapshot:
            raise ValueError('Destination changed after planning')
        save_baseline(args.magento_root, plan, snapshot, stage)
        write_json(receipt / 'status.json', {'state': 'adopted'})
        return receipt
    if not snapshot['maintenance']:
        runtime.magento(receipt, 'maintenance:enable')
    started = False
    try:
        if runtime.request('inspect')['catalog_sha256'] != snapshot['catalog_sha256']:
            raise ValueError('Destination changed before backup')
        info = backup_files(args.magento_root, receipt)
        database = runtime.request('backup', destination=runtime.path(receipt / 'database.sql'), binary=args.db_dump,
                                   container=args.db_container)
        info.update(database)
        info['identity'] = snapshot['identity']
        info['maintenance_before'] = snapshot['maintenance']
        write_json(receipt / 'backup.json', info)
        print('Backup prepared: ' + str(receipt), flush=True)
        confirmation = args.confirm or input('Type ' + plan['confirmation'] + ' to apply this exact plan: ')
        if confirmation != plan['confirmation']:
            raise ValueError('Confirmation does not match this exact plan')
        live = runtime.request('inspect')
        if live['identity'] != snapshot['identity'] or live['catalog_sha256'] != snapshot['catalog_sha256'] or live['running_cron']:
            raise ValueError('Destination changed after backup; create a new plan')
        if hashlib.sha256(encoded(tree_inventory(stage))).hexdigest() != plan['stage_sha256']:
            raise ValueError('Verified release stage changed after planning')
        for name, inventory in info['file_inventory'].items():
            if tree_inventory(args.magento_root / name) != inventory:
                raise ValueError('Destination files changed after backup: ' + name)
        if args.operation == 'update' and plan['changes']['csv_files']:
            for name, sha in plan['changes']['csv_sha256'].items():
                if digest(delta_dir / name) != sha:
                    raise ValueError('Planned update CSV changed')
            if digest(delta_dir / 'before-gallery.json') != plan['changes']['gallery_checks_sha256']:
                raise ValueError('Planned gallery update changed')
        started = True
        preserved_before = None
        if not args.reset_existing_catalog:
            preserved_before = runtime.request('preserved')
            write_json(receipt / 'preserved-before.json', preserved_before)
        stock_before = None
        if args.operation == 'update':
            existing = list(catalog_data(args.magento_root / 'var/wands-installer/current/data')[1])
            stock_before = runtime.request('stock', skus=existing)
            write_json(receipt / 'stock-before.json', stock_before)
        write_json(receipt / 'status.json', {'state': 'applying', 'restore_required_on_failure': True})
        if args.reset_existing_catalog:
            runtime.request('reset', expected_fingerprint=snapshot['catalog_sha256'], identity=snapshot['identity'],
                            expected_reservations=snapshot.get('reservations', 0))
        module = args.magento_root / 'app/code/RocketWeb/LabCatalog'
        if module.exists():
            shutil.rmtree(module)
        copy_verified_tree(stage / 'module', module)
        runtime.magento(receipt, 'module:enable', 'RocketWeb_LabCatalog')
        runtime.magento(receipt, 'setup:upgrade')
        runtime.magento(receipt, 'lab:wands:provision', '--base-url=' + args.base_url)
        if plan['make_wands_default']:
            runtime.request('activate')
        data = args.magento_root / 'var/wands-lab/data'
        if data.exists():
            shutil.rmtree(data)
        copy_verified_tree(stage / 'data', data)
        copy_verified_tree(stage / 'media', args.magento_root / 'pub/media/import')
        if args.operation == 'update':
            inputs = receipt / 'delta'
            if plan['changes']['csv_files']:
                copy_verified_tree(delta_dir, inputs)
            files = [inputs / name for name in plan['changes']['csv_files']]
            if plan['changes'].get('gallery_reset_products'):
                runtime.request('clear-gallery', skus=list(json.loads((inputs / 'before-gallery.json').read_bytes())))
        else:
            files = [data / (phase + '.csv') for phase in PHASES if read_rows(data / (phase + '.csv'))]
        for file in files:
            if file.name.endswith('6-qa.csv') and args.operation == 'install':
                runtime.magento(receipt, 'lab:wands:curate-navigation')
            command = ['lab:wands:import', '--file=' + runtime.path(file)]
            if args.operation == 'update':
                command.append('--preserve-existing-stock')
            runtime.magento(receipt, *command)
        if args.operation == 'install' and not (data / '6-qa.csv').exists():
            runtime.magento(receipt, 'lab:wands:curate-navigation')
        if snapshot['mode'] == 'production':
            runtime.magento(receipt, 'setup:di:compile')
            runtime.magento(receipt, 'setup:static-content:deploy', '-f', *args.locales)
        runtime.magento(receipt, 'indexer:reindex')
        runtime.magento(receipt, 'cache:clean')
        result = runtime.request('verify', expected=verification_payload(stage / 'data'), preserve_stock=args.operation == 'update')
        if stock_before is not None:
            stock_after = runtime.request('stock', skus=existing)
            write_json(receipt / 'stock-after.json', stock_after)
            if stock_before != stock_after:
                raise ValueError('Existing stock/reservations changed during update; restore the backup')
            result['existing_stock_preserved'] = True
        if preserved_before is not None:
            preserved_after = runtime.request('preserved')
            write_json(receipt / 'preserved-after.json', preserved_after)
            if preserved_before != preserved_after:
                raise ValueError('Existing products or categories outside WANDS changed; restore the backup')
            result['existing_catalog_preserved'] = True
        write_json(receipt / 'verification.json', result)
        after = runtime.request('inspect')
        save_baseline(args.magento_root, plan, after, stage)
        write_json(receipt / 'status.json', {'state': 'verified', 'release': args.tag})
        if not snapshot['maintenance']:
            runtime.magento(receipt, 'maintenance:disable')
    except BaseException:
        write_json(receipt / 'status.json', {'state': 'failed', 'restore_required': started})
        if not started and not snapshot['maintenance']:
            runtime.magento(receipt, 'maintenance:disable')
        if started:
            print('Stopped. Maintenance remains enabled. Restore using --receipt ' + str(receipt), file=sys.stderr)
        raise
    return receipt


def restore(args, runtime):
    receipt = args.receipt.resolve()
    state_root = args.magento_root / 'var/wands-installer'
    if not receipt.is_relative_to(state_root) or receipt == state_root:
        raise ValueError('Receipt must belong to this installation')
    info = json.loads((receipt / 'backup.json').read_bytes())
    plan = json.loads((receipt / 'plan.json').read_bytes())
    live = runtime.request('inspect')
    current_lock = digest(args.magento_root / 'composer.lock') if (args.magento_root / 'composer.lock').is_file() else None
    if (live['edition'], live['version'], live['php'].split('.')[:2]) != (plan['edition'], plan['version'], plan['php'].split('.')[:2]):
        raise ValueError('Restore requires the original platform version and PHP family')
    if 'composer_lock_sha256' in plan and current_lock != plan['composer_lock_sha256']:
        raise ValueError('Composer dependencies changed since the backup; restore the matching runtime first')
    if live['identity'] != info['identity'] or digest(receipt / 'files.tar') != info['file_sha256'] or digest(receipt / 'database.sql') != info['database_sha256']:
        raise ValueError('Backup identity/checksum mismatch')
    current_file_bytes = sum(path.stat().st_size for name in info['file_inventory']
                             for path in ([args.magento_root / name] if (args.magento_root / name).is_file()
                                          else (args.magento_root / name).rglob('*')) if path.is_file())
    reserve = current_file_bytes + (receipt / 'files.tar').stat().st_size + 2 * live.get('database_bytes', 0) + 64 * 1024 ** 2
    if args.apply and shutil.disk_usage(args.magento_root).free < reserve:
        raise ValueError('Insufficient disk reserve for an inverse recovery backup: ' + str(reserve) + ' bytes')
    token = 'RESTORE:' + hashlib.sha256(encoded({'backup': info, 'identity': live['identity'],
        'catalog_sha256': live['catalog_sha256'], 'test_records': live.get('test_records', {})})).hexdigest()[:20]
    print(json.dumps({'restore_receipt': str(receipt), 'target_root': str(args.magento_root),
                      'current_products': live['products'], 'restore_products': plan['existing_products'],
                      'database': live['database'], 'current_categories': live['categories'],
                      'restore_categories': plan['existing_categories'], 'current_test_records': live.get('test_records', {}),
                      'restore_test_records': plan.get('existing_test_records', {}), 'restore_scope': 'Complete database and recorded file trees',
                      'restore_release': plan.get('previous_release'), 'restore_catalog_sha256': plan['before_catalog_sha256'],
                      'confirmation': token}, indent=2))
    if not args.apply:
        return
    if not args.jobs_stopped or (args.confirm or input('Type ' + token + ' to restore: ')) != token:
        raise ValueError('Restore requires stopped writers and exact confirmation')
    runtime.magento(receipt, 'maintenance:enable')
    fresh = runtime.request('inspect')
    if fresh['catalog_sha256'] != live['catalog_sha256'] or fresh['identity'] != live['identity'] or fresh['running_cron']:
        raise ValueError('Destination changed after restore planning')
    # Prepare a normal restore receipt for the current state before changing it.
    quarantine = receipt / ('quarantine-' + str(time.time_ns()))
    quarantine.mkdir(mode=0o700)
    inverse = backup_files(args.magento_root, quarantine)
    inverse.update(runtime.request('backup', destination=runtime.path(quarantine / 'database.sql'),
                                   binary=args.db_dump, container=args.db_container))
    inverse.update(identity=live['identity'], maintenance_before=live['maintenance'])
    inverse_plan = {**plan, 'operation': 'restore', 'before_catalog_sha256': live['catalog_sha256'],
                    'existing_products': live['products'], 'existing_categories': live['categories'],
                    'existing_test_records': live.get('test_records', {}), 'previous_release': None}
    write_json(quarantine / 'backup.json', inverse)
    write_json(quarantine / 'plan.json', inverse_plan)
    write_json(quarantine / 'status.json', {'state': 'inverse-backup-prepared'})
    print('Inverse recovery receipt: ' + str(quarantine), flush=True)
    with tarfile.open(receipt / 'files.tar', 'r:') as archive:
        members = archive.getmembers()
        for member in members:
            safe_path(member.name)
            if not (member.isfile() or member.isdir()) or not any(member.name == name or member.name.startswith(name + '/') for name in BACKUP_PATHS):
                raise ValueError('Unsafe backup member')
        for name in info['file_inventory']:
            if name not in BACKUP_PATHS:
                raise ValueError('Backup scope contains an unsupported path')
            target = args.magento_root / name
            if target.exists():
                saved = quarantine / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                target.rename(saved)
        for member in members:
            target = args.magento_root / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.isdir():
                target.mkdir(exist_ok=True)
            else:
                with archive.extractfile(member) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                os.chmod(target, member.mode & 0o777)
    runtime.request('restore', source=runtime.path(receipt / 'database.sql'), binary=args.db_client,
                    container=args.db_container)
    for name in ('generated/code', 'generated/metadata', 'var/cache', 'var/page_cache'):
        target = args.magento_root / name
        if target.is_symlink():
            raise ValueError('Recovery cache path cannot be symlinked: ' + name)
        if target.exists():
            saved = quarantine / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            target.rename(saved)
    after = runtime.request('inspect')
    if after['catalog_sha256'] != plan['before_catalog_sha256']:
        raise ValueError('Restored database differs from the original catalog snapshot; maintenance remains enabled')
    for name, inventory in info['file_inventory'].items():
        if tree_inventory(args.magento_root / name) != inventory:
            raise ValueError('Restored files failed verification: ' + name)
    runtime.magento(receipt, 'cache:clean')
    if plan.get('mode') == 'production':
        runtime.magento(receipt, 'setup:di:compile')
        runtime.magento(receipt, 'setup:static-content:deploy', '-f', *plan['locales'])
    runtime.magento(receipt, 'indexer:reindex')
    if not info['maintenance_before']:
        runtime.magento(receipt, 'maintenance:disable')
    write_json(receipt / 'status.json', {'state': 'restored', 'quarantine': str(quarantine)})


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('operation', choices=('install', 'update', 'adopt', 'restore'))
    result.add_argument('--magento-root', type=Path, required=True)
    result.add_argument('--runtime-root', help='Corresponding Magento root inside a container')
    result.add_argument('--php-command', default='["php"]', help='JSON argv prefix, e.g. ["ddev","exec","php"]')
    result.add_argument('--tag', default=DEFAULT_TAG)
    result.add_argument('--profile', choices=('starter', 'medium', 'full'), default='full')
    result.add_argument('--manifest-sha256')
    result.add_argument('--release-dir', type=Path, help='Offline directory containing the pinned manifest and archives')
    result.add_argument('--work-dir', type=Path, help='Download/staging directory outside the Magento root')
    result.add_argument('--base-url', help='Explicit WANDS storefront URL')
    result.add_argument('--keep-default-website', action='store_true', help='Keep existing default website; route your server explicitly to wands')
    result.add_argument('--apply', action='store_true', help='Back up, confirm and apply; default only prints the plan')
    result.add_argument('--confirm', help='Exact confirmation token from the current plan, for unattended operation')
    result.add_argument('--json-plan', action='store_true', help='Print the complete plan as JSON for review or automation')
    result.add_argument('--jobs-stopped', action='store_true', help='Assert cron, consumers and other catalog writers are stopped')
    result.add_argument('--reset-existing-catalog', action='store_true')
    result.add_argument('--dedicated-test-installation', action='store_true')
    result.add_argument('--allow-unverified-platform', action='store_true', help='Allow an explicitly registered candidate during maintainer qualification')
    result.add_argument('--db-dump', default='mysqldump', help='Database dump executable inside the PHP runtime')
    result.add_argument('--db-client', default='mysql', help='Database restore executable inside the PHP runtime')
    result.add_argument('--db-container', help='Optional local DB container; its published port must match env.php')
    result.add_argument('--locales', nargs='+', default=['en_US'])
    result.add_argument('--receipt', type=Path, help='Protected installation receipt to restore')
    return result


def show_plan(plan, machine=False):
    if machine:
        print(json.dumps(plan, indent=2), flush=True)
        return
    print('Target: ' + plan['target_root'] + ' (database: ' + plan['database'] + ')')
    print('Platform: ' + plan['edition'] + ' ' + plan['version'] + ' / PHP ' + plan['php'])
    print('Catalog: ' + plan['release'] + ' / ' + plan['profile'])
    print('Existing: ' + str(plan['existing_products']) + ' products, ' + str(plan['existing_categories']) + ' categories')
    changes = plan['changes']
    if plan['reset_existing_catalog']:
        print('RESET: delete ' + str(changes['removed_products']) + ' products, ' + str(changes['removed_categories'])
              + ' categories and ' + str(changes['removed_reservations']) + ' inventory reservations')
        print('Retain category roots: ' + ', '.join(map(str, plan['retained_category_roots'])))
    else:
        print('Changes: ' + str(changes.get('added_products', 0)) + ' added, ' + str(changes.get('changed_products', 0))
              + ' updated, ' + str(changes.get('gallery_reset_products', 0)) + ' galleries replaced')
        if 'preserved_existing_products' in changes:
            print('Preserve existing catalog: ' + str(changes['preserved_existing_products']) + ' products and its categories')
    if plan['make_wands_default']:
        print('WANDS becomes the default website at ' + plan['base_url'])
    print('Disk reserve: ' + format(plan['estimated_disk_reserve_bytes'] / 1024 ** 3, '.2f') + ' GiB')
    print('Confirmation: ' + plan['confirmation'], flush=True)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        args.magento_root = args.magento_root.resolve(strict=True)
        args.work_dir = (args.work_dir or args.magento_root.parent / ('.wands-download-' + args.magento_root.name)).resolve()
        if not (args.magento_root / 'app/bootstrap.php').is_file():
            raise ValueError('Target is not an installed Magento/Mage-OS root')
        if args.reset_existing_catalog and args.operation != 'install':
            raise ValueError('Reset is available only with install')
        if args.operation == 'restore' and not args.receipt:
            raise ValueError('Restore requires --receipt')
        if args.operation in ('install', 'update') and not args.base_url:
            raise ValueError('--base-url is required for the catalog storefront')
        if args.base_url:
            url = urlsplit(args.base_url)
            if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment or any(c.isspace() for c in args.base_url):
                raise ValueError('Use an HTTP(S) base URL without credentials, query or fragment')
        validate_destination(args.magento_root)
        runtime = Runtime(args)
        with installation_lock(args.magento_root):
            runtime.check_mount()
            if args.operation == 'restore':
                restore(args, runtime)
                return 0
            pin, manifest, stage = prepare_release(args)
            with tempfile.TemporaryDirectory(prefix='delta-', dir=args.work_dir) as temporary:
                delta = Path(temporary) / 'csv'
                plan, snapshot = build_plan(args, runtime, pin, stage, delta)
                show_plan(plan, args.json_plan)
                if args.apply:
                    if args.operation == 'update' and plan['manifest_sha256'] == json.loads((args.magento_root / 'var/wands-installer/current/receipt.json').read_bytes())['manifest_sha256']:
                        print('This exact catalog release is already installed; no update is needed.')
                        return 0
                    receipt = apply(args, runtime, plan, snapshot, stage, delta)
                    print('Verified receipt: ' + str(receipt), flush=True)
                else:
                    print('Preview only. Stop catalog writers, then add --apply --jobs-stopped to proceed.', file=sys.stderr)
    except (Exception, KeyboardInterrupt) as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        return 130 if isinstance(error, KeyboardInterrupt) else 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
