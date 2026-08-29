# Mage-OS 3.4 qualification fixture

This public fixture installs `mage-os/project-community-edition` 3.4.0 on PHP 8.4 and verifies the module against MySQL 8.4 and the exact pinned OpenSearch 3.8 image. It has no private Composer dependency.

The fixture compiles dependency injection, verifies declarative schema status, calls Search Relevance through the installed module and Mage-OS client, creates the stock catalog-search index, and runs the baseline capture harness through two real Mage-OS request builders:

- the storefront `quick_search_container` path used by the stock catalog-search collection
- the `graphql_product_search` path built by `Magento_CatalogGraphQl`

Each surface uses two collision-resistant sentinels and five validation queries. The emitted evidence contains only hashes, template digests, and JSON pointer paths. It does not contain query text.

The runner then executes the complete Phase 1 persistence gate:

- preview, privacy inspection, explicit approval, and reconstruction of an immutable query snapshot
- stock baseline capture against the alias-resolved physical index
- bounded field-boost candidate creation and five-query validation
- a fresh top-ten human rating union and immutable imported judgment
- materialization or exact reuse of the owned query set, baseline configuration, candidate configuration, and judgment
- one pairwise and two pointwise experiments, result polling, and Search Relevance validation
- local NDCG@10, judged-coverage, known-item, improvement-threshold, and index-freshness gates
- explicit fixture acceptance of otherwise-winning evidence
- content-addressed review-only proposal persistence and export safety assertions
- accepted-run resumability without duplicate local or remote artifacts
- accepted-winner activation, runtime field-boost application, duplicate-apply rejection, append-only audit, and exact rollback to stock

It also executes the Phase 3 technical gate:

- before-and-after product movement evidence and a regression inbox
- deleted-product reconstruction as explicit unavailable context
- stale index evidence and stale existing-proposal rejection
- merchant-curated category and brand metadata with persisted provenance and remote query-set fields
- scheduled query snapshot preparation that remains a local, unapproved draft
- unchanged remote evaluation bindings during scheduled work
- exact-identity cleanup preview for all seven bound fixture resources
- no exposed remote cleanup delete action

The fixture acceptance is deterministic test data. It proves the technical acceptance gate, not merchant usability or revenue impact. The activation assertion briefly applies the fixture winner inside the disposable installation, proves the runtime query change, rejects reapplying the exact current candidate, then writes an audited rollback and verifies the exact stock query is restored before later assertions run.

From the repository root:

```bash
docker compose -f dev/ci/compose.yaml up -d --wait
MAGEOS_PHP_BINARY=/opt/homebrew/opt/php@8.4/bin/php dev/ci/run.sh
docker compose -f dev/ci/compose.yaml down -v
```

The runner refuses to overwrite an existing fixture directory. Set `MAGEOS_FIXTURE_ROOT` to choose a new disposable path. The fixed service credentials are local and CI-only. The five assertions are `assert-baseline-capture.php`, `assert-phase-one-snapshot.php`, `assert-phase-one-baseline.php`, `assert-live-activation.php`, and `assert-phase-three.php`; `run.sh` invokes all of them.

## Larger real-product catalog

The default gate uses eight deterministic documents written directly to OpenSearch. It does not create Magento catalog products. Keep that lane for exact contract assertions.

An opt-in runner derives a catalog-only variant of the official Mage-OS 3.4.0 small performance profile after the deterministic gate, reindexes through Magento, seeds 100 query-history rows from visible product SKUs, and verifies snapshot, baseline, candidate, and rating-queue construction against the larger index:

```bash
docker compose -f dev/ci/compose.yaml up -d --wait
MAGEOS_FIXTURE_ROOT=/private/tmp/osrw-mageos-large-catalog \
MAGEOS_PHP_BINARY=/opt/homebrew/opt/php@8.4/bin/php \
dev/ci/run-large-catalog.sh
docker compose -f dev/ci/compose.yaml down -v
```

The derived profile keeps the official product, variation, category, attribute-set, image, store, source, and stock counts. It sets administrators, customers, orders, coupons, cart rules, and catalog rules to zero and removes the official profile's configuration overrides. A clean local run created 1,200 Magento product entities and 816 storefront-indexed product documents. Use only a new disposable fixture path. The runner refuses to overwrite an existing directory. See [../../docs/TEST-CATALOGS.md](../../docs/TEST-CATALOGS.md) for exact sizes, limitations, and the two-lane test strategy.

## Private Hyvä qualification

The same disposable fixture can qualify an exact licensed Hyvä version without storing its repository URL or credentials in this repository. Composer authentication must already exist in the operator's credential store.

```bash
OSRW_HYVA_REPOSITORY_URL=https://licensed-repository.example/ \
OSRW_HYVA_VERSION=1.5.2 \
MAGEOS_FIXTURE_ROOT=/private/tmp/osrw-mageos-hyva \
MAGEOS_PHP_BINARY=/opt/homebrew/opt/php@8.4/bin/php \
dev/ci/run.sh
```

The URL must use HTTPS without embedded credentials, and the version must be exact. This opt-in lane installs and activates `Hyva/default`, verifies `Hyva_Theme`, then runs the same installed-module transport, storefront, and GraphQL baseline gates. The public CI lane remains free of private dependencies.
