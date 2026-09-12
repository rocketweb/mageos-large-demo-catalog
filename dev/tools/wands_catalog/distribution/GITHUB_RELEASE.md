# GitHub release assets

Use the assets attached to `catalog-2026.09.12-rc2` in
`rocketweb/mageos-large-demo-catalog`. The repository is private; recipients need
repository access. Publishing these assets does not change repository visibility.

The release contains the unchanged rc2 starter and full catalog archives, with
`starter-` or `full-` added to asset names to avoid filename collisions. The
GitHub downloader maps those names back into a profile-specific cache. Original
catalog manifests and archive bytes keep their tested hashes.

Download `github_download.py`, `download.py`, and `release.py` together. Authenticate
their hashes against the release notes before running them. Python 3.11+ is
required. For private access, use an existing `gh auth login` session, or provide
`GH_TOKEN`/`GITHUB_TOKEN` through your credential manager. Do not put tokens in
commands, files, URLs or logs. Public repositories can be read without a token.

## Download a profile

From the directory containing the three scripts:

```sh
python3 github_download.py --repo rocketweb/mageos-large-demo-catalog \
  --tag catalog-2026.09.12-rc2 --profile starter --cache-dir ./cache \
  --manifest-sha256 42bd8400415204b8bc6b8f5ed5cf8adb8156185eca92ff156cd54285bb68b40f
```

For the full catalog, use `--profile full` and this pin:

```text
9bf76000f3de8816459638ba2f396af805eaaa83c504886000e1b3c32adcf19d
```

Logs go to `wands-download.log` by default. Watch them with
`tail -f wands-download.log`. Rerun the same command after interruption. Verified
files are reused; partial files resume where GitHub supports ranges. Archives
are not accepted until their exact size, SHA-256 and member inventory pass.

GitHub credentials are sent only to `api.github.com`. Asset redirects are limited
to HTTPS on GitHub's known asset-storage hosts, with authorization and cookies
removed before following them. Generic mirrors still use `download.py`, whose
redirect refusal is unchanged. Signed storage URLs are not logged or persisted.

## Get current installation tools

Use `--profile toolkit` and the toolkit manifest pin from the release notes to
fetch the small current toolkit. Extract it into a new directory with `release.py`.
It includes the current preflight and installation instructions. Use its preflight
instead of the older one nested inside the immutable rc2 catalog archives.

The release notes contain complete commands with exact toolkit and profile pins.
An offline alternative is to download all assets through the GitHub UI or
`gh release download`, verify `SHA256SUMS`, and remove the selected profile prefix
from filenames in a new profile directory before running the offline verifier.

The release tag anchors the hosting repository's existing main commit. It does
not claim that GitHub's automatically generated source ZIP contains the current
catalog tooling. Use the attached toolkit and profile module archives. Each
contains the actual source used, with hashes and retained license notices.

This is a lab prerelease. Installation remains fresh-install-only, with an empty
baseline backup for recovery. Resumable downloads do not imply resumable imports.
No Mage-OS 3.4, clean-install Hyvä or checkout/payment result is claimed.
