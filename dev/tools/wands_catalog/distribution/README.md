# WANDS catalog for Mage-OS Lab

A large, synthetic home-and-furniture catalog for testing search, navigation,
configurable products, bundles, prices, inventory and product media.

This is a private integration candidate, not an official Mage-OS or Wayfair
release. Starter and full profiles passed fresh-install testing on Mage-OS 3.5.0
with the stock Luma theme. See the [acceptance result](ACCEPTANCE.md).
Mage-OS 3.4 was not tested; publication remains separate.
Code and authored data use MIT; generated images use CC0 where rights are held.
Do not use this candidate in a customer store.

## What recipients need

A dedicated, empty Mage-OS lab with PHP 8.4, USD currency, the standard product
types and Python 3.11 or newer for offline verification. A GPU, model service,
API key, Hyvä theme, Koti sample data and hybrid search are not required.

Choose one profile on a fresh installation:

- **Starter:** selected corrected families plus a living-room bundle, including
  every child and selection dependency. Counts are in `data/counts.json`.
- **Full:** 53,844 records, including disabled legacy variants. This is a derived
  catalog, not the original 42,994-product WANDS benchmark.

Each profile includes `catalog.tar`, `module.tar`, separate `media-*.tar` files,
`manifest.json`, and the standalone `release.py` verifier. Images are not in Git
or Git LFS. No database, customer, order, credential, vendor or theme export is
included. The candidate is assembled from saved inputs, not a live database dump.

## Verify offline first

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

The companion [download tool](DOWNLOADS.md) provides pinned, resumable HTTPS
downloads once an approved mirror is available. It is available in source tooling;
the immutable rc2 archives predate it. Offline copying remains supported.
Automatic interrupted-import recovery is not supported in this candidate.

## Integration procedure for the clean-install test

The following procedure was exercised on a fresh Mage-OS 3.5.0 installation,
including the ownership and menu steps noted below. Back up the empty installation first.
Confirm zero products, no existing `wands` website/store and no other sample data.
Do not install this over an existing WANDS catalog or switch starter to full in
place. On interruption, restore the empty baseline before retrying.

Run the read-only destination preflight from extracted tooling before installing
the module or provisioning. It refuses any existing products or WANDS store codes
and logs exact proposed product/media counts. It does not create a backup or
grant import approval:

```sh
php ./wands-staging/tools/preflight.php --magento-root=/path/to/empty/mageos \
  --data-dir=./wands-staging/data --log-file=./preflight.log
```

1. Copy the staged `module/` contents into a new
   `app/code/RocketWeb/LabCatalog/` directory. The module has its own Composer
   metadata; do not use this repository's project-level Composer files.
2. Enable `RocketWeb_LabCatalog`, run `setup:upgrade` and the normal compilation
   steps for the recipient's deployment mode. These are database writes.
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
4. Copy staged `data/` to `var/wands-lab/data/`, and staged `media/wands-lab/` to
   `pub/media/import/wands-lab/`. Provisioned attributes must contain every label
   in `data/attribute-options.json` before product import.
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

   `--validate-only` validates without changing products but writes native import
   staging tables. Dependent parents/bundles cannot be validated as if their
   children already existed. Do not use bundle reconciliation on a fresh install.
6. Run `lab:wands:curate-navigation` to limit the menu to the ten main departments
   without deleting categories or product assignments. Run Magento commands as
   the web filesystem owner so generated code remains writable by PHP-FPM.
7. Reindex, clean relevant caches, then compare exact type/link/selection/media
   counts with `data/counts.json`. Check configurable options, child price/image
   switching, bundle selections and calculated prices, stock scenarios, search
   and product images on desktop and mobile.

The original importer commands remain general-purpose; they do not automatically
enforce the empty-store requirement. The clean-install operator must check it.
Uninstalling the module does not delete data. Never use a whole-store SQL deletion
as a catalog uninstaller.

## Acceptance still required before public handoff

- Separate testing before claiming Mage-OS 3.4 or clean-install Hyvä compatibility.
- Import failure/retry behavior and destination-bound
  checkpoints before claiming resumable/idempotent installation.
- Retention of MIT/WANDS notices, CC0 scope and disclosed media-provenance limits.
- Approved hosting, immutable release identifiers and a trusted checksum channel.

See `DATA_CARD.md`, `TERMS.md`, `WANDS-LICENSE.txt` and `CITATION.bib`. Original
WANDS relevance labels do not measure ranking on the rewritten catalog.
