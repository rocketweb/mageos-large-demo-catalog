# Downloading a pinned catalog

The downloader uses Python 3.11+ on macOS or Linux. It needs no API key, GPU,
Magento connection or SSH access. Use `download.py` and `release.py` from reviewed
source tooling, kept in the same directory. Never execute a downloader merely
because it arrived beside an untrusted archive.

No public download location has been selected or published. Once a maintainer
provides a direct HTTPS directory URL and a separately trusted manifest SHA-256:

```sh
python3 dev/tools/wands_catalog/distribution/download.py \
  --base-url https://downloads.example.test/catalog/RELEASE/PROFILE/ \
  --cache-dir ./wands-cache \
  --manifest-sha256 PIN_FROM_MAINTAINER \
  --log-file ./wands-download.log
```

The URL above is a placeholder, not a working download service. It must point
directly to `manifest.json` and all archives listed in that manifest. Credentials,
URL query strings and redirects are refused. TLS certificate verification stays
enabled. The maintainer can provide a different direct HTTPS mirror containing
the same pinned files without changing the release identity.

The terminal stays quiet during the transfer. To watch progress in another terminal:

```sh
tail -f ./wands-download.log
```

The default is three attempts per file, a 30-second socket timeout and bounded
retry delays. `--attempts` accepts 1 through 5; `--timeout` accepts 1 through 60
seconds. These are socket timeouts, not a whole-release runtime limit.

## Resume and verify

If the connection drops or the process is stopped, rerun the same command.
The cache directory is `wands-cache/PIN_FROM_MAINTAINER/`, so different release
pins never share partial files. Only one downloader can write a release cache
at a time. Verified archives are reused. Partial archives resume with HTTP Range;
if the mirror ignores ranges, that archive restarts from byte zero.

Every completed archive must match its pinned size and SHA-256 before promotion
from `.part` to `.tar`. Corrupt completed files are retained as `.rejected-*`
for inspection, not silently accepted or deleted. These files use additional
disk space; remove only the exact rejected cache files you no longer need.

The downloader then runs the offline verifier across every archive member.
Exit zero and a `COMPLETE` log entry mean verification passed. Nonzero means the
release is not ready to extract. An interrupted run exits 130. Normal download
failures exit 1 and are logged without server response text or credential URLs.

Extraction remains an explicit, separate step:

```sh
python3 dev/tools/wands_catalog/distribution/release.py \
  ./wands-cache/PIN_FROM_MAINTAINER \
  --manifest-sha256 PIN_FROM_MAINTAINER --extract ./wands-staging
```

Use a new staging directory. This process never installs a module, changes a
Magento database, executes downloaded scripts or starts an image generator.
Follow the [installation guide](README.md) only after verifying the destination.
Resumable downloads do not imply resumable Magento imports: restore the empty
baseline before retrying an interrupted import.

## Verification scope

Download behavior is covered by unit tests and a real loopback HTTPS test that
closes the first artifact transfer early, then verifies the next run requests
the remaining byte range. Redirect refusal, unsafe URLs, corrupt bytes, wrong
ranges, oversized responses, disk space, cache symlinks, concurrent runs, pin
mismatches and quiet error logging are covered separately.

Public hosting and CDN behavior remain untested until a destination is selected.
The downloader works with the existing schema-1 rc2 catalog manifests. Those
immutable archives predate this companion tool; obtain it from reviewed source,
not by assuming it is already inside rc2.
