# Contributing

Start with the [README](README.md) to install a release in a disposable Mage-OS
lab. To change the tooling, clone this repository and work on a branch. Do not
run its root `composer install` as a catalog installation step: that file
describes the historical development store and its separate dependencies.

## Where to work

- `app/code/RocketWeb/LabCatalog/`: portable catalog module.
- `dev/tools/wands_catalog/`: preparation, import, media and validation tools.
- `dev/tools/wands_catalog/distribution/`: release building and downloading.
- `dev/tools/wands_catalog/tests/`: Python regression tests.

The Workbench snapshot under `packages/` is a separate project. Keep catalog
changes out of that snapshot unless they specifically require an integration fix.

## Before opening a pull request

Keep changes focused. For a bug, include a small reproducer and a regression
test. For catalog corrections, show the affected SKUs, relationships and counts,
and distinguish source evidence from synthetic choices. Preserve identifiers,
provenance and license notices.

Run from this repository's root with Python 3.11+:

```sh
python3 -m unittest discover -s dev/tools/wands_catalog/tests -p 'test_*.py' \
  > /tmp/wands-tests.log 2>&1
```

For the PHP checks and local HTTPS download-resume fixture, provide PHP 8.4 and
allow the tests to bind a localhost port:

```sh
WANDS_TEST_PHP=/absolute/path/to/php WANDS_TEST_HTTPS=1 \
  python3 -m unittest discover -s dev/tools/wands_catalog/tests -p 'test_*.py' \
  > /tmp/wands-tests.log 2>&1
```

Use `tail -f /tmp/wands-tests.log` in another terminal. Report the exit status,
test totals and any skipped checks. These tests do not replace a Magento import
or browser check. For storefront changes, include the tested Mage-OS/theme
versions and actual screenshots. Do not claim checkout or payment support from
catalog-page checks.

## Files and rights

Keep product images, archives, database dumps, credentials, runtime logs and
machine-specific configuration out of Git. Use release assets for catalog media.
Small documentation screenshots are welcome when they contain no private data.
Do not add third-party product photography without a documented right to share it.

Submit only material you have permission to contribute under the applicable
terms in [NOTICE.md](NOTICE.md). Keep attribution for third-party material and
identify any additional terms in the pull request. Do not change licensing or
make incomplete provenance look like a rights clearance.

Use issues for reproducible bugs, installation questions and proposed catalog
improvements. Include the release tag, profile, manifest hash, runtime versions
and redacted logs. This is community lab tooling, with no guaranteed response
time or long-term support policy. Report vulnerabilities privately as described
in [SECURITY.md](SECURITY.md).
