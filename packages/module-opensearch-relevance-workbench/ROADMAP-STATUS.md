# OpenSearch Relevance Workbench roadmap status

Date: 2026-08-28

This file is the current status overlay for `IMPLEMENTATION-PLAN.md`. The implementation plan remains the product and release contract. This file records what is complete, what is blocked, and what evidence is still required.

## Current state

| Phase | State | Evidence | Remaining gate |
| --- | --- | --- | --- |
| Phase 0: contracts | Human-workflow contracts qualified | Pinned OpenSearch 3.8 integration, restricted-role security tests, Mage-OS baseline capture, drift evidence, cleanup guard | Qualified LLM judgment runtime remains unavailable |
| Phase 1: human vertical slice | Installed-system complete, private-lab boundary extended | Immutable snapshots, stock baseline, field-boost candidate, human ratings, three experiments, local evidence, accepted evidence package, controlled activation and rollback | Operator browser acceptance of the redesigned Admin remains required |
| Phase 2: LLM judgment | Blocked | Official Search Relevance tags rechecked on 2026-08-27 | A qualified official or explicitly reviewed runtime must satisfy the full judgment, polling, failure, cache, cleanup, and identity contract |
| Phase 3: merchant evidence | Technical work complete | Product movement, stale-product handling, curated metadata, draft-only schedules, cleanup preview, large-catalog qualification | A real merchant must complete the preregistered initial and return observation sessions |
| Phase 4: release candidate | Not started | Private-lab activation code is not release evidence | Phase 2 and Phase 3 must exit, or the implementation plan must be explicitly revised before Phase 4 starts |

## Private-lab full-app extension

The private-lab product boundary now extends beyond the original review-only implementation plan. The module can apply one bounded field-boost candidate to the storefront only when its source experiment is an explicitly accepted `WINNER` and a fresh OpenSearch index-evidence capture exactly matches the frozen baseline. The current candidate, actor, target alias, evidence identity, and prior live state are persisted. Rollback writes a new audit event and restores the preceding state.

A clean Mage-OS 3.4 installed-system run on 2026-08-28 passed declarative schema validation, dependency-injection compilation, storefront and GraphQL baseline capture, the complete human workflow, exact live field-boost application, duplicate-activation rejection, rollback to stock, and all Phase 3 technical assertions. Screenshot-based Admin acceptance remains separate and requires an authorized runtime deployment of this source.

The activation path does not import an evidence package, accept arbitrary query JSON, write OpenSearch configuration resources, modify aliases, delete remote resources, run paid work, or enable the unqualified LLM judgment path. A runtime read failure leaves the Mage-OS mapped query unchanged.

This is a lab-testing boundary revision, not Phase 4 authorization or production qualification. The original implementation plan remains the historical release contract until it is explicitly revised.

## Evidence added after the original Phase 3 fixture

The catalog-only Mage-OS small-profile lane passed from a clean fixture:

- 1,200 rows in `catalog_product_entity`
- 816 storefront-indexed OpenSearch product documents
- 100 product-derived query-history rows selected into one immutable snapshot
- five baseline validation searches
- five candidate validation searches
- 50 query-product pairs in the human rating queue
- no live search mutation

This proves the human workflow still operates against a real Magento catalog and indexing pipeline. It does not prove merchant usability or ranking quality because the generated catalog has no approved human relevance labels.

A separate styled Admin rehearsal completed the 50-pair queue and persisted exactly 50 fixture ratings as one immutable `LOCALLY_REVIEWED` judgment set. The pass found that headings disappeared while reviewing the lower rows of the 1,931-pixel queue. A scoped sticky-heading fix now keeps the five rating columns visible, with a focused regression test and a repeated browser check at a 1920 by 1080 viewport. This remains developer rehearsal, not merchant-observation evidence.

## Phase 2 recheck

The official Search Relevance repository still lists `3.8.0.0` as its newest semantic release tag. The newer `custom_3.4` tag points to a dependency-only commit and is not a qualified replacement distribution for this module.

Sources:

- [Official Search Relevance tags](https://github.com/opensearch-project/search-relevance/tags)
- [`custom_3.4` tagged commit](https://github.com/opensearch-project/search-relevance/commit/7b20566442203d68c094377d35957a4eaa364eef)

The Phase 2 blocker remains. Do not simulate the missing runtime behavior or weaken the recorded identity policy.

## Next valid roadmap action

Run the Phase 3 observation protocol with one real merchant operator in an approved environment. Use `PILOT-RUNBOOK.md`, preregister the limits and exit rule before results are visible, and keep raw customer data outside this repository.

Passing Phase 3 alone does not authorize Phase 4 while Phase 2 remains blocked. After a valid Phase 3 result, make one explicit decision:

1. wait for a qualified Phase 2 runtime and retain the existing v1 plan; or
2. revise the implementation plan so a human-only v1 can enter Phase 4.

That decision does not authorize commit, push, deployment, release, live search application, connector work, or remote deletion.
