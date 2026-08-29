# Phase 1 Human Workflow Findings

Date: 2026-08-26

These findings apply to the exact disposable Mage-OS fixture described below. They establish a locally complete human-judged vertical slice. They do not establish production readiness, merchant usability, revenue lift, or support for another OpenSearch distribution.

## Status

Phase 1 is complete against the local acceptance surface defined in `IMPLEMENTATION-PLAN.md`:

- the complete workflow is available in Magento Admin without OpenSearch Dashboards
- no LLM connector or external spend is required
- persisted inputs and outputs are reconstructable from frozen local identities and hashes
- the module cannot apply a proposal or change live storefront search configuration

Phase 2 remains blocked on a qualified official OpenSearch runtime artifact. It was not simulated or weakened to claim progress.

## Qualified fixture

- Mage-OS: 3.4.0
- PHP: 8.4
- MySQL: 8.4
- OpenSearch: 3.8.0
- Search Relevance plugin: 3.8.0.0
- ML Commons plugin: 3.8.0.0
- storefront target alias: `magento2_product_1`
- resolved fixture physical index: `magento2_product_1_v3`

Declarative schema status, dependency-injection compilation, catalog-search reindexing, installed-module transport, and the complete Phase 1 fixture assertion passed.

## Completed merchant control plane

The Magento Admin workbench now provides POST-only, ACL-controlled actions for:

1. Read-only capability preflight.
2. Query preview with source bounds and privacy classification.
3. Exact preview approval into an immutable local snapshot.
4. Stock storefront baseline capture with physical-index evidence.
5. A guided field-boost candidate constrained to mapped searchable fields.
6. A fresh top-ten union of baseline and candidate results for human rating.
7. Immutable imported human judgment persistence.
8. Creation or exact resumption of one pairwise and two pointwise offline experiments.
9. Local NDCG@10 evidence, freshness, coverage, threshold, and known-item evaluation.
10. Explicit acceptance of exact otherwise-winning evidence.
11. Download of a content-addressed, review-only proposal.

The workbench displays a persistent warning that version 1 cannot change live search configuration.

## Decision contract

An experiment freezes these local and remote identities:

- query snapshot UUID and SHA-256
- baseline configuration UUID, SHA-256, and remote configuration ID
- candidate configuration UUID, SHA-256, and remote configuration ID
- human judgment UUID, SHA-256, and remote judgment ID
- physical-index evidence SHA-256
- exact remote query-set ID
- exact pairwise, pointwise baseline, and pointwise candidate experiment IDs
- result depth of 10
- primary metric `NDCG@10`
- minimum judged coverage of 1.0
- minimum improvement of 0.01

Objective failures are evaluated before human acceptance. Stale index evidence, incomplete judged coverage, a known-item regression, or an improvement below the preregistered threshold cannot be accepted. Evidence that passes those checks is `EXPLORATORY` with `MERCHANT_ACCEPTANCE_REQUIRED` until an administrator accepts that exact result. Only then does it become `WINNER`.

Rerunning identical accepted inputs reuses the exact local experiment and three remote experiment IDs. It preserves the accepted result only when the recomputed aggregate and per-query evidence are byte-identical after canonicalization. Changed evidence fails closed.

## Deterministic fixture evidence

The complete fixture produced:

- baseline NDCG@10: `0.70474380285717`
- candidate NDCG@10: `1.0`
- delta: `0.29525619714283`
- judged coverage: `1.0`
- Search Relevance validation: valid for all three experiments
- index evidence: unchanged before and after local evaluation
- acceptance: explicit fixture acceptance after all objective gates passed
- remote experiment reuse: exact IDs preserved on rerun
- live search mutation: none

The accepted experiment UUID was `c8fa88b6-ad13-400e-a8fe-66bcfe9d1221`. Its review-only proposal UUID was `403104ae-5b84-4b8c-b980-e26b7d2ac330`, with artifact SHA-256 `c7c1a290b9601d18b0b9a616ce541043fc7fd428108f4d989b933cfa27c7beca`.

These identifiers belong to a disposable local fixture and are evidence references, not durable production resources.

## Proposal safety

Proposal creation requires an experiment in `ACCEPTED / WINNER` state with matching persisted candidate evidence. One source experiment can produce only one persisted proposal.

The downloaded canonical JSON:

- identifies the source experiment and all evidence hashes
- includes the allowlisted candidate transformation
- includes aggregate offline evidence and warnings
- declares `target_type` as `review_only`
- declares `application.supported` as `false`
- excludes raw query text
- is hashed after all fields are present
- is rehashed and verified whenever the persisted artifact is read

Browser acceptance downloaded the artifact and reproduced the persisted SHA-256 exactly. A direct text scan found none of the five fixture query strings.

## Runtime corrections learned during the slice

- Search Relevance names are limited to 50 characters. Owned names now use deterministic bounded prefixes and short hashes while local records preserve the full content identity.
- Magento captures a storefront target alias, but Search Relevance configurations require the evidence-resolved physical index for reproducible experiments.
- The Mage-OS request shape may include the legacy document type `document`. Bounded replay permits only that known value and removes it before sending the OpenSearch 3 request.
- The Mage-OS client can return a document identity in `fields._id` instead of top-level `_id`. Bounded result parsing supports both representations and rejects missing identities.
- An accepted experiment is not a mutable label. Its evidence and exact remote bindings remain part of the acceptance decision.

## Verification evidence

The final local source gates passed:

- PHPUnit: 128 tests, 700 assertions
- PHPStan: no errors
- PHP_CodeSniffer: no violations; dependency deprecation notices only
- Composer package validation: strict validation passed
- OpenSearch integration: 8 tests, 86 assertions, 1 expected LLM skip
- Mage-OS declarative schema: all modules up to date
- Mage-OS dependency injection: compilation passed
- browser acceptance: full Admin workflow, exact acceptance, resumability, and proposal download passed

## Remaining blocker and release boundary

The official OpenSearch 3.8 artifact does not provide a qualified LLM judgment path for this module. The Phase 0 investigation found a Search Relevance plugin runtime dependency failure on the first remote-model prediction. The full installed preflight also lacks the required usable LLM judgment storage contract. A diagnostic derivative is not a supported artifact and cannot satisfy Phase 2.

Phase 2 therefore requires a current official artifact or explicitly reviewed distribution that passes connector creation, judgment creation, polling, rating output, failure handling, cache or explicit reuse semantics, cleanup, and the module's identity policy.

No commit, push, deployment, package release, or live search application is part of this local Phase 1 result.
