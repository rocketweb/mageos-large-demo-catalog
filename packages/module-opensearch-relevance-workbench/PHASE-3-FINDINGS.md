# Phase 3 Merchant Evidence and Draft Scheduling Findings

Date: 2026-08-27

These findings apply to the exact disposable Mage-OS fixture described below. They establish the Phase 3 technical deliverables and two technical exit criteria. They do not establish merchant usability, production readiness, revenue lift, or completion of the required pilot observation.

## Status

All six Phase 3 deliverables in `IMPLEMENTATION-PLAN.md` are locally implemented and verified:

- before-and-after product grids with movement classification
- known-item and regression inbox evidence
- merchant-curated scalar query metadata with provenance
- scheduled draft snapshot preparation
- stale-index alerts and rerun safety
- bounded owned-resource cleanup preview

The technical exit criteria pass:

- product resolution preserves stale or deleted documents as unavailable context
- scheduled work cannot spend money or apply configuration

The final Phase 3 exit criterion remains open: monthly workflow usability must be observed in a real pilot. Deterministic fixture and browser acceptance cannot substitute for merchant observation. Phase 4 release-candidate work has therefore not started.

Phase 2 also remains independently blocked. A fresh check of the official Search Relevance tags on 2026-08-27 still found `3.8.0.0` as the newest semantic tag. The newer `custom_3.4` tag points to a dependency-only commit, not a qualified replacement distribution for the missing LLM runtime contracts. The LLM judgment and calibration path was not simulated or weakened.

## Qualified fixture

- Mage-OS: 3.4.0
- PHP: 8.4.24
- MySQL: 8.4
- OpenSearch: 3.8.0
- Search Relevance plugin: 3.8.0.0
- ML Commons plugin: 3.8.0.0
- storefront target alias: `magento2_product_1`
- resolved fixture physical index: `magento2_product_1_v3`

The final run began with a new fixture directory and empty MySQL and OpenSearch volumes. Declarative schema status, dependency-injection compilation, catalog-search reindexing, installed-module transport, both request-surface baseline assertions, the complete Phase 1 workflow, and the Phase 3 assertion passed.

## Product evidence and stale safety

Completed experiment evidence now preserves the baseline and candidate document identities per query. The Admin workbench reconstructs current catalog context and classifies each product as:

- `MOVED_UP`
- `MOVED_DOWN`
- `UNCHANGED`
- `ADDED`
- `DROPPED`

Known-item regressions remain a separate persisted inbox rather than being inferred from the current catalog. Product context has explicit `AVAILABLE`, `PARTIAL`, and `UNAVAILABLE` states. If a stored document no longer exists, the grid keeps its document identity and displays `Product unavailable` instead of failing the report.

The clean fixture removed document `910001` after a fresh evaluation. Evidence changed from `FRESH / AVAILABLE` to `STALE / PARTIAL`, and the deleted document remained visible as unavailable context.

Proposal creation rechecks the frozen baseline, store, captured target alias, physical index, and current index evidence before candidate work and before returning an existing proposal. The clean fixture proved that a previously created proposal cannot bypass the stale-index gate.

## Larger catalog qualification

The deterministic fixture uses eight synthetic documents to preserve exact ranking and stale-product assertions. A separate clean qualification used a catalog-only derivative of the Mage-OS 3.4.0 small performance profile and Magento's real catalog indexing pipeline.

That run reported:

- 1,200 rows in `catalog_product_entity`
- 816 storefront-indexed OpenSearch product documents
- 100 product-derived query-history rows selected into one immutable snapshot
- five baseline validation searches
- five candidate validation searches
- 50 query-product pairs in the human rating queue
- no live search mutation

The 1,200 database products are 800 standalone simple products, 384 simple configurable variations, and 16 configurable parents. Magento indexed the 800 standalone products and 16 configurable parents as 816 storefront search documents. The 384 variation products were not separate storefront search documents.

This qualifies the workflow against a real Magento product catalog and index. It does not satisfy the merchant-observation gate or establish ranking quality because the generated products have no approved human relevance labels.

## Large-catalog Admin rehearsal

The same 1,200-product lane was repeated in a fresh disposable fixture and opened through the styled Magento Admin at a 1920 by 1080 viewport. The Workbench prepared all 50 frozen query-product pairs, rendered 150 rating choices, and saved one immutable local judgment set with exactly 50 ratings. The saved set reappeared in history as `LOCALLY_REVIEWED`. The page produced no browser-console errors and did not change live search configuration.

The first visual pass exposed one deterministic scale problem: the 50-row queue occupied 1,931 vertical pixels, so its query, product, rank, and rating headings disappeared during the lower half of the review. A Workbench-specific Admin stylesheet now keeps those headings sticky without changing other grids. The repeated browser check measured the heading at viewport position 0 after scrolling 900 pixels into the queue, and the focused presentation regression test binds the stylesheet and scoped table class to the rating-queue block.

This is developer rehearsal evidence only. The generated product names and queries are intentionally synthetic, all submitted ratings were fixture-only inputs, and no merchant performed or observed the task. The preregistered pilot remains the only evidence that can close the usability gate.

## Curated scalar metadata

Phase 3 supports two optional query fields:

- `category_id`
- `brand_value`

Both are entered by a merchant in the exact snapshot preview. The module does not infer either value from query text. The server assigns the fixed `MERCHANT_CURATED` provenance, validates a bounded scalar value, and includes the structured value and provenance in the canonical snapshot identity.

Editing metadata does not change an already displayed approval payload. The administrator must rebuild the preview, observe the new SHA-256 identity and provenance, then approve that exact preview. Browser acceptance changed the displayed snapshot hash after adding category `42` and brand `Northwind`, displayed `MERCHANT_CURATED`, and persisted only the rebuilt identity.

Local persistence retains the structured provenance. The Search Relevance query-set payload receives only the validated scalar `customFields` values after exact approval. The clean fixture reconstructed both forms and confirmed their equality.

## Scheduled drafts

Snapshot schedules are exact, content-addressed policies with explicit store, source-window, sampling, first-run, interval, and retention values. Schedule creation and pausing are POST-only and ACL controlled.

The cron worker uses a lock, selects only due active schedules, prepares a local snapshot in `DRAFT` state, advances the schedule only after persistence, and leaves approval to a separate administrator action. Scheduled work has no path to:

- approve a snapshot
- create or run a judgment
- create or run an experiment
- export a proposal
- submit paid work
- mutate live search configuration

The clean fixture prepared a six-query reviewable draft. Its approval fields and remote query-set ID remained null, and all remote evaluation binding counts were unchanged.

## Owned-resource cleanup preview

The cleanup surface enumerates only remote resources already bound to local records. It reconstructs the expected immutable content, verifies the deterministic owned name and local-to-remote identity, and applies the existing exact-match cleanup guard to every row.

The clean fixture enumerated seven resources:

- one query set
- two search configurations
- one human judgment
- three experiments

All seven passed the exact identity gate. Any read failure, name mismatch, content mismatch, or binding inconsistency fails closed for that resource. The Admin surface is preview only. No remote delete controller or action exists.

## Browser acceptance

A styled Magento Admin run verified:

- before-and-after evidence with stale and partial context
- explicit unavailable product display
- moved-up and moved-down classifications
- exact schedule approval, draft review, and separate draft approval
- stale existing-proposal rejection
- seven-row cleanup preview with exact-match results and no delete action
- curated metadata re-preview, hash change, provenance display, and exact approval
- a 50-pair large-catalog queue with sticky column headings throughout the review
- immutable persistence of exactly 50 local ratings as a `LOCALLY_REVIEWED` judgment set

The browser workflow did not change live search configuration.

## Verification evidence

The current local source gates passed after adding the large-catalog lane and documentation:

- PHPUnit: 152 tests, 884 assertions
- PHPStan: no errors
- PHP_CodeSniffer: no violations
- Composer package validation: strict validation passed
- OpenSearch integration: 8 tests, 86 assertions, 1 expected LLM skip
- restricted-role security integration: 3 tests, 16 assertions

The clean Mage-OS fixture additionally reported:

- Phase 3 assertion: `PASS`
- movement query count: `5`
- deleted product preserved as unavailable: `true`
- stale existing proposal blocked: `true`
- cleanup preview resource count: `7`
- cleanup delete action exposed: `false`
- curated metadata provenance: `MERCHANT_CURATED`
- scheduled draft query count: `6`
- scheduled draft only: `true`
- remote binding mutation: `false`

## Remaining roadmap and release boundary

The pilot protocol, execution runbook, and evidence template are prepared in `PILOT-OBSERVATION-PLAN.md`, `PILOT-RUNBOOK.md`, and `PILOT-OBSERVATION-RECORD.md`. Preparation does not satisfy the observation gate.

The next valid roadmap work is:

1. Run the monthly workflow with a real pilot merchant and record usability, confusion, support burden, and completion evidence.
2. Requalify Phase 2 only when a current official or explicitly reviewed distribution provides the required LLM judgment, polling, rating, failure, cache, cleanup, and identity contracts. The 2026-08-27 official tag recheck did not unblock it.
3. Begin Phase 4 only after the applicable Phase 2 and Phase 3 exit gates are satisfied or the implementation plan is explicitly revised.

No commit, push, deployment, package release, remote cleanup, or live search application is part of this local result.
