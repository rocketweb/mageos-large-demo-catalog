# Catalog installer acceptance, October 14, 2026

The local installer candidate passed native fixture acceptance on Mage-OS 3.5.0,
Mage-OS 3.6.0 and Magento Open Source 2.4.9. Default installation preserves the
existing catalog. Reset requires explicit flags, a checked backup and confirmation.
The updater and recovery path were exercised against actual installed stores.

This report qualifies a 127-product synthetic fixture release and one added
product. The complete 107,815-product catalog through the new installer, production
mode, other PHP versions and hosting wrappers remain unqualified. The installer
is distributed separately as
[installer-2026.10.14-rc1](https://github.com/rocketweb/mageos-large-demo-catalog/releases/tag/installer-2026.10.14-rc1).
Existing catalog release assets remain unchanged.

## Runtime matrix

Each store had its own Composer dependencies, database and OpenSearch index
prefix. The disposable databases were named `wands_installer_*`; the test helper
refuses other database names. Existing catalog stores were not test targets.

| Platform | PHP | Database | Search | Native workflow |
| --- | --- | --- | --- | --- |
| Mage-OS 3.5.0 | 8.4.24 | MySQL 8.4 | OpenSearch 3.8.0 | Passed |
| Mage-OS 3.6.0 | 8.4.24 | MySQL 8.4 | OpenSearch 3.8.0 | Passed |
| Magento Open Source 2.4.9 | 8.4.24 | MySQL 8.4 | OpenSearch 3.8.0 | Passed |

The PHP family gate accepts PHP 8.4; the executed patch version was 8.4.24.
The fixtures ran in default mode. Production compilation and static deployment
are implemented paths that need their own acceptance.

## Verified workflow

1. Seed one unrelated product with stock and an existing category.
2. Preview, back up and install 127 WANDS products across all six product types.
   Compare native product, stock, category, option, relationship and gallery rows
   outside WANDS before and after. Total products: 128.
3. Remove the installer baseline, refuse update without it, then adopt the exact
   installed release. Adoption leaves the native catalog fingerprint unchanged.
4. Change one existing product's quantity to 41 and add a reservation of -3.
   Apply a second pinned fixture release with a changed name, price, gallery and
   one new virtual product. The release's quantity 999 is ignored for the existing
   SKU. Legacy stock, MSI source items and reservations remain unchanged.
   Total products: 129, of which 128 are WANDS.
5. Run a same-release update and compare the unchanged native fingerprint.
   Make a local name edit and verify that update refuses it before mutation.
6. Refuse another default install over existing WANDS products. Explicitly reset
   129 products and the non-root categories, clear the existing reservation
   synchronously, and reinstall the 127-product fixture. No deferred inventory
   cleanup message is introduced by the reset.
7. Restore the checked backup and compare the original native catalog fingerprint
   and recorded file hashes.
8. Force `indexer:reindex` to fail during another reset/install. Verify that
   maintenance remains enabled, restore its backup, and compare the original state.
9. Exercise recovery's inverse receipt, then reapply recovery. Both operations
   restore their recorded native catalog fingerprints.

The release fixture module was frozen before the final matrix runs. The same
33-file snapshot was used on all three platforms, with inventory digest:

```text
aa3ad6299949872b14ca040c3b572f6f7581667e70157b47966599e3c48d0a38
```

This snapshot isolates the installer tests from concurrent navigation work in the
shared source checkout. It includes the cross-platform Composer requirements.
Fixture releases `fixture-v1` and `fixture-v2` are test artifacts, not catalog
releases for recipients.

## Commands and evidence

Run the public native harness against an independently installed, empty disposable
store, using a fixed module snapshot:

```sh
python3 dev/tools/wands_catalog/distribution/acceptance/catalog_installer.py \
  --magento-root=/path/to/disposable-store \
  --module-root=/path/to/fixed-module-snapshot \
  --php-binary=/path/to/php-8.4 \
  --db-container=DISPOSABLE_MYSQL_CONTAINER \
  --base-url=http://127.0.0.1:18051/ --output=/path/to/new-evidence
```

The harness uses the previously accepted QA fixture inputs under
`var/catalog-qa-20261006/candidate-v5/`. It records real CLI previews, apply logs
and `acceptance.json`. The final matrix evidence is retained privately under
`var/catalog-installer-20261014/`:

| Runtime | Main receipt | Inverse recovery receipt |
| --- | --- | --- |
| Mage-OS 3.5.0 | `acceptance-fixed/acceptance.json` | `pinned-store-inverse-acceptance.json` |
| Mage-OS 3.6.0 | `mageos36-acceptance-fixed/acceptance.json` | `mageos36-store-inverse-acceptance.json` |
| Magento 2.4.9 | `magento-acceptance-fixed/acceptance.json` | `magento-store-inverse-acceptance.json` |

The inverse cycles were also executed independently after the matrix runs through
the harness's `verify_inverse_recovery` function. Raw database dumps, credentials,
store configuration and runtime logs remain ignored private artifacts.

The final targeted regression gate ran 65 tests without skips:

```sh
PYTHONPATH=dev/tools/wands_catalog/tests \
WANDS_TEST_PHP=/path/to/php-8.4 WANDS_TEST_HTTPS=1 \
WANDS_INSTALLER_TEST_STORE=/path/to/disposable-store \
python3 -m unittest test_catalog_installer test_lab_distribution test_lab_download \
  test_github_download test_expanded_release test_github_assets test_lab_handoff \
  test_candidate_assets
```

The native gallery guard test temporarily inserts a store-specific caption,
verifies refusal, and removes only its synthetic row in `finally`. It was observed
failing before the guard was added and passing afterward. Other focused checks
covered mount mismatches, embedded PHP loading from the zipapp, checksum
tampering, explicit reset, empty import phases and restore scope.

Both new PHP files passed `php -l`. No PHPCS installation was present in these
fixtures. The runtime bridge was reviewed for bound SQL, argv-based subprocesses,
private credential files, protected backups and sanitized native errors.

## Packaged artifact and storefront check

`build_installer.py` creates a deterministic `wands-catalog.pyz` and SHA-256 file.
The archive includes the runtime bridge, pinned downloader/verifier, MIT license
and attribution notice. A real packaged preview against a populated fixture
checks embedded runtime execution, release verification, counts and confirmation
without applying a catalog mutation.

The reviewed artifact is 33,316 bytes with SHA-256:

```text
e458a4e269ed097f6584480eefc695b50c7373a4e82438aec005ec6e679e5b02
```

A local Luma browser smoke check on Mage-OS 3.6 confirmed the updated product
heading, price of $102.00, loaded replacement image and enabled Add to Cart button.
The initial disabled button came from a missing versioned `requirejs-config.js`
route in the disposable PHP server. Correcting that test-server route restored
normal JavaScript initialization. No installer change was needed for that issue.
The screenshot is retained privately as `storefront-updated.png`.

This smoke check does not qualify checkout, payments, every product page or
search behavior. Image hashes prove the gallery transition's contents; the
replacement photo is synthetic test data.

For recipient commands and recovery requirements, see the
[installer guide](../distribution/INSTALLER.md).
