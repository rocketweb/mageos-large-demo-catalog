# Expanded catalog release

Release `catalog-2026.10.06` contains **107,815 product records**, all six core
Mage-OS product types and the approved, measurement-free expansion media. It is
a stable release of synthetic lab data for testing. Prices, inventory, dimensions
and descriptions are fictional. Images are illustrations, not fit guarantees.

| Included | Scope |
| --- | ---: |
| Simple products, including children | 103,720 |
| Configurable parents | 4,001 |
| Bundles | 62 |
| Virtual products | 14 |
| Downloadable products | 12 |
| Grouped products | 6 |
| Named QA fixtures within those counts | 127 |
| Distinct accepted JPEG contents | 95,401 |
| Packaged JPEG files | 95,417, including 16 reused QA copies |
| QA downloadable files | Three small fictional PDF/ZIP files |
| Configurable parent-child links | 27,763 |

Use an **empty, dedicated Mage-OS lab**, backed up before import. The release
contains a portable module, six ordered import phases, media, QA definitions,
expected test outcomes, licenses and checksum inventories. It contains no database
dump, customer/order records, credentials, model weights, vendor tree or theme.
A GPU, image generator, API key and Hyvä theme are not needed.

## Acceptance and practical limits

The expansion and final QA CSVs were installed on the two existing Studio and
Comtom labs. Each store passed **934 product checks, 202 unsaved guest-cart cases,
four cart compositions, 97 visible product pages and 30 hidden/disabled URL
exclusions**. Original products and stock were preserved. The package carries a
sanitized `docs/INSTALLATION_ACCEPTANCE.json`; private backups and rollback
journals stay with the operators.

This release packages the exact accepted import CSV and media bytes, with a merged
count inventory. Archive and member checksums are verified separately. A third
store was not created, so there is no new empty-store end-to-end acceptance of
these release archives. Earlier September recipient tests qualify their earlier
pins only. Mage-OS 3.5 and PHP 8.4 are the recorded lab runtime; other versions
need recipient qualification.

Checkout, payments, real browser file uploads, post-order download access,
download counters and multi-website/currency/tax-rule configurations remain
unqualified. Cart tests use unsaved guest USD quotes and existing-file metadata
for file options. Comtom browser checks used private SSH ingress and a private CA
bypass; they do not establish public TLS or uptime. Stable release status does
not certify a customer production store.

## Download and verification

Get the release's `full` and `toolkit` assets using the authenticated helper
hashes and manifest pins in the repository's root README or trusted release notes.
The GitHub automatic source archive does not include the product media. Keep the
three helpers together; use Python 3.11 or newer and anonymous access:

```sh
python3 github_download.py --anonymous --repo rocketweb/mageos-large-demo-catalog \
  --tag catalog-2026.10.06 --profile toolkit --cache-dir ./cache \
  --manifest-sha256 TRUSTED_TOOLKIT_PIN
python3 release.py ./cache/TRUSTED_TOOLKIT_PIN \
  --manifest-sha256 TRUSTED_TOOLKIT_PIN --extract ./toolkit
python3 github_download.py --anonymous --repo rocketweb/mageos-large-demo-catalog \
  --tag catalog-2026.10.06 --profile full --cache-dir ./cache \
  --manifest-sha256 TRUSTED_FULL_PIN
python3 release.py ./cache/TRUSTED_FULL_PIN \
  --manifest-sha256 TRUSTED_FULL_PIN --extract ./wands-staging
```

Replace the pin placeholders before running. Verify helper hashes before executing
code. The downloader resumes verified/partial transfers; the importer does not
resume. Extraction requires a new directory and refuses unsafe archive members.
Logs are `wands-download.log` and `cache/<pin>/verification.log`. Budget roughly
5.5 GB per download or extraction copy, plus Magento's imported media, generated
image cache, database and search index.

## Install into an empty lab

Run PHP in the destination environment as its web filesystem owner. Container
users must make staging and toolkit paths available inside the container. Stop
and inspect the log after any nonzero command. Back up the empty database and
application configuration; restore that baseline before retrying an interrupted
import. Do not import this full profile over an existing medium/full catalog.

From the download directory, run the current toolkit's read-only preflight:

```sh
php ./toolkit/tools/preflight.php --magento-root=/path/to/empty/mageos \
  --data-dir=./wands-staging/data --log-file=./preflight.log
```

It counts all 107,815 proposed inserts across phases 1, 2, 3 and 6, and refuses
existing products or conflicting WANDS website/store codes. It does not back up
or write to the destination database.

Then switch to the Mage-OS root. Replace the staging path and storefront URL:

```sh
set -e
WANDS_STAGE=/path/to/wands-demo/wands-staging
test ! -e app/code/RocketWeb/LabCatalog
mkdir -p app/code/RocketWeb/LabCatalog
cp -R "$WANDS_STAGE/module/." app/code/RocketWeb/LabCatalog/
php bin/magento module:enable RocketWeb_LabCatalog > var/log/wands-enable.log 2>&1
php bin/magento setup:upgrade > var/log/wands-setup.log 2>&1
php bin/magento lab:wands:provision --base-url=https://catalog.example.test/ \
  > var/log/wands-provision.log 2>&1
mkdir -p var/wands-lab/data pub/media/import
cp -R "$WANDS_STAGE/data/." var/wands-lab/data/
cp -R "$WANDS_STAGE/media/." pub/media/import/
```

The module provisions the WANDS website, standard attributes and required option
labels. Configure the web server with `MAGE_RUN_TYPE=website` and
`MAGE_RUN_CODE=wands`. Provisioning does not set DNS, TLS or routing. Production
mode needs its normal DI compilation and theme static-content deployment. Theme
packages are installed separately. Use USD and the standard tax classes `None`
and `Taxable Goods` for these fixtures.

Import base products, parents, bundles, media and merchandising in order. The
current module uses native `append`, preserving relationships during media
updates. Do not use the old rc2 module or existing-store reconciliation flags.

```sh
set -e
for phase in 1-simple 2-configurable 3-bundle 4-media 5-merchandising; do
  php bin/magento lab:wands:import --file="var/wands-lab/data/$phase.csv" \
    > "var/log/wands-$phase.log" 2>&1
done
php bin/magento lab:wands:curate-navigation > var/log/wands-navigation.log 2>&1
php bin/magento lab:wands:import --file=var/wands-lab/data/6-qa.csv \
  > var/log/wands-6-qa.log 2>&1
php bin/magento indexer:reindex > var/log/wands-reindex.log 2>&1
php bin/magento cache:clean > var/log/wands-cache.log 2>&1
```

Curate navigation **before phase 6**: the curator exposes the eleven base
departments and would hide the new QA Fixtures menu if run afterward. Phase 6
creates eleven QA categories and includes its own physical images and download
links. Preserve all three media directories: `wands-expanded`, `wands-qa` and
`wands-qa-downloads`. Do not flatten filenames or remove download payload fields.
Native `--validate-only` writes import staging tables; it is not a read-only
preflight and cannot validate parents before their children exist.

Check `data/counts.json` against native records, relationships, media roles and
visibility. Open the QA Fixtures category, check custom-option controls, sparse
configurable combinations, variant images/prices, bundle selections, grouped
quantities, stock limits and downloads. Inspect image load failures and menu/search
behavior on the installed theme. Download verification alone does not establish
successful Magento import or storefront acceptance.

## Developer data contract

Phases 1, 2 and 3 introduce expansion products; phases 4 and 5 add media and
merchandising links; phase 6 introduces the 127 closed QA fixture dependencies.
`data/qa/fixtures.json` holds canonical fixture definitions and expectations;
`data/qa/test-matrix.json` lists exact SKUs, inputs and expected outcomes.
`data/qa/media-lineage.json` maps reused QA illustrations to accepted source SKUs.
The top-level manifest records archive/member hashes, source-file hashes, the
build baseline commit and both input manifest pins. The baseline commit alone
is not a claim that an uncommitted build is reproducible.

All QA SKUs begin `WANDS-QA-`. Physical products use accepted illustrations;
virtual and downloadable products intentionally may have no image. Scheduled
pricing fixtures use October 6, 2026 as their reference date and need controlled
store time for repeatable future tests. All six native types are represented;
extension-specific types, inventory sources, customer groups, price rules and
transaction behavior require separate configuration and tests.

The published portable module imports this data in a new lab. Repository QA
installation/rollback helpers are guarded operator tools for the two existing
stores and are not general-purpose recipient installers. Source guides describe
those tools separately. Old September profiles remain immutable historical
releases; their assertions and galleries do not qualify this new release.

## Data rights and provenance

Retain [distribution terms](TERMS.md), the [WANDS MIT notice](WANDS-LICENSE.txt),
[BibTeX citation](CITATION.bib), Rocket Web MIT notice and [CC0 notice](CC0-1.0.txt).
Generated media uses CC0 only where Rocket Web holds rights; third-party rights
are not waived. Historical model/reference provenance is incomplete. The derived
catalog is not the original WANDS benchmark, and original relevance labels do
not validate search ranking on rewritten products. See the [dataset card](DATA_CARD.md).
