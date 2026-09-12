import hashlib
import io
import fcntl
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import ssl
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import build_opener, HTTPSHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'distribution'))
from download import fetch_release, download_file, validate_base_url, NoRedirects
from release import write_archive


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


class DownloadTest(unittest.TestCase):
    def test_resume_and_skip_verified_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.tar'
            path.with_suffix('.tar.part').write_bytes(b'abc')
            requests = []
            def opener(request, timeout):
                requests.append(request.get_header('Range'))
                return Response(b'def', 206, {'Content-Range': 'bytes 3-5/6'})
            download_file('https://example.test/catalog.tar', path, 6, sha(b'abcdef'), opener=opener)
            download_file('https://example.test/catalog.tar', path, 6, sha(b'abcdef'), opener=opener)
            self.assertEqual(requests, ['bytes=3-'])
            self.assertEqual(path.read_bytes(), b'abcdef')

    def test_server_without_ranges_restarts_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.tar'
            path.with_suffix('.tar.part').write_bytes(b'abc')
            download_file('https://example.test/a', path, 6, sha(b'abcdef'),
                          opener=lambda *a, **k: Response(b'abcdef'))
            self.assertEqual(path.read_bytes(), b'abcdef')

    def test_interruption_is_resumable_after_process_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.tar'
            with self.assertRaises(RuntimeError):
                download_file('https://example.test/a', path, 6, sha(b'abcdef'), attempts=1,
                              opener=lambda *a, **k: Response(b'abc'))
            self.assertFalse(path.exists())
            self.assertEqual(path.with_suffix('.tar.part').read_bytes(), b'abc')
            def opener(request, timeout):
                self.assertEqual(request.get_header('Range'), 'bytes=3-')
                return Response(b'def', 206, {'Content-Range': 'bytes 3-5/6'})
            download_file('https://example.test/a', path, 6, sha(b'abcdef'), opener=opener)
            self.assertEqual(path.read_bytes(), b'abcdef')

    def test_corruption_quarantined_and_retry_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.tar'
            with patch('download.time.sleep'), self.assertRaises(RuntimeError):
                download_file('https://example.test/a', path, 3, sha(b'abc'), attempts=2,
                              opener=lambda *a, **k: Response(b'BAD'))
            self.assertFalse(path.exists())
            self.assertEqual(len(list(path.parent.glob('*.rejected-*'))), 2)

    def test_bad_range_and_oversized_response_never_promoted(self):
        for response in [lambda: Response(b'def', 206, {'Content-Range': 'bytes 0-2/6'}),
                         lambda: Response(b'abcdefX')]:
            with self.subTest(response=response), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'catalog.tar'
                path.with_suffix('.tar.part').write_bytes(b'abc')
                with self.assertRaises(RuntimeError):
                    download_file('https://example.test/a', path, 6, sha(b'abcdef'), attempts=1,
                                  opener=lambda *a, **k: response())
                self.assertFalse(path.exists())
                self.assertLessEqual(path.with_suffix('.tar.part').stat().st_size, 6)

    def test_symlink_rejected_without_writing_target(self):
        for suffix in ['', '.part']:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / 'untouched'
                target.write_bytes(b'keep')
                path = root / 'catalog.tar'
                (root / ('catalog.tar' + suffix)).symlink_to(target)
                with self.assertRaises(ValueError):
                    download_file('https://example.test/a', path, 3, sha(b'abc'))
                self.assertEqual(target.read_bytes(), b'keep')

    def test_requires_plain_https_directory_url(self):
        for url in ['http://example.test/', 'file:///tmp/', 'https://user:secret@example.test/',
                    'https://example.test/?token=secret', 'https://example.test/#token',
                    'https://example.test/../escape', 'https://example.test/\n']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_base_url(url)
        self.assertEqual(validate_base_url('https://example.test/releases/rc2'),
                         'https://example.test/releases/rc2/')

    def test_full_release_pin_and_member_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = write_archive(root / 'catalog.tar', {'data/item.csv': b'sku\nexample\n'})
            manifest = json.dumps({'schema': 1, 'artifacts': [artifact]}).encode()
            responses = {'manifest.json': manifest, 'catalog.tar': (root / 'catalog.tar').read_bytes()}
            requests = []
            def opener(request, timeout):
                name = request.full_url.rsplit('/', 1)[1]
                requests.append(name)
                return Response(responses[name])
            result = fetch_release('https://example.test/rc2/', root / 'cache', sha(manifest), opener=opener)
            self.assertEqual(result['files'], 1)
            fetch_release('https://example.test/rc2/', root / 'cache', sha(manifest), opener=opener)
            self.assertEqual(requests, ['manifest.json', 'catalog.tar'])
            with self.assertRaises(ValueError):
                fetch_release('https://example.test/rc2/', root / 'bad', '0' * 64, opener=opener)
            self.assertFalse((root / 'bad' / ('0' * 64) / 'catalog.tar').exists())

    def test_unsafe_or_duplicate_artifact_refused_before_download(self):
        for names in [['../outside.tar'], ['catalog.tar', 'catalog.tar'], ['download.log']]:
            with tempfile.TemporaryDirectory() as directory:
                manifest = json.dumps({'schema': 1, 'artifacts': [
                    {'path': name, 'bytes': 3, 'sha256': sha(b'abc')} for name in names]}).encode()
                requests = []
                def opener(request, timeout):
                    requests.append(request.full_url)
                    return Response(manifest)
                with self.assertRaises(ValueError):
                    fetch_release('https://example.test/', Path(directory), sha(manifest), opener=opener)
                self.assertEqual(len(requests), 1)

    def test_cli_failure_is_quiet_and_logged_without_url_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'download.log'
            script = Path(__file__).resolve().parents[1] / 'distribution/download.py'
            result = subprocess.run([sys.executable, str(script), '--base-url',
                'https://user:SECRET@example.test/', '--cache-dir', directory,
                '--manifest-sha256', '0' * 64, '--log-file', str(log)], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout + result.stderr, b'')
            self.assertIn('failed', log.read_text())
            self.assertNotIn('SECRET', log.read_text())

    def test_redirects_refused_including_https_downgrade(self):
        for url in ['http://example.test/archive', 'https://another.test/archive']:
            with self.assertRaisesRegex(ValueError, 'Redirect'):
                NoRedirects().redirect_request(None, None, 302, '', {}, url)

    def test_concurrent_fetch_refused_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / ('0' * 64)
            root.mkdir()
            with (root / '.download.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    fetch_release('https://example.test/', directory, '0' * 64,
                                  opener=lambda *a, **k: self.fail('Network called while locked'))

    def test_insufficient_space_refused_before_artifacts(self):
        manifest = json.dumps({'schema': 1, 'artifacts': [
            {'path': 'catalog.tar', 'bytes': 3, 'sha256': sha(b'abc')}]}).encode()
        with tempfile.TemporaryDirectory() as directory, patch('download.shutil.disk_usage') as usage:
            usage.return_value.free = 0
            with self.assertRaisesRegex(ValueError, 'disk space'):
                fetch_release('https://example.test/', directory, sha(manifest),
                              opener=lambda *a, **k: Response(manifest))

    def test_manifest_size_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory, patch('download.MANIFEST_LIMIT', 8):
            with self.assertRaises(ValueError):
                fetch_release('https://example.test/', directory, sha(b'x' * 9),
                              opener=lambda *a, **k: Response(b'x' * 9))

    @unittest.skipUnless(os.environ.get('WANDS_TEST_HTTPS'), 'Set WANDS_TEST_HTTPS=1 for loopback TLS test')
    def test_real_https_interrupted_transfer_then_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = write_archive(root / 'catalog.tar', {'data/item.csv': b'sku\nexample\n'})
            manifest = json.dumps({'schema': 1, 'artifacts': [artifact]}).encode()
            payloads = {'/manifest.json': manifest, '/catalog.tar': (root / 'catalog.tar').read_bytes()}
            ranges = []
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_GET(self):
                    payload = payloads[self.path]
                    offset = int(self.headers.get('Range', 'bytes=0-')[6:-1])
                    if self.path == '/catalog.tar':
                        ranges.append(offset)
                    self.send_response(206 if offset else 200)
                    self.send_header('Content-Length', str(len(payload) - offset))
                    if offset:
                        self.send_header('Content-Range', f'bytes {offset}-{len(payload) - 1}/{len(payload)}')
                    self.end_headers()
                    # The first artifact connection closes before its promised body completes.
                    if self.path == '/catalog.tar' and len(ranges) == 1:
                        self.wfile.write(payload[:2048])
                        self.wfile.flush()
                        self.close_connection = True
                    else:
                        self.wfile.write(payload[offset:])
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                '-keyout', str(root / 'key.pem'), '-out', str(root / 'cert.pem'), '-days', '1',
                '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost'],
                check=True, capture_output=True)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(root / 'cert.pem', root / 'key.pem')
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            trusted = ssl.create_default_context(cafile=str(root / 'cert.pem'))
            opener = build_opener(NoRedirects(), HTTPSHandler(context=trusted)).open
            base_url = f'https://localhost:{server.server_port}/'
            try:
                with self.assertRaises(RuntimeError):
                    fetch_release(base_url, root / 'cache', sha(manifest), opener=opener, attempts=1)
                result = fetch_release(base_url, root / 'cache', sha(manifest), opener=opener)
                self.assertEqual(result['files'], 1)
                self.assertEqual(ranges, [0, 2048])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
