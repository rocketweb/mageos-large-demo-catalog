# Guided catalog installation and updates

The installer downloads a pinned catalog release and handles module setup,
website provisioning, media, ordered imports, indexing and native verification.
The default adds WANDS alongside the store's existing products and categories.
Its optional reset clears the catalog in a dedicated test installation. The
updater applies supported changes between pinned releases while preserving stock.

The [installer-2026.10.14-rc1 prerelease](https://github.com/rocketweb/mageos-large-demo-catalog/releases/tag/installer-2026.10.14-rc1)
provides a standalone download. Native acceptance covers the fixture workflow on
the versions listed below. The full 107,815-product run through this installer and
production-mode compilation remain unqualified. Use a dedicated test installation.

## Download and verify

Download the installer and check its SHA-256 before executing it:

```sh
curl --fail --location --output wands-catalog.pyz \
  https://github.com/rocketweb/mageos-large-demo-catalog/releases/download/installer-2026.10.14-rc1/wands-catalog.pyz &&
printf '%s  %s\n' \
  e458a4e269ed097f6584480eefc695b50c7373a4e82438aec005ec6e679e5b02 \
  wands-catalog.pyz | shasum -a 256 -c - &&
python3 wands-catalog.pyz --help
```

The release also provides `wands-catalog.sha256`, the acceptance report and license
notices. The pin above authenticates this exact installer artifact.

## Install

Use Python 3.11+ on macOS or Linux and the store's PHP runtime as its web filesystem
owner. Stop and drain cron, consumers, imports and other catalog writers before
applying changes. The Magento or Mage-OS installation must already exist.

```sh
python3 wands-catalog.pyz install \
  --magento-root=/path/to/test-store --base-url=https://catalog.example.test/
```

The default is a preview showing the destination, release, counts and settings.
`--json-plan` prints the complete plan for detailed review or automation.
Add `--apply --jobs-stopped` to proceed. The tool enables maintenance, creates and
checks a private database and file backup, then asks for the confirmation printed
in the plan. The token binds the target, release and changes. A changed destination
or release stage stops the operation.

The default catalog is the full `catalog-2026.10.06` release. Its trusted manifest
pin is built into the tool. Downloads use anonymous GitHub access and resume
verified transfers. Extraction is verified separately outside the Magento root.
`--work-dir` selects the download/staging directory. `--release-dir` uses an
offline directory containing the manifest and archives. Other tags require a
trusted `--manifest-sha256`; the requested profile must exist in that release.

The installer makes WANDS the default website so a normal single-site server
shows the catalog. `--keep-default-website` preserves the previous default and
requires server routing with `MAGE_RUN_TYPE=website` and `MAGE_RUN_CODE=wands`.
DNS, TLS and server rules that select another website need operator configuration.
Theme packages come from the store. Production mode runs DI compilation and
static deployment; `--locales` selects the enabled locales.

Existing products, stock, options, relationships, gallery rows and categories
outside WANDS are fingerprinted before and after installation and updates.
Existing WANDS products or website/store codes require `adopt`, `update` or an
explicit reset. The `WANDS-` SKU prefix is reserved for this catalog.

## Reset a dedicated test catalog

```sh
python3 wands-catalog.pyz install \
  --magento-root=/path/to/test-store --base-url=https://catalog.example.test/ \
  --reset-existing-catalog --dedicated-test-installation --apply --jobs-stopped
```

Reset is off by default and available only with `install`. It deletes every
product across all websites and the category trees beneath the retained roots.
The plan lists deletion counts, inventory reservation counts and retained root IDs. Magento's system root and
roots assigned to store groups remain as empty containers. Unassigned category
trees are removed. Deletion uses Magento's native product importer and category
service. Inventory reservation cleanup finishes synchronously before SKUs are
reintroduced; the reset does not queue a later cleanup against the new catalog.
Existing WANDS website/store containers can then be reused.

The whole installation must be a dedicated test store. The flag is an operator
declaration; software cannot prove that all data is disposable. The reset scope
is products and categories. Admin users, customers, orders, CMS content and
extensions remain. Obsolete media binaries may remain unreferenced. The backup
retains the complete media tree. The release's module and inputs replace the
previous catalog module and import data.

For unattended execution, `--confirm` accepts the token from a current preview.
The apply, stopped-writer and explicit reset flags are still required.

## Update

```sh
python3 wands-catalog.pyz update \
  --magento-root=/path/to/test-store --base-url=https://catalog.example.test/ \
  --tag=catalog-YYYY.MM.DD --manifest-sha256=TRUSTED_NEW_FULL_PIN
```

Preview first, then add `--apply --jobs-stopped`. The installed receipt records
the exact release and native catalog, module, input and original-media hashes.
Updates refuse local catalog or module edits since that receipt. Stock changes
are allowed. Existing legacy stock, MSI source items and reservations are checked
before and after the update; new products use their release stock values.

Updates use minimal CSVs for new products and changed scalar attributes or images.
Changed galleries are checked against their pinned previous image inventory,
then their product-specific links and roles are rebuilt from the new release.
Shared gallery masters and binary files are retained. Per-store image/caption
overrides require review before gallery replacement. Unchanged relationships and custom-option columns are omitted from
existing-product updates. Cleared scalar values use Magento's explicit empty
sentinel. A same-release update performs no catalog writes.

The initial updater supports additions, scalar changes and gallery replacement. Product
removal, type changes, category reassignment, configurable/bundle structure,
grouped links, custom options and downloadable definitions
require another transition recipe. These changes are refused before mutation.
Reset and reinstall provides the complete replacement path in a dedicated lab.

For a manually installed catalog, register the exact pinned release with `adopt`:

```sh
python3 wands-catalog.pyz adopt \
  --magento-root=/path/to/test-store --tag=catalog-2026.10.06 \
  --profile=full --apply --jobs-stopped
```

Adoption verifies the existing catalog and records its baseline. Later updates
also compare each changed native field against its pinned previous value. Local
overrides of those fields block the update, including edits made before adoption.

## Restore

Failed imports or verification leave maintenance enabled. Imports do not resume
automatically. Each attempt retains its plan, logs, backups and status in
`var/wands-installer/<attempt>/`, protected with directory mode 0700. The backup
contains the complete database, media, catalog module, application configuration,
import inputs and previous installer baseline, including private store data.

```sh
python3 wands-catalog.pyz restore \
  --magento-root=/path/to/test-store \
  --receipt=/path/to/test-store/var/wands-installer/ATTEMPT
```

The preview shows the backup, target and product counts. Add
`--apply --jobs-stopped` and confirm the restore plan. Restore quarantines the
changed file trees, restores the checked backup, compares the original native
catalog fingerprint and file hashes, then rebuilds indexes and caches. Production
mode also recompiles DI and static assets. Maintenance returns to its prior state.
Restore requires the original platform version, PHP family and Composer lock.

Restore returns the whole database to the snapshot. Test orders, customers and
other database changes made afterward are rolled back too. Before changing it,
restore creates another checked database and file backup in the quarantine.
Its printed inverse receipt can be passed to the same restore command to undo
the recovery. Keep both receipts until the store has been checked.

## Runtime options

`--php-command` accepts a JSON argument array. Containers need the same store
files mounted at the path supplied with `--runtime-root`:

```sh
python3 dev/tools/wands_catalog/distribution/catalog.py install \
  --magento-root=/host/path/to/store --runtime-root=/var/www/html \
  --php-command='["ddev","exec","php"]' --base-url=https://catalog.example.test/
```

The bridge reads credentials from the installed `env.php` and passes JSON on
stdin. It never prints database passwords or encryption keys. Database backup and
restore use `mysqldump` and `mysql` in that runtime. `--db-dump` and `--db-client`
select compatible executable paths. A private temporary client option file is
removed when the database command finishes.

Native PHP can use a local Docker database with `--db-container=CONTAINER`.
The published database port must match the installation's loopback configuration.
This transport passes the password through the database subprocess environment.
Remote media storage and symlinked destination paths require separate adapters
and are refused. Container UID permissions must permit the filesystem owner to
read the protected receipts.

The full release needs roughly 5.5 GB per download or extraction copy, plus
imported media, database, search indexes and complete media backups. The plan
reserves space for applying changes and backing up the changed state if recovery
is needed. The extra recovery reserve can be substantial for a populated store.

## Standalone artifact

```sh
python3 dev/tools/wands_catalog/distribution/build_installer.py \
  --output=var/wands-catalog.pyz
python3 var/wands-catalog.pyz --help
```

Maintainers can also run the source command at
`dev/tools/wands_catalog/distribution/catalog.py` with the same arguments.
This deterministic artifact includes the installer, PHP bridge, license notices and pinned
download/verifier code. A `.sha256` file accompanies it. Recipients should verify
the artifact against a trusted published hash before execution. Building creates
local files; publishing is a separate step.

## Acceptance

The native harness uses an empty, pre-created database named `wands_installer_*`.
It imports the 127 QA fixtures across all six product types, updates a scalar
value and adds a product, preserves an existing product and category by default,
checks stock preservation, rejects local edits, resets
129 products including an unrelated SKU, then restores and compares the complete
native catalog fingerprint.

The complete fixture workflow passed on Mage-OS **3.5.0**, Mage-OS **3.6.0** and
Magento Open Source **2.4.9**, using PHP **8.4.24**, MySQL **8.4** and OpenSearch
**3.8.0**. Each run also adopted an existing catalog without changing it, verified
gallery replacement, and restored after an intentionally failed indexing command.
Other versions are refused. Composer requirements use the Magento interfaces
that Mage-OS provides through `replace`.

The complete 107,815-product import through this new installer, other PHP versions,
production-mode compilation and every hosting wrapper need separate acceptance.
Native verification covers SKU/type inventory, names, statuses, applicable prices,
image roles and gallery contents, category assignments, configurable links and declared bundle counts.
Storefront, checkout and payment behavior have separate checks.

See the [dated acceptance report](../docs/INSTALLER_ACCEPTANCE_2026-10-14.md)
for commands, fixture identities and the scope of the storefront smoke check.
