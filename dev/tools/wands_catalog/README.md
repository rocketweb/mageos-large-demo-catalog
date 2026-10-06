# WANDS catalog tooling

These tools build synthetic catalog data, generate and review product images,
prepare imports, and verify installations. The completed expansion has **107,688
records before the separate QA extension**. Both existing lab stores now have
**107,815 WANDS records**, including the 127-product QA suite. The stable `catalog-2026.10.06` full download contains the same 107,815 records
and approved expansion media. September profiles remain historical prereleases.

## Choose your starting point

| You want to | Start here |
| --- | --- |
| Install a prepared catalog | [Repository quick start](../../../README.md#quick-start), then [recipient installation](distribution/PRODUCTION_RELEASE.md) |
| Understand the completed expansion | [Completion record](EXPANSION-CHECKPOINT.md) and [implementation guide](docs/EXPANSION.md) |
| Check product-type and test coverage | [Coverage audit](PRODUCT-COVERAGE.md) and [127-product QA suite](QA-CATALOG.md) |
| Review or correct images | [Human image review](HUMAN-IMAGE-REVIEW.md) |
| Operate an admitted remote renderer | [Mac mini](MINI-WORKER.md) or [Linux laptop](LAPTOP-WORKER.md) |
| Build and distribute an immutable release | [Release building](distribution/BUILDING.md) and [sharing checklist](../../../SHARING.md) |
| Find a pilot, acceptance result or recovery record | [Complete documentation index](docs/README.md) |

A prepared catalog needs no GPU or image generator. Running development tools
requires their pinned inputs and appropriate environment. The root Composer
project describes the historical development store; it is not a catalog installer.

The catalog provides scale and image variety. The installed QA extension adds
virtual, downloadable and grouped products plus configuration, custom-option,
pricing and inventory cases. The two stores contain all six core product types.
See the coverage audit before using catalog size as evidence of complete commerce testing.

## Developer map

| Path | Responsibility |
| --- | --- |
| `app/code/RocketWeb/LabCatalog/` | Provisioning, import, stock preservation and navigation |
| `dev/tools/wands_catalog/` | Data recipes, model workers, review, export and existing-store coordination |
| `dev/tools/wands_catalog/tests/` | Python regression and native-PHP/HTTPS fixtures |
| `dev/tools/wands_catalog/distribution/` | Portable release builder, verifier, downloader and fresh-install checks |
| `dev/tools/wands_catalog/docs/` | Current implementation reference, index and preserved histories |
| `build_qa_catalog.py`, `install_qa_catalog.php`, `test_qa_store.php` | Pinned additive QA fixtures, guarded installation and unsaved-cart acceptance |
| `var/`, `pub/media/` | Private runtime evidence and generated media, excluded from Git |
| `packages/` | Separate Workbench snapshot; not the catalog's source of truth |

Paths in this table are relative to the repository root. Run development commands
there unless a guide explicitly says to run in the destination Mage-OS root.

## Data, generation and installation boundaries

The current pipeline separates frozen data candidates, generated images,
accepted exports and installed stores. A generation return starts central review;
a clean transfer or OCR result does not prove product correctness. Accepted media
must also match product identity, material, variant color and included components.
All generators share the ban on visible measurements, writing, numbers, rulers,
diagrams, logos and watermarks. Dimensions may remain in structured product data.

The [expansion guide](docs/EXPANSION.md) documents the source modules, job ledger,
sealed remote packets, corrections, file contracts and final verification.
Workers are stopped for the completed run. Historical process IDs and timings in
older notes are not instructions to restart generation.

The published release installer expects an empty, dedicated lab. The two-store
expansion coordinator is an existing-store update workflow with destination
snapshots, backups and inverse journals. Do not exchange these procedures or
blindly rerun an interrupted native import. Native `--validate-only` also writes
staging tables. Review the exact procedure and destination before execution.

## Run the checks

The Python suite can run with Python 3.11+. To include native PHP fixtures and
the real local HTTPS download-resume check, supply PHP 8.4 and allow loopback ports:

```sh
WANDS_TEST_PHP=/absolute/path/to/php WANDS_TEST_HTTPS=1 \
  python3 -m unittest discover -s dev/tools/wands_catalog/tests \
  > /tmp/wands-tests.log 2>&1
```

Inspect the exit status, final test totals and skipped checks. The recorded
October 6 QA tooling run passed 882 tests, with no skips. The earlier module suite passed 13
PHP unit tests with 39 assertions. Those are dated results, not a guarantee about
later changes. See [contribution checks](../../../CONTRIBUTING.md) for setup and
module-test commands. Unit tests do not replace native import, stock, media or
rendered storefront acceptance.

## Attribution and earlier recipes

Wayfair WANDS supplies the original corpus. Synthetic prices, stock, dimensions,
descriptions, families and images are lab additions. Original relevance judgments
do not qualify search ranking over rewritten products. Keep the upstream MIT
notice and scholarly citation with distributions; see
[license scope](../../../NOTICE.md) and the [dataset card](distribution/DATA_CARD.md).

The [earlier workflow reference](docs/LEGACY-WORKFLOW.md) retains original base
preparation, generation and merchandising examples, the WANDS citation, and
September progress notes. Use it when reproducing those exact historical inputs.
For other evidence, use the [documentation index](docs/README.md).
