# WANDS catalog for Mage-OS Lab

A large, synthetic home-and-furniture catalog for testing search, navigation,
configurable products, bundles, prices, inventory and product media.

This is a lab prerelease, not an official Mage-OS or Wayfair release.
The enriched medium and full profiles were tested on Mage-OS 3.5.0 with Hyvä
Default 1.5.2 and stock OpenSearch 3.1.0. See the exact profile pins and limits in
[enriched acceptance](ENRICHED_ACCEPTANCE.md). The older [rc2 acceptance](ACCEPTANCE.md)
and [Hyvä checks](HYVA_ACCEPTANCE.md) remain historical evidence.
Theme packages remain separate. Mage-OS 3.4 was not tested. Downloads are public.
Code and authored data use MIT; generated images use CC0 where rights are held.
Do not use this candidate in a customer store.

## What recipients need

A dedicated, empty Mage-OS lab with PHP 8.4, USD currency, the standard product
types and Python 3.11 or newer for offline verification. A GPU, model service,
API key, Hyvä theme, Koti sample data and hybrid search are not required.

Choose one profile on a fresh installation:

- **Medium:** 5,000 records, with complete configurable and bundle dependencies.
  This is the default for a first installation.
- **Full:** 53,844 records, including disabled legacy variants. This is a derived
  catalog, not the original 42,994-product WANDS benchmark.

Each profile includes `catalog.tar`, `module.tar`, separate `media-*.tar` files,
`manifest.json`, and the standalone `release.py` verifier. Images are not in Git
or Git LFS. No database, customer, order, credential, vendor or theme export is
included. The candidate is assembled from saved inputs, not a live database dump.

## Verify offline first

For the current GitHub assets, begin with the
[root quick start](https://github.com/rocketweb/mageos-large-demo-catalog#quick-start). It downloads and verifies
both the catalog profile and the current toolkit. Return here for installation.
The instructions below also support a previously obtained offline candidate.

Obtain the manifest SHA-256 through a trusted channel separate from the archives.
The adjacent `manifest.sha256` is a convenience, not an authenticity guarantee.
Use the verifier from reviewed tooling or independently check its source hash.

```sh
python3 release.py ./candidate --manifest-sha256 PIN_FROM_MAINTAINER
tail -f ./candidate/verification.log
```

Exit zero means all declared archives and members match their hashes and sizes.
No output is written to the terminal by default. Corruption or unsafe archive
contents produces a nonzero exit and an explanation in the log.

Optionally extract into a **new** staging directory, never directly into Magento:

```sh
python3 release.py ./candidate --manifest-sha256 PIN_FROM_MAINTAINER \
  --extract ./wands-staging
```

The [GitHub downloader](GITHUB_RELEASE.md) provides pinned, resumable downloads
from the current release. The generic [download tool](DOWNLOADS.md) supports
direct HTTPS mirrors. Offline copying remains supported.
Automatic interrupted-import recovery is not supported in this candidate.

## Install into an empty Mage-OS instance

The following procedure was exercised on a fresh Mage-OS 3.5.0 installation,
including the ownership and menu steps noted below. Back up the empty installation first.
Confirm zero products, no existing `wands` website/store and no other sample data.
Do not install this over an existing WANDS catalog or switch medium to full in
place. On interruption, restore the empty baseline before retrying.

Run the read-only destination preflight from extracted tooling before installing
the module or provisioning. It refuses any existing products or WANDS store codes
and logs exact proposed product/media counts. It does not create a backup or
grant import approval:

```sh
php ./toolkit/tools/preflight.php --magento-root=/path/to/empty/mageos \
  --data-dir=./wands-staging/data --log-file=./preflight.log
```

Run that command from the download working directory shown in the root quick
start. Use the current toolkit, not the older preflight nested inside rc2's
profile archive. If PHP runs in a container, mount or copy both directories into
it and adjust the paths. This check must run in the destination PHP environment.

For the copy steps below, replace `/path/to/wands-demo` with the absolute download
directory as seen by the Mage-OS environment. Run all subsequent shell commands
from your **Mage-OS root**, as the web filesystem owner. Stop on any nonzero exit.

1. Copy the staged `module/` contents into a new
   `app/code/RocketWeb/LabCatalog/` directory. The module has its own Composer
   metadata; do not use this repository's project-level Composer files.

   ```sh
   WANDS_STAGE=/path/to/wands-demo/wands-staging
   test ! -e app/code/RocketWeb/LabCatalog && \
     mkdir -p app/code/RocketWeb/LabCatalog && \
     cp -R "$WANDS_STAGE/module/." app/code/RocketWeb/LabCatalog/
   ```

2. Enable `RocketWeb_LabCatalog`, run `setup:upgrade` and the normal compilation
   steps for the recipient's deployment mode. These are database writes.

   ```sh
   php bin/magento module:enable RocketWeb_LabCatalog > var/log/wands-enable.log 2>&1
   php bin/magento setup:upgrade > var/log/wands-setup.log 2>&1
   ```

   Inspect each log before continuing. Production mode also needs the usual DI
   compilation and static-content deployment for the installed theme and locale.

3. Provision the WANDS website with an explicit recipient URL:

   ```sh
   php bin/magento lab:wands:provision --base-url=https://catalog.example.test/ \
     > var/log/wands-provision.log 2>&1
   ```

   Configure the recipient's web server to serve website code `wands`. Provisioning
   does not configure DNS, TLS or the web server. It preserves the inherited theme
   and global price scope. Select an installed theme explicitly with
   `--theme=frontend/Vendor/theme` if needed. This catalog expects USD, not a
   multi-currency production configuration.

   The request must reach Magento with `MAGE_RUN_TYPE=website` and
   `MAGE_RUN_CODE=wands`. Without this routing you may see the empty default store.

4. Copy staged `data/` to `var/wands-lab/data/`, and staged `media/wands-lab/` to
   `pub/media/import/wands-lab/`. Provisioned attributes must contain every label
   in `data/attribute-options.json` before product import.

   ```sh
   mkdir -p var/wands-lab/data pub/media/import/wands-lab
   cp -R "$WANDS_STAGE/data/." var/wands-lab/data/
   cp -R "$WANDS_STAGE/media/wands-lab/." pub/media/import/wands-lab/
   ```

5. Import in this exact order, inspecting the log and exit code after each step:

   ```sh
   php bin/magento lab:wands:import --file=var/wands-lab/data/1-simple.csv \
     > var/log/wands-simple.log 2>&1
   php bin/magento lab:wands:import --file=var/wands-lab/data/2-configurable.csv \
     > var/log/wands-configurable.log 2>&1
   php bin/magento lab:wands:import --file=var/wands-lab/data/3-bundle.csv \
     > var/log/wands-bundle.log 2>&1
   php bin/magento lab:wands:import --file=var/wands-lab/data/4-media.csv \
     > var/log/wands-media.log 2>&1
   ```

   Enriched candidates also include `5-merchandising.csv`. Import it last, after
   every linked SKU exists:

   ```sh
   if test -f var/wands-lab/data/5-merchandising.csv; then
     php bin/magento lab:wands:import --file=var/wands-lab/data/5-merchandising.csv \
       > var/log/wands-merchandising.log 2>&1
   fi
   ```

   Use the current module's native `append` behavior. The earlier module used
   `add_update`, which can remove product links during a later media-only import.
   The immutable rc2 module does not contain this correction. Retain the original
   candidates; do not replace their archives or imply they passed enriched testing.

   `--validate-only` validates without changing products but writes native import
   staging tables. Dependent parents/bundles cannot be validated as if their
   children already existed. Do not use bundle reconciliation on a fresh install.

6. Run `lab:wands:curate-navigation` to limit the menu to the ten main departments
   without deleting categories or product assignments. Run Magento commands as
   the web filesystem owner so generated code remains writable by PHP-FPM.

   ```sh
   php bin/magento lab:wands:curate-navigation > var/log/wands-navigation.log 2>&1
   ```

7. Reindex, clean relevant caches, then compare exact type/link/selection/media
   counts with `data/counts.json`. Check configurable options, child price/image
   switching, bundle selections and calculated prices, stock scenarios, search
   and product images on desktop and mobile.

   ```sh
   php bin/magento indexer:reindex > var/log/wands-reindex.log 2>&1
   php bin/magento cache:clean > var/log/wands-cache.log 2>&1
   ```

   Tail any log from another terminal, for example `tail -f var/log/wands-media.log`.

The original importer commands remain general-purpose; they do not automatically
enforce the empty-store requirement. The clean-install operator must check it.
Uninstalling the module does not delete data. Never use a whole-store SQL deletion
as a catalog uninstaller.

## Known limits

- Separate testing before claiming Mage-OS 3.4 or a fresh import under Hyvä.
  The recorded Hyvä checks cover a theme installation on the populated 3.5 lab.
- Import failure/retry behavior and destination-bound
  checkpoints before claiming resumable/idempotent installation.
- Retention of MIT/WANDS notices, CC0 scope and disclosed media-provenance limits.
- The current release assets are hosted on GitHub with pinned manifests, but
  repository access is still required. Download success does not establish
  installation compatibility on another stack.

See `DATA_CARD.md`, `TERMS.md`, `WANDS-LICENSE.txt` and `CITATION.bib`. Original
WANDS relevance labels do not measure ranking on the rewritten catalog.
