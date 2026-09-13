"""Download a pinned catalog profile from GitHub release assets, without installing it."""
import argparse
import json
import logging
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request

from download import fetch_release, NoRedirects


class GitHubRedirects(HTTPRedirectHandler):
    max_redirections = 3

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urlsplit(newurl)
        if (destination.scheme != 'https' or destination.hostname not in {
                'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
                or destination.port not in (None, 443) or destination.username or destination.password
                or destination.fragment or any(ord(c) <= 32 for c in newurl)):
            raise ValueError('GitHub asset redirect destination refused')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        for name in ['Authorization', 'Cookie', 'Host']:
            redirected.remove_header(name)
        return redirected


def github_token():
    value = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if value:
        return value.strip()
    try:
        result = subprocess.run(['gh', 'auth', 'token', '--hostname', 'github.com'],
                                capture_output=True, text=True, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


class GitHubAssets:
    def __init__(self, repository, tag, profile, *, token=None, metadata_opener=None, binary_opener=None):
        if (not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', repository)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', tag)
                or profile not in ('starter', 'medium', 'full', 'toolkit')):
            raise ValueError('Invalid GitHub repository, tag or profile')
        self.api_root = 'https://api.github.com/repos/' + repository
        self.base_url = f'https://github.com/{repository}/releases/download/{tag}/'
        self.profile = profile
        self.token = github_token() if token is None else token
        self.metadata_opener = metadata_opener or build_opener(NoRedirects()).open
        self.binary_opener = binary_opener or build_opener(GitHubRedirects()).open
        release = self._json(self.api_root + '/releases/tags/' + tag)
        release_id = release['id']
        if type(release_id) is not int or release_id <= 0:
            raise ValueError('Invalid release identity')
        self.assets = {}
        for page in range(1, 11):
            entries = self._json(f'{self.api_root}/releases/{release_id}/assets?per_page=100&page={page}')
            if not isinstance(entries, list):
                raise ValueError('Invalid release asset inventory')
            for entry in entries:
                name, asset_id = entry['name'], entry['id']
                if not isinstance(name, str) or type(asset_id) is not int or asset_id <= 0 or name in self.assets:
                    raise ValueError('Invalid or duplicate release asset')
                self.assets[name] = asset_id
            if len(entries) < 100:
                break
        else:
            raise ValueError('Release asset inventory exceeds limit')

    def _request(self, url, headers):
        request = Request(url, headers={'User-Agent': 'WANDS-Lab-Downloader/1', **headers})
        if self.token:
            request.add_unredirected_header('Authorization', 'Bearer ' + self.token)
        return request

    def _json(self, url):
        request = self._request(url, {'Accept': 'application/vnd.github+json'})
        with self.metadata_opener(request, timeout=30) as response:
            if response.status != 200:
                raise ValueError('GitHub release metadata unavailable')
            data = response.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise ValueError('GitHub release metadata exceeds size limit')
        return json.loads(data)

    def __call__(self, request, timeout):
        if not request.full_url.startswith(self.base_url):
            raise ValueError('Unexpected download origin')
        name = request.full_url[len(self.base_url):]
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
            raise ValueError('Invalid asset filename')
        asset_id = self.assets.get(self.profile + '-' + name)
        if asset_id is None:
            raise ValueError('Missing release asset')
        headers = {key: value for key, value in request.header_items()
                   if key.lower() in ('range', 'accept-encoding', 'user-agent')}
        headers['Accept'] = 'application/octet-stream'
        return self.binary_opener(self._request(f'{self.api_root}/releases/assets/{asset_id}', headers), timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--profile', choices=['starter', 'medium', 'full', 'toolkit'], required=True)
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--log-file', type=Path, default=Path('wands-download.log'))
    parser.add_argument('--attempts', type=int, default=3)
    parser.add_argument('--timeout', type=int, default=30)
    args = parser.parse_args()
    logging.basicConfig(filename=args.log_file, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        client = GitHubAssets(args.repo, args.tag, args.profile)
        fetch_release(client.base_url, args.cache_dir, args.manifest_sha256, opener=client,
                      attempts=args.attempts, timeout=args.timeout)
    except KeyboardInterrupt:
        logging.info('Interrupted; rerun to resume')
        return 130
    except Exception as error:
        logging.error('GitHub download failed (%s). Check access, tag, profile and pin; rerun to retry.', type(error).__name__)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
