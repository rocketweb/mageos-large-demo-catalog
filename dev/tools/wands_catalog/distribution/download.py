"""Fetch a pinned WANDS release into a local cache; never install or execute it."""
import argparse
import fcntl
import hashlib
from http.client import HTTPException
import json
import logging
from pathlib import Path
import re
import shutil
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request
import uuid

from release import digest, verify_release

MANIFEST_LIMIT = 32 * 1024 * 1024
CHUNK = 1024 * 1024


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect refused; use a direct HTTPS mirror URL')


def validate_base_url(value):
    if any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise ValueError('Invalid download URL')
    url = urlsplit(value)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment or '%' in url.path or '\\' in value
            or any(part in ('.', '..') for part in url.path.split('/'))):
        raise ValueError('Use a direct HTTPS directory URL without credentials, query or fragment')
    return value.rstrip('/') + '/'


def regular_or_absent(path):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('Cache entry is not a regular file')


def quarantine(path):
    path.rename(path.with_name(path.name + '.rejected-' + uuid.uuid4().hex))
    logging.warning('Quarantined corrupt cache entry: %s', path.name)


def download_file(url, path, size, expected_sha256, *, opener=None, attempts=3, timeout=30):
    """Only promote complete, pinned bytes. Keep interrupted partials for a rerun."""
    path = Path(path)
    partial = path.with_name(path.name + '.part')
    regular_or_absent(path)
    regular_or_absent(partial)
    if path.exists():
        if path.stat().st_size == size and digest(path) == expected_sha256:
            logging.info('Cached and verified %s', path.name)
            return
        quarantine(path)
    opener = opener or build_opener(NoRedirects()).open
    for attempt in range(attempts):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            if offset >= size and partial.exists():
                if offset == size and digest(partial) == expected_sha256:
                    partial.replace(path)
                    return
                quarantine(partial)
                offset = 0
            headers = {'Accept-Encoding': 'identity', 'User-Agent': 'WANDS-Lab-Downloader/1'}
            if offset:
                headers['Range'] = f'bytes={offset}-'
            with opener(Request(url, headers=headers), timeout=timeout) as response:
                if response.headers.get('Content-Encoding', 'identity') != 'identity':
                    raise ValueError('Encoded response refused')
                if response.status == 206:
                    if response.headers.get('Content-Range') != f'bytes {offset}-{size - 1}/{size}':
                        raise ValueError('Invalid range response')
                elif response.status == 200:
                    offset = 0  # A mirror may ignore Range; restart, never append a full response.
                else:
                    raise ValueError('Unexpected HTTP status')
                length = response.headers.get('Content-Length')
                if length is not None and int(length) != size - offset:
                    raise ValueError('Response size differs from pinned manifest')
                logging.info('Downloading %s from byte %d of %d', path.name, offset, size)
                checkpoint = offset
                with partial.open('ab' if offset else 'wb') as output:
                    while block := response.read(min(CHUNK, size - offset + 1)):
                        if offset + len(block) > size:
                            raise ValueError('Response exceeds pinned size')
                        output.write(block)
                        offset += len(block)
                        if offset - checkpoint >= 64 * CHUNK:
                            logging.info('%s: %d / %d bytes', path.name, offset, size)
                            checkpoint = offset
                if offset != size:
                    raise EOFError('Interrupted response')
            if digest(partial) != expected_sha256:
                quarantine(partial)
                raise ValueError('Artifact checksum mismatch')
            partial.replace(path)
            logging.info('Downloaded and verified %s: %d bytes', path.name, size)
            return
        except (OSError, ValueError, EOFError, HTTPException) as error:
            # Never log server-controlled text or URLs, including query credentials.
            logging.warning('%s attempt %d/%d failed (%s)', path.name, attempt + 1, attempts, type(error).__name__)
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 4))
    raise RuntimeError('Download attempts exhausted; rerun to resume partial files')


def read_manifest(url, path, pin, opener, attempts, timeout):
    regular_or_absent(path)
    if path.exists():
        if path.stat().st_size > MANIFEST_LIMIT or digest(path) != pin:
            raise ValueError('Cached manifest does not match trusted pin')
        return json.loads(path.read_bytes())
    for attempt in range(attempts):
        try:
            with opener(Request(url, headers={'Accept-Encoding': 'identity'}), timeout=timeout) as response:
                if response.status != 200:
                    raise ValueError('Unexpected manifest response')
                data = response.read(MANIFEST_LIMIT + 1)
            if len(data) > MANIFEST_LIMIT or hashlib.sha256(data).hexdigest() != pin:
                raise ValueError('Manifest does not match trusted pin or size limit')
            manifest = json.loads(data)
            with path.open('xb') as stream:
                stream.write(data)
            return manifest
        except (OSError, HTTPException):
            logging.warning('Manifest transfer attempt %d/%d failed', attempt + 1, attempts)
            if attempt + 1 == attempts:
                raise RuntimeError('Manifest download attempts exhausted') from None
            time.sleep(min(2 ** attempt, 4))


def fetch_release(base_url, cache_dir, pin, *, opener=None, attempts=3, timeout=30):
    base_url = validate_base_url(base_url)
    if not re.fullmatch('[0-9a-f]{64}', pin):
        raise ValueError('Expected a lowercase SHA-256 manifest pin')
    if not 1 <= attempts <= 5 or not 1 <= timeout <= 60:
        raise ValueError('Attempts must be 1..5 and timeout 1..60 seconds')
    if Path(cache_dir).is_symlink():
        raise ValueError('Cache directory cannot be a symlink')
    root = Path(cache_dir).resolve() / pin
    if root.is_symlink():
        raise ValueError('Release cache directory cannot be a symlink')
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / '.download.lock'
    regular_or_absent(lock_path)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        opener = opener or build_opener(NoRedirects()).open
        manifest = read_manifest(base_url + 'manifest.json', root / 'manifest.json', pin, opener, attempts, timeout)
        if manifest.get('schema') != 1 or not isinstance(manifest.get('artifacts'), list) or not manifest['artifacts']:
            raise ValueError('Unsupported or empty manifest')
        names = set()
        remaining = 0
        for artifact in manifest['artifacts']:
            name, size, checksum = artifact['path'], artifact['bytes'], artifact['sha256']
            if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*\.tar', name)
                    or name in names or type(size) is not int or size <= 0
                    or not isinstance(checksum, str) or not re.fullmatch('[0-9a-f]{64}', checksum)):
                raise ValueError('Invalid or duplicate artifact declaration')
            names.add(name)
            path = root / name
            regular_or_absent(path)
            if not path.exists() or path.stat().st_size != size or digest(path) != checksum:
                remaining += size  # Conservative: allow a full replacement, even when partial exists.
        if shutil.disk_usage(root).free < remaining + MANIFEST_LIMIT:
            raise ValueError('Insufficient cache disk space')
        for artifact in manifest['artifacts']:
            download_file(base_url + artifact['path'], root / artifact['path'], artifact['bytes'], artifact['sha256'],
                          opener=opener, attempts=attempts, timeout=timeout)
        result = verify_release(root, pin)
        logging.info('COMPLETE directory=%s result=%s', root, json.dumps(result, sort_keys=True))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--log-file', type=Path, default=Path('wands-download.log'))
    parser.add_argument('--attempts', type=int, default=3)
    parser.add_argument('--timeout', type=int, default=30)
    args = parser.parse_args()
    logging.basicConfig(filename=args.log_file, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        fetch_release(args.base_url, args.cache_dir, args.manifest_sha256, attempts=args.attempts, timeout=args.timeout)
    except KeyboardInterrupt:
        logging.info('Interrupted; rerun the same command to resume')
        return 130
    except Exception as error:
        logging.error('Download failed (%s). Check pin, direct HTTPS URL, cache paths and space; rerun to retry.', type(error).__name__)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
