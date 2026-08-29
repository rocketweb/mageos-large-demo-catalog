# Test catalogs

## Current deterministic catalog

The normal Mage-OS fixture does not load a Magento product catalog. It creates an empty Magento catalog-search index, then `assert-phase-one-baseline.php` writes eight synthetic product documents directly to the temporary OpenSearch physical index.

The eight documents use IDs `910001` through `910008` and cover five intentional relevance pairs:

| Query intent | Relevant fixture product | Distractor |
| --- | --- | --- |
| boots | trail footwear | boot decoration |
| red dress | evening garment | red dress poster |
| `MUG-001` | ceramic mug | other text matches |
| café table | ceramic mug | café table sign |
| winter coat | insulated outerwear | winter coat poster |

The query source has seven test rows across the fixture sequence. Six are safe terms and one is the deliberately private `private@example.com` term. Privacy filtering excludes the email address, so six safe terms can be selected. The end-to-end rating gate deliberately uses the five higher-popularity relevance queries listed above.

Phase 3 deletes one of the eight OpenSearch documents to prove stale-index and unavailable-product behavior. A completed contract run therefore ends with seven synthetic documents in the active test index.

These are not rows in `catalog_product_entity`. They bypass Magento product creation, EAV attributes, websites, categories, stock, prices, visibility, and Magento's indexing pipeline. No fixture container or persistent catalog is left running after cleanup.

## What the tiny catalog proves

The eight-document lane is intentionally small and deterministic. It is the right test for:

- exact baseline and candidate rankings;
- immutable hashes and idempotent persistence;
- complete human ratings with known expected answers;
- NDCG improvement and known-item regression gates;
- proposal acceptance and export boundaries;
- stale index and deleted-product behavior;
- exact cleanup preview identities;
- repeatable execution in CI.

It is not enough to evaluate:

- realistic Magento product mappings;
- ranking quality across many similar products;
- category, attribute, configurable-product, and long-tail interactions;
- rating-queue usability with realistic names and SKUs;
- indexing or query behavior at merchant-like catalog sizes;
- revenue impact or production capacity.

## Available official larger catalogs

Mage-OS 3.4.0 contains the Commerce performance-toolkit profiles in `setup/performance-toolkit/profiles/ce`. The official profile definitions are in the [Mage-OS 3.4.0 source tree](https://github.com/mage-os/mageos-magento2/tree/3.4.0/setup/performance-toolkit/profiles/ce), and the supported generator command is documented in [Adobe Commerce fixture-generation documentation](https://experienceleague.adobe.com/en/docs/commerce-operations/configuration-guide/cli/generate-data).

| Profile | Simple products | Configurable products | Variations per configurable | Categories |
| --- | ---: | ---: | ---: | ---: |
| Small | 800 | 16 | 24 | 30 |
| Medium | 24,000 | 640 | 24 | 300 |
| Large | 300,000 | 8,000 | 24 | 3,000 |
| Extra large | 600,000 | 16,000 | 24 | 6,000 |

The unmodified profiles also create non-catalog entities such as customers, administrators, and orders, and may change fixture configuration. They are suitable only for a disposable environment. The small profile is the only profile wired into this repository because it is large enough to exercise real product indexing without making medium or larger generation part of routine CI.

Before generation, the repository makes a derived `osrw-catalog-small.xml` next to the official profile. It preserves the official product, configurable variation, category, attribute-set, image, website, store, source, and stock counts. It sets administrator, customer, order, coupon, cart-rule, and catalog-rule counts to zero and removes the profile's configuration overrides. The official `small.xml` remains unchanged. This also avoids the unmodified profile's short generated admin passwords, which do not satisfy the current Mage-OS 3.4 admin password policy.

Magento also maintains an official [sample-data repository](https://github.com/magento/magento2-sample-data). That dataset is useful for recognizable demo products, but the built-in Mage-OS profile is preferred here because it ships with the exact pinned Mage-OS version, is credential-free, and has explicit scale targets.

## Recommended two-lane catalog strategy

Keep both lanes:

1. **Contract lane:** retain the eight direct OpenSearch documents for fast, exact, behavioral assertions.
2. **Catalog lane:** run the official Mage-OS small profile in a new disposable fixture, reindex through Magento, seed 100 query-history rows from real searchable product SKUs, and exercise snapshot, baseline, candidate, and rating-queue construction.

The larger lane adds realism without weakening the deterministic contract test. It does not manufacture relevance labels for the generated catalog, so it stops before claiming an NDCG winner. Meaningful ranking evaluation still requires a human to label the resulting product-query pairs.

## Running the larger catalog lane

The large-catalog runner first completes the normal deterministic qualification. It then derives and invokes the catalog-only form of the bundled `small.xml` profile, reindexes `catalogsearch_fulltext`, and verifies all of the following:

- at least 800 Magento product entities exist;
- at least 800 documents exist in the active OpenSearch product index;
- 100 distinct visible product SKUs are added to Magento query history;
- all 100 terms survive an immutable snapshot preview;
- the first five pass stock baseline capture;
- a name-boost candidate passes five-query validation;
- the baseline and candidate produce a non-empty human rating queue.

Start the pinned MySQL and OpenSearch services, choose a new path, and run:

```bash
composer fixture:mageos:up
MAGEOS_FIXTURE_ROOT=/private/tmp/osrw-mageos-large-catalog \
MAGEOS_PHP_BINARY=/opt/homebrew/opt/php@8.4/bin/php \
dev/ci/run-large-catalog.sh
composer fixture:mageos:down
```

The runner refuses to overwrite an existing fixture path. Do not point it at a development, staging, production, or otherwise valuable Magento installation. It installs fresh Mage-OS code and generates products, configurable variations, categories, attribute sets, images, stores, sources, and stock data solely inside the new disposable fixture.

The clean local qualification on August 27, 2026 measured 1,200 rows in `catalog_product_entity`: 800 standalone simple products, 384 simple variations, and 16 configurable parents. Magento indexed 816 storefront-visible product documents, which are the 800 standalone products plus the 16 configurable parents. The 384 variation products were not separate storefront search documents.

That run also selected all 100 product-derived queries, passed five baseline and five candidate validation searches, and produced 50 query-product pairs for human rating. The final JSON output reports these counts on every run. It reports `live_search_mutation: false` because this qualification lane deliberately stops before the separately permissioned activation action. The extension now has a private-lab activation path, but generated catalog data and fixture ratings are not sufficient evidence to activate a candidate automatically.

The August 27 styled Admin rehearsal repeated that lane in a new disposable fixture. At a 1920 by 1080 viewport, the Workbench rendered all 50 pairs as 150 rating choices and persisted exactly 50 fixture ratings in one immutable `LOCALLY_REVIEWED` judgment set. The 1,931-pixel queue initially scrolled its column headings out of view; the rating table now uses a scoped sticky header verified in the same fixture. This checks scale presentation and persistence mechanics only. It is not a substitute for representative products, approved relevance labels, or an observed merchant pilot.

## Getting more realistic than generated data

Generated fixtures prove scale and integration, not merchant relevance. The strongest later test would be a sanitized copy of a representative merchant catalog plus an approved, privacy-reviewed set of real search terms and human judgments.

That dataset should remain a separate private fixture. Before using it, obtain explicit approval for the exact source and destination, remove customer and order data, review product licensing and confidential attributes, scan search terms for personal data, and retain a documented disposal process. Do not commit merchant data or query text to this public repository.
