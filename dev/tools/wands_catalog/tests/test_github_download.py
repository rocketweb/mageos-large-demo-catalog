import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'distribution'))
from github_download import GitHubRedirects, GitHubAssets
from download import fetch_release
from release import digest, verify_release, write_archive


class Response(io.BytesIO):
    status = 200
    headers = {}


class GitHubDownloadTest(unittest.TestCase):
    def test_anonymous_cli_does_not_resolve_local_credentials(self):
        from github_download import main
        with tempfile.TemporaryDirectory() as directory, patch('github_download.GitHubAssets') as client, \
                patch('github_download.fetch_release'), patch.object(sys,'argv',[
                    'github_download.py','--repo','example/catalog','--tag','v2','--profile','medium',
                    '--cache-dir',directory,'--manifest-sha256','a'*64,'--anonymous']):
            self.assertEqual(main(),0)
            self.assertEqual(client.call_args.kwargs['token'],'')

    def test_gallery_profile_uses_its_own_asset_namespace(self):
        def metadata(request, timeout):
            data = {'id': 11} if '/tags/' in request.full_url else [
                {'id': 7, 'name': 'gallery-manifest.json'},
                {'id': 8, 'name': 'gallery-gallery-additions.tar'}]
            return Response(json.dumps(data).encode())
        calls=[]
        def binary(request, timeout):
            calls.append(request.full_url)
            return Response(b'gallery')
        client=GitHubAssets('example/catalog','enriched-v2','gallery',token='',
                            metadata_opener=metadata,binary_opener=binary)
        with client(Request(client.base_url+'gallery-additions.tar'),timeout=10) as response:
            self.assertEqual(response.read(),b'gallery')
        self.assertEqual(calls,['https://api.github.com/repos/example/catalog/releases/assets/8'])

    def test_medium_download_verifies_extracts_and_reuses_pinned_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = write_archive(root / 'catalog.tar', {'data/products.csv': b'sku\nMEDIUM-1\n'})
            (root / 'manifest.json').write_text(json.dumps({'schema': 1, 'profile': 'medium',
                                                         'artifacts': [artifact]}))
            pin = digest(root / 'manifest.json')
            payloads = {7: (root / 'manifest.json').read_bytes(), 8: (root / 'catalog.tar').read_bytes()}
            def metadata(request, timeout):
                data = {'id': 11} if '/tags/' in request.full_url else [
                    {'id': 7, 'name': 'medium-manifest.json'}, {'id': 8, 'name': 'medium-catalog.tar'}]
                return Response(json.dumps(data).encode())
            calls = []
            def binary(request, timeout):
                asset = int(request.full_url.rsplit('/', 1)[1])
                calls.append(asset)
                return Response(payloads[asset])
            client = GitHubAssets('example/catalog', 'enriched-v1', 'medium', token='',
                                  metadata_opener=metadata, binary_opener=binary)
            fetch_release(client.base_url, root / 'cache', pin, opener=client, attempts=1)
            fetch_release(client.base_url, root / 'cache', pin, opener=client, attempts=1)
            self.assertEqual(calls, [7, 8])
            verify_release(root / 'cache' / pin, pin, root / 'staged')
            self.assertEqual((root / 'staged/data/products.csv').read_bytes(), b'sku\nMEDIUM-1\n')

    def test_cli_accepts_medium_and_remains_quiet(self):
        from github_download import main
        with tempfile.TemporaryDirectory() as directory, patch('github_download.GitHubAssets') as client, \
                patch('github_download.fetch_release') as fetch, patch('sys.stdout', new_callable=io.StringIO) as stdout:
            client.return_value.base_url = 'https://github.com/example/catalog/releases/download/enriched-v1/'
            with patch.object(sys, 'argv', ['github_download.py', '--repo', 'example/catalog',
                    '--tag', 'enriched-v1', '--profile', 'medium', '--cache-dir', directory,
                    '--manifest-sha256', 'a' * 64, '--log-file', directory + '/download.log']):
                self.assertEqual(main(), 0)
            self.assertEqual(stdout.getvalue(), '')
            self.assertEqual(client.call_args.args[2], 'medium')
            fetch.assert_called_once()

    def test_medium_profile_maps_only_medium_assets(self):
        def metadata(request, timeout):
            data = {'id': 11} if '/tags/' in request.full_url else [
                {'id': 7, 'name': 'medium-manifest.json'},
                {'id': 8, 'name': 'full-manifest.json'}]
            return Response(json.dumps(data).encode())
        calls = []
        def binary(request, timeout):
            calls.append(request.full_url)
            return Response(b'medium')
        client = GitHubAssets('example/catalog', 'enriched-v1', 'medium', token='',
                              metadata_opener=metadata, binary_opener=binary)
        with client(Request(client.base_url + 'manifest.json'), timeout=10) as response:
            self.assertEqual(response.read(), b'medium')
        self.assertEqual(calls, ['https://api.github.com/repos/example/catalog/releases/assets/7'])

    def test_allowed_redirect_strips_auth_and_preserves_range(self):
        request = Request('https://api.github.com/repos/example/catalog/releases/assets/7',
                          headers={'Authorization': 'Bearer TEST_ONLY', 'Cookie': 'test', 'Range': 'bytes=123-'})
        redirected = GitHubRedirects().redirect_request(request, None, 302, '', {},
            'https://release-assets.githubusercontent.com/asset?signature=example')
        self.assertIsNone(redirected.get_header('Authorization'))
        self.assertIsNone(redirected.get_header('Cookie'))
        self.assertEqual(redirected.get_header('Range'), 'bytes=123-')

    def test_other_redirect_destinations_refused(self):
        request = Request('https://api.github.com/repos/example/catalog/releases/assets/7')
        for url in ['http://release-assets.githubusercontent.com/a', 'https://evil.test/a',
                    'https://release-assets.githubusercontent.com.evil.test/a',
                    'https://user:password@release-assets.githubusercontent.com/a',
                    'https://release-assets.githubusercontent.com:8443/a']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                GitHubRedirects().redirect_request(request, None, 302, '', {}, url)

    def test_flat_profile_names_map_to_local_manifest_names(self):
        calls = []
        def metadata(request, timeout):
            calls.append(request)
            if '/tags/' in request.full_url:
                return Response(json.dumps({'id': 11}).encode())
            return Response(json.dumps([{'id': 7, 'name': 'full-manifest.json'},
                                        {'id': 8, 'name': 'full-catalog.tar'}]).encode())
        def binary(request, timeout):
            calls.append(request)
            return Response(b'payload')
        client = GitHubAssets('example/catalog', 'catalog-rc2', 'full', token='TEST_ONLY',
                              metadata_opener=metadata, binary_opener=binary)
        with client(Request(client.base_url + 'catalog.tar', headers={'Range': 'bytes=3-'}), timeout=10) as response:
            self.assertEqual(response.read(), b'payload')
        self.assertTrue(calls[-1].full_url.endswith('/releases/assets/8'))
        self.assertEqual(calls[-1].get_header('Authorization'), 'Bearer TEST_ONLY')
        self.assertEqual(calls[-1].get_header('Range'), 'bytes=3-')
        with self.assertRaises(ValueError):
            client(Request('https://evil.test/catalog.tar'), timeout=10)
        with self.assertRaises(ValueError):
            client(Request(client.base_url + 'missing.tar'), timeout=10)

    def test_invalid_target_never_contacts_network(self):
        for repo, tag, profile in [('evil.test/a/b', 'rc2', 'full'), ('example/catalog', '../bad', 'full'),
                                   ('example/catalog', 'rc2', '../')]:
            with self.assertRaises(ValueError):
                GitHubAssets(repo, tag, profile, token='', metadata_opener=lambda *a, **k: self.fail('network'))

    def test_duplicate_asset_names_refused(self):
        def metadata(request, timeout):
            data = {'id': 11} if '/tags/' in request.full_url else [
                {'id': 7, 'name': 'full-catalog.tar'}, {'id': 8, 'name': 'full-catalog.tar'}]
            return Response(json.dumps(data).encode())
        with self.assertRaises(ValueError):
            GitHubAssets('example/catalog', 'rc2', 'full', token='', metadata_opener=metadata)


if __name__ == '__main__':
    unittest.main()
