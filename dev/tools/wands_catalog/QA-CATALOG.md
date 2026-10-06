# QA fixtures for product behavior

This suite adds **127 named test products covering all six core Mage-OS product
types**. It fills the virtual, downloadable and grouped gaps, and adds cases for
configuration, options, pricing, inventory and visibility. Each product has a
stable `WANDS-QA-` SKU and an expected outcome in the test matrix.

**Status:** installed on the existing Studio and Comtom lab stores. Each WANDS
catalog now contains **107,815 records**. Store acceptance covers native records,
unsaved guest-cart behavior and rendered pages. Checkout, payment and post-order
download access need separate transaction qualification. The stable `catalog-2026.10.06` full release includes this suite as phase 6, with
fixture definitions, the test matrix and downloadable files. See the
[portable release installation guide](distribution/PRODUCTION_RELEASE.md).

| Product type | New records | Main purpose |
| --- | ---: | --- |
| Simple | 77 | Physical components, variant children, custom options, pricing, inventory and visibility |
| Virtual | 14 | Twelve service fixtures and two configurable children |
| Downloadable | 12 | PDF/ZIP files, samples, link selection, sharing and download limits |
| Configurable | 6 | Three attributes, sparse combinations, unavailable children and virtual variants |
| Bundle | 12 | Pricing, controls, shipment, quantities and physical/virtual components |
| Grouped | 6 | Physical, virtual and downloadable associations with independent quantities |
| **Total** | **127** | Parents and children counted separately |

The package reuses **16 approved JPEGs** and contains **three small local download
files**. It requires no model, GPU, API key or new image generation. There are no
new image annotations or measurements. The service names, prices and downloadable
contents are fictional test data.

Installation created 127 fixtures per store and updated or deleted **zero existing
products**. Tests saved no accounts, carts, orders or reservations, and changed no
global settings. Eleven QA categories were added; ancestor category counts and
timestamps changed to reflect them. Historical September downloads remain unchanged. The October full release
combines the expansion and QA suite.

| Acceptance surface | Studio | Comtom |
| --- | --- | --- |
| Native import | 127 new records; zero invalid rows or errors | 127 new records; zero invalid rows or errors |
| Product and cart behavior | 934 product checks, 202 cart cases and four cart compositions passed | 934 product checks, 202 cart cases and four cart compositions passed |
| Rendered products | All 97 visible fixtures and 30 hidden/disabled exclusions passed | All 97 visible fixtures and 30 hidden/disabled exclusions passed |
| QA category | Category and menu passed | Category and menu passed |
| Original-data preservation | Original products, stock and protected data unchanged | Original products, stock and protected data unchanged |
| Recovery evidence | SQL backup, row journals and exact inverse prepared | SQL backup, row journals and exact inverse prepared |

Comtom's final browser pass used the existing private SSH route and refreshed
`block_html` and `full_page` caches so the QA menu appeared. The checks exercise
the private lab ingress with its private CA bypass; they do not qualify public
TLS, uptime, checkout, payment or post-order download access.

[Documentation index](docs/README.md) · [Existing coverage audit](PRODUCT-COVERAGE.md)

## Choose a test

| Area | SKU suffix after `WANDS-QA-` | What to exercise |
| --- | --- | --- |
| Components | `COMPONENT-01` through `COMPONENT-12` | Available physical items; 11 is out of stock, 12 is disabled |
| Services | `VIRTUAL-01` through `VIRTUAL-12` | Taxable/non-taxable services, free service, unavailable and disabled services |
| Downloads | `DOWNLOAD-01` through `DOWNLOAD-12` | All 12 combinations of selectable/included links, finite/unlimited limits and sharing settings; single/multiple PDF/ZIP links with previews |
| Options | `OPTION-{TYPE}-{0,1}` | Optional/required versions of all ten native custom-option controls |
| Configurables | `CONFIG-FULL-THREE`, `CONFIG-SPARSE-THREE` | Eight complete or five sparse color/size/finish combinations; three deliberately absent combinations |
| Configurables | `CONFIG-OUT-OF-STOCK`, `CONFIG-DISABLED-CHILD` | Four color/finish children, including one unavailable child |
| Configurables | `CONFIG-VIRTUAL`, `CONFIG-PRICE-IMAGE` | Virtual children; differing physical variant prices and matching color/finish images |
| Bundles | `BUNDLE-01` through `BUNDLE-12` | Fixed/dynamic pricing with dropdown, radio, checkbox and multiselect; optional options, shipment together/separately, editable dropdown/radio quantities; mixed and virtual-only bundles |
| Grouped | `GROUPED-01` through `GROUPED-06` | Independent line prices, zero/default quantities, unavailable associations, virtual-only group and a downloadable association |
| Pricing | `PRICE-{CASE}` | Free, active/expired/future special prices, quantity tier, guest-group price, tax classes and merchandising links |
| Inventory | `STOCK-{CASE}` | Out of stock, both backorder modes, minimum/maximum quantity, increments, decimal quantity and unmanaged stock |
| Visibility | `VISIBILITY-01` through `VISIBILITY-04` | Not visible individually, catalog only, search only, and catalog plus search |

The configurable families also contain 27 hidden `CHILD-*` records. One grouped
fixture uses a downloadable product with included links, avoiding an unselected
link requirement. Checkbox/multiselect bundle quantities are fixed; customer
quantity changes are exercised on dropdown/radio controls.

Use the package's `test-matrix.json` for exact SKUs and expectations. For example:

- `OPTION-FIELD-0` has a $200 base price and an optional $10 fixed charge.
- `OPTION-FIELD-1` requires input and adds 10% of the $200 base price, or $20.
- `PRICE-TIER-ALL` is $100 per unit at quantity one and $70 at quantity five.
- `PRICE-GROUP-GUEST` tests a quantity-one price of $80 for customer group ID 0.
- `CONFIG-FULL-THREE` requires all three choices and has eight combinations.
- `CONFIG-SPARSE-THREE` exposes the same axes with only five valid combinations.

Expected prices are before tax, currency conversion and store price rules.
Scheduled-price expectations use October 6, 2026 as their reference date.

## What remains to qualify

The suite includes physical-only, virtual-only, download-only and mixed-cart
scenarios. Native cart checks exercise shipping requirements, required selections,
option charges, selected variants, availability and quantity rules. Rendered-page
checks exercise controls and image loading. These checks use unsaved guest quotes;
they do not complete orders.

Download access after a qualifying order, finite download counters, sharing,
checkout and payments need separate transaction tests and cleanup. Inventory
sources, additional websites/stores, currencies, tax rules, customer groups and
price rules are store configuration, not additional product types. This package
does not provision them. Extension-specific types such as subscriptions or gift
cards require separate fixtures for the actual installed extension.

## Developer specification

### Inputs and reproducibility

`build_qa_catalog.py` is a standard-library Python recipe. It makes no store,
network or model calls. It requires the private accepted measurement-free expansion
export, checks its manifest pin and selected input/image hashes, and refuses an
existing output directory. The accepted export and resulting media are ignored
runtime artifacts; cloning the source repository does not download them.

Recorded accepted export:

```text
var/catalog-expansion-20260918/accepted-export-completion-20261003
manifest SHA-256:
4c276a38a325a682c1537c5932c0c24c51dc2732a220cac19faec6646174c386
```

Build from the repository root, choosing a fresh output directory:

```sh
python3 dev/tools/wands_catalog/build_qa_catalog.py \
  --source var/catalog-expansion-20260918/accepted-export-completion-20261003 \
  --source-sha256 4c276a38a325a682c1537c5932c0c24c51dc2732a220cac19faec6646174c386 \
  --output var/catalog-qa-rebuild

python3 dev/tools/wands_catalog/build_qa_catalog.py --verify var/catalog-qa-rebuild
```

The recipe selects twelve physical source classes and an accepted complete
color/finish family. Physical variant imagery follows its source color and finish;
size-only variants may share illustrations. Media lineage records the source SKU,
file and hash. Virtual/downloadable products need no physical product image.

Download files are deterministic, original fixtures: a one-page planning PDF,
a one-page sample PDF and a ZIP containing a disclosure plus synthetic materials
JSON. They contain no account data, executable scripts or third-party assets.
The recipe prohibits remote download URLs and paths outside its download namespace.

### Package contract

| File or directory | Contract |
| --- | --- |
| `manifest.json` | Recipe, source pin, type counts, image/download counts and every member's SHA-256/byte count |
| `fixtures.json` | Canonical product rows, expected outcomes and source SKUs |
| `data/products.csv` | All 127 native import rows, with dependencies validated together |
| `test-matrix.json` | Per-SKU cases, four cart scenarios and explicitly pending store scenarios |
| `media-lineage.json` | Exact accepted JPEG provenance for each illustrated fixture |
| `media/import/wands-qa/` | Sixteen reused approved images in a fixture namespace |
| `media/import/wands-qa-downloads/` | Three local PDF/ZIP assets referenced by download links and samples |
| `installation-proposal.json` | Exact additive scope, two destinations, required apply checks and inverse plan |

The verifier checks hashes, member inventory, CSV/fixture agreement, type counts,
unique SKUs/URLs, configurable combinations, dependency closure and required
assets. Grouped, configurable, bundle and merchandising links stay within the QA
suite. Reused JPEGs are copied into the package; original media remains untouched.

The six native product types use the installed platform's import contracts:
`associated_skus` for grouped products, `downloadable_links`/`downloadable_samples`
for files, `configurable_variations` for axes, `bundle_values` for selections, and
`custom_options` for controls. Tier prices use `_tier_price_*` fields. CSV quoting
preserves nested separators, including the file-option `pdf,txt` extension list.

### Native validation

`validate_qa_catalog.php` accepts only the two existing installation roots, requires
a trusted manifest SHA-256 and verifies all package bytes before bootstrapping
Mage-OS. It refuses an existing `WANDS-QA-` SKU or a changed 107,688-record WANDS
baseline. It stages a private temporary CSV, calls native `validateSource()`, rolls
back the staging transaction, removes the CSV and compares 32 database table
fingerprints. **It never calls `importSource()`.**

Run the Studio check with its PHP 8.4 binary:

```sh
/opt/homebrew/opt/php@8.4/bin/php -d memory_limit=4G \
  dev/tools/wands_catalog/validate_qa_catalog.php \
  --root=/Users/matt/code/mageos-latest \
  --package=/Users/matt/code/mage-os-large-demo-catalog/var/catalog-qa-20261006/candidate-v5 \
  --manifest-sha256=7fac73094a043c9fa4b11eed9def21d56e59a7dacb83ae4e29af332295262836
```

Validation can write normal framework cache/log files and temporarily writes
native staging rows. Existing staging content is restored by rollback. A native
database auto-increment counter may advance despite rollback. Fingerprints cover
product data, options, relationships, categories, EAV option labels, stock,
configuration, customers, orders, quotes, reservations and import staging/history.
An unchanged report establishes these checked table contents, not every file or
table in the installation. A native validation pass also does not establish file
delivery or successful product creation.

### Recorded verification and installation boundary

Final candidate:

```text
var/catalog-qa-20261006/candidate-v5
manifest SHA-256:
7fac73094a043c9fa4b11eed9def21d56e59a7dacb83ae4e29af332295262836
```

Two independent builds of this candidate have matching manifest and member
hashes. The tooling regression run passed **882 tests with no skips**, including
14 focused QA-recipe tests and native SQLite journal-compensation checks.
The focused tests cover dependency closure, source/package tampering, nested
CSV payloads, downloadable selection flags, website-scoped tiers and options.

```sh
python3 -m unittest discover -s dev/tools/wands_catalog/tests -p test_qa_catalog.py -v
```

### Installation and runtime tools

| Tool | Purpose |
| --- | --- |
| `qa_database_backup.php` | Private destination SQL backup with hash receipt |
| `expansion_catalog_journal.php` | Before/after row journals, including custom options and downloadable tables |
| `install_qa_catalog.php` | Manifest and baseline checks, dry run, additive import and interruption guard |
| `reindex_qa_catalog.php` | Refresh stock, price, attribute, category and search indexes for only 127 new IDs |
| `test_qa_store.php` | 934 product checks, 202 unsaved cart cases and four cart-composition checks |
| `verify_qa_browser.py` | Isolated browser checks of product identities, controls, selections, images and QA navigation |
| `build_expansion_inverse.py`, `restore_expansion_catalog.php` | Exact changed-row compensation with drift checks |

The importer validates all 127 rows and reports zero invalid rows or errors.
Its native processed-entity counter includes import phases; database membership
and type counts establish the actual number of created products.

Download selection flags and section titles must be embedded in the native
`downloadable_links` payload. Top-level CSV attributes alone are insufficient:
the native importer derives these settings from the link payload. Tier prices
are scoped to the WANDS website so the host store's default base currency does
not convert test prices unexpectedly. Both cases have regression tests.

Unsaved price checks initialize quote addresses and collect totals. They use
USD and guest group 0 without a customer address. File-option positive cases use
native existing-file metadata; they do not exercise a browser HTTP upload.
No orders, payments, reservations or download entitlements are created.

Before installation, each store received a private full SQL backup and a catalog
journal. Exact original IDs, website assignments, product rows, stock and
protected customer/transaction tables are checked after installation. A row
inverse preserves unchanged data and includes the two ancestor-category changes.
The compensator refuses subsequent drift. It is a recovery tool, not permission
to remove fixtures after outside data begins depending on them. Derived indexes
and owned media require reconciliation after compensation.

Private destination evidence is under `var/wands-qa-install-20261007/` in each
existing store; the repository's ignored acceptance receipts are under
`var/catalog-qa-20261006/install-20261007/`. These directory names are identifiers;
receipt timestamps identify when the operations occurred. Do not publish backups
or private row journals. Native imports cannot be blindly resumed: inspect the
apply marker and exact partial journal before recovery or another attempt.

The pre-install validation command above now refuses the installed QA SKUs, as
intended. For acceptance after installation, use the pinned package and current
runtime test tool instead:

```sh
/opt/homebrew/opt/php@8.4/bin/php \
  dev/tools/wands_catalog/test_qa_store.php \
  --root=/Users/matt/code/mageos-latest \
  --package=/Users/matt/code/mage-os-large-demo-catalog/var/catalog-qa-20261006/candidate-v5 \
  --manifest-sha256=7fac73094a043c9fa4b11eed9def21d56e59a7dacb83ae4e29af332295262836
```

### Platform references

- [Adobe: virtual products](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/types/product-create-virtual)
- [Adobe: downloadable products](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/types/product-create-downloadable)
- [Adobe: grouped products](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/types/product-create-grouped)
- [Adobe: bundle products](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/types/product-create-bundle)
- [Adobe: custom options](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/settings/settings-advanced-custom-options)

The local native check uses the installed Mage-OS implementation as the authority
for this candidate's CSV validation. Platform documentation describes behavior to
test, not successful execution of these particular fixtures.
