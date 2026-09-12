import io
import json
from pathlib import Path
import sys
import unittest
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'distribution'))
from github_download import GitHubRedirects, GitHubAssets


class Response(io.BytesIO):
    status = 200


class GitHubDownloadTest(unittest.TestCase):
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
