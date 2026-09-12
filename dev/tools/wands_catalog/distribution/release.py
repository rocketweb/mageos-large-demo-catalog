"""Offline, standard-library verifier and deterministic archive primitives.

No network access, Magento writes, shell execution or model dependencies.
"""
import argparse
import hashlib
import io
import json
import logging
from pathlib import Path, PurePosixPath
import shutil
import tarfile


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_path(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError(f'Unsafe relative path: {value!r}')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ('', '.', '..') for part in value.split('/')) or ':' in value:
        raise ValueError(f'Unsafe relative path: {value!r}')
    return path


def dependencies(row):
    key = {'configurable': 'configurable_variations', 'bundle': 'bundle_values'}.get(row.get('product_type'))
    if not key:
        return set()
    result = set()
    for group in row.get(key, '').split('|'):
        if not group:
            continue
        fields = dict(field.split('=', 1) for field in group.split(',') if '=' in field)
        if not fields.get('sku'):
            raise ValueError(f'Missing dependency SKU in {key}')
        result.add(fields['sku'])
    if not result:
        raise ValueError(f'Missing dependency list: {row.get("sku")}')
    return result


def closure(rows, seeds):
    parents = {}
    for sku, row in rows.items():
        if row.get('product_type') == 'configurable':
            for child in dependencies(row):
                parents.setdefault(child, set()).add(sku)
    selected, pending = set(), set(seeds)
    while pending:
        sku = pending.pop()
        if sku in selected:
            continue
        if sku not in rows:
            raise ValueError(f'Missing dependency: {sku}')
        selected.add(sku)
        pending.update((dependencies(rows[sku]) | parents.get(sku, set())) - selected)
    return selected


def write_archive(path, files):
    path = Path(path)
    entries = {}
    for name, source in files.items():
        safe_path(name)
        if isinstance(source, Path) and (source.is_symlink() or not source.is_file()):
            raise ValueError(f'Not a regular source file: {name}')
    with path.open('xb') as output, tarfile.open(fileobj=output, mode='w') as archive:
        for name, source in sorted(files.items()):
            is_file = isinstance(source, Path)
            size = source.stat().st_size if is_file else len(source)
            sha = digest(source) if is_file else hashlib.sha256(source).hexdigest()
            member = tarfile.TarInfo(name)
            member.size, member.mode, member.mtime = size, 0o644, 0
            with source.open('rb') if is_file else io.BytesIO(source) as stream:
                archive.addfile(member, stream)
            entries[name] = {'bytes': size, 'sha256': sha}
    return {'path': path.name, 'bytes': path.stat().st_size, 'sha256': digest(path),
            'unpacked_bytes': sum(item['bytes'] for item in entries.values()), 'files': entries}


def verify_release(root, expected_manifest_sha256, extract=None):
    root = Path(root)
    if digest(root / 'manifest.json') != expected_manifest_sha256:
        raise ValueError('Release manifest checksum mismatch')
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest.get('schema') != 1 or not manifest.get('artifacts'):
        raise ValueError('Unsupported or empty release manifest')
    all_names, archive_names, total = set(), set(), 0
    for artifact in manifest['artifacts']:
        safe_path(artifact['path'])
        if artifact['path'] in archive_names:
            raise ValueError('Duplicate artifact')
        archive_names.add(artifact['path'])
        path = root / artifact['path']
        if path.is_symlink() or not path.is_file() or path.stat().st_size != artifact['bytes'] or digest(path) != artifact['sha256']:
            raise ValueError(f'Artifact checksum mismatch: {artifact["path"]}')
        declared = artifact['files']
        for name in declared:
            safe_path(name)
        seen, unpacked = set(), 0
        with tarfile.open(path, 'r:') as archive:
            for member in archive:
                safe_path(member.name)
                if not member.isfile() or member.name not in declared or member.name in seen or member.name in all_names:
                    raise ValueError(f'Invalid, duplicate or undeclared member: {member.name}')
                info = declared[member.name]
                unpacked += member.size
                if member.size != info['bytes'] or unpacked > artifact['unpacked_bytes']:
                    raise ValueError('Archive expansion exceeds manifest')
                with archive.extractfile(member) as stream:
                    sha = hashlib.file_digest(stream, 'sha256').hexdigest()
                if sha != info['sha256']:
                    raise ValueError(f'Member checksum mismatch: {member.name}')
                seen.add(member.name)
        if seen != set(declared) or unpacked != artifact['unpacked_bytes']:
            raise ValueError('Archive does not match declared inventory')
        all_names.update(seen)
        total += unpacked
        logging.info('Verified %s: %d files, %d bytes', path.name, len(seen), unpacked)
    if extract:
        destination = Path(extract)
        destination.mkdir(parents=True, exist_ok=False)
        for artifact in manifest['artifacts']:
            path = root / artifact['path']
            if digest(path) != artifact['sha256']:
                raise ValueError('Archive changed after verification')
            with tarfile.open(path, 'r:') as archive:
                for member in archive:
                    target = destination / member.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source, target.open('xb') as output:
                        shutil.copyfileobj(source, output)
        logging.info('Extracted to new directory %s', destination)
    return {'status': 'verified', 'artifacts': len(archive_names), 'files': len(all_names), 'unpacked_bytes': total}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--manifest-sha256', required=True, help='Pin received through a trusted channel')
    parser.add_argument('--extract', type=Path, help='Optional NEW staging directory; never a Magento root')
    parser.add_argument('--log-file', type=Path)
    args = parser.parse_args()
    log = args.log_file or args.directory / 'verification.log'
    logging.basicConfig(filename=log, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        result = verify_release(args.directory, args.manifest_sha256, args.extract)
        logging.info(json.dumps(result, sort_keys=True))
    except Exception:
        logging.exception('Release verification failed')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
