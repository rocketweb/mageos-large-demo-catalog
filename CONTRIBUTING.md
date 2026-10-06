# Contributing

Start with the [README](README.md) to install a release in a disposable Mage-OS
lab. To change the tooling, clone this repository and work on a branch. Do not
run its root `composer install` as a catalog installation step: that file
describes the historical development store and its separate dependencies.

## Contribution overview

1. Choose a focused change and preserve identifiers, provenance and unrelated work.
2. Run the relevant tooling checks and actual Magento/browser checks for the behavior changed.
3. Submit the change with its evidence and any unresolved limits.

Use the [documentation index](dev/tools/wands_catalog/docs/README.md) to find
current guides, implementation details and dated acceptance reports. The source
checkout, installed lab stores and published release assets are separate states.

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

Module unit tests require a compatible Mage-OS checkout with its development
dependencies. This repository's root Composer project is not the setup recipe.
Run from this repository root, substituting the existing checkout and PHP binary:

```sh
WANDS_TEST_STORE=/absolute/path/to/mageos
/absolute/path/to/php "$WANDS_TEST_STORE/vendor/bin/phpunit" \
  --do-not-cache-result \
  --bootstrap "$WANDS_TEST_STORE/dev/tests/unit/framework/bootstrap.php" \
  app/code/RocketWeb/LabCatalog/Test/Unit
```

The recorded October 6 checks used PHP 8.4.24: 868 tooling tests without skips,
plus 13 module tests with 39 assertions. Rerun relevant checks for new changes;
do not treat these historical totals as a required constant.

## Documentation changes

Lead guides with what the reader needs: purpose, status, the main result or
decision, and a short route to the next action. Use compact tables or lists when
they help scanning. Put commands, file contracts, invariants, evidence and
recovery details below that overview. Short policies and small reference notes
can stay short; avoid adding empty sections just to match a template.

Keep current instructions separate from dated results and proposals. Label the
profile, release or installation a count belongs to. Link new pages from the
documentation index, use relative links that work on GitHub, and preserve old
evidence as history instead of rewriting it into a current success claim.
Check local links, heading anchors, fenced examples and applicable CLI options.
Documentation changes do not update immutable release assets.

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
