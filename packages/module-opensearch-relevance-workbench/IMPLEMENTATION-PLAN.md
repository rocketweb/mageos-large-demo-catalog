# OpenSearch Relevance Workbench for Mage-OS

Status: Proposed local implementation plan. This document authorizes no implementation, commit, push, connector creation, production configuration change, release, or deployment.

Current implementation and gate status: [ROADMAP-STATUS.md](ROADMAP-STATUS.md)

Date: 2026-08-25

Temporary repository: `rocketweb/module-opensearch-relevance-workbench`

Intended destination after a verified v1 and separate approval: Mage-OS Lab

## 1. Decision

Build the module, but narrow the first release to the trustworthy product boundary:

> A merchant can turn approved Magento search terms into an immutable query set, compare a captured production baseline with a bounded candidate, calibrate and run judgments, review offline relevance evidence, and export a reproducible proposal without using OpenSearch Dashboards or writing query DSL.

Version 1 stops at proposal export. It does not apply search configuration to a live store.

This is the right boundary because:

- OpenSearch 3.8 provides the required Search Relevance Workbench APIs, provider-neutral LLM judgments, Mustache search configurations, cache reuse, and experiment-input validation.
- Mage-OS 3.4 exposes enough of the stock OpenSearch path to attempt exact baseline capture.
- The stock query mapper is public but is not a declared `@api` contract. It must be qualified before any runtime interception becomes a supported production surface.
- Offline relevance metrics do not establish conversion or revenue lift.
- The existing `MageOS_OpenSearchHybrid` pilot has its own frozen retrieval, generation, activation, and rollback contracts. This module must not edit or bypass them.

The market thesis is promising, but it remains a product hypothesis until merchant interviews, pilot use, support-cost evidence, and current competitor validation are complete. It is not a release claim.

## 2. Provisional identity

Use one Magento module for v1:

- Product name: `OpenSearch Relevance Workbench for Mage-OS`
- Magento module: `MageOS_OpenSearchRelevanceWorkbench`
- PHP namespace: `MageOS\OpenSearchRelevanceWorkbench`
- Provisional Composer package: `mage-os/module-opensearch-relevance-workbench`
- Database prefix: `osrw_`

The code identity is provisional until Mage-OS Lab, licensing, affiliation, and OpenSearch trademark review. The temporary GitHub organization does not change the runtime namespace.

Do not split v1 into Core, Adminhtml, Sync, and Export packages. One module with explicit internal contracts is easier to install, test, and port. Consequential application adapters are separate future packages.

## 3. Verified source baseline

Planning is pinned to these exact sources:

- Mage-OS `3.4.0`, source commit `d16a13824cfd4938c32f44cb9d0abe5a9faa20e8`.
- OpenSearch Search Relevance plugin tag `3.8.0.0`, source commit `1f7402c43c42dea388626d995521b37092db4412`.
- Mage-OS 3.4 requires `opensearch-project/opensearch-php:^2.3`; its locked distribution currently resolves `2.5.1`.
- OpenSearch 3.8 is the hard minimum and OpenSearch 4 is outside the initial support contract.

The compatibility contract must be rechecked when any of those inputs changes. Capability probes control the UI. Version strings alone do not.

## 4. Corrections to the seed proposals

These corrections are design inputs, not editorial details.

| Seed assumption | Verified 3.8 behavior | Plan consequence |
| --- | --- | --- |
| Judgment reuse uses `existingJudgments` | The tagged 3.8 request uses `overwriteCache`; no `existingJudgments` request field exists in the tagged source | Model cache behavior directly and contract-test `overwriteCache=false` and `true` |
| Failed judgments need a Magento retry emulation | Transient retries are configured on the ML Commons connector through `client_config`; 3.8 has no public judgment `_retry` route | Show the connector retry policy before spend; do not invent an unsupported retry endpoint |
| Judgment cache reuse is safe across reruns | The 3.8 lookup key includes query text, index plus document ID, context field names, and prompt/rating hash. It does not filter by model ID or document content | Default decision runs to `overwriteCache=true` unless all locally recorded model, prompt, context-value, query-set, and index-evidence identities match |
| Experiment `/validate` detects catalog drift | It compares the stored query set, search configurations, and judgment lists. It does not fingerprint target index contents | Require a separate physical-index evidence check before a result remains decision-eligible |
| LLM calls equal queries times result depth | Hits are grouped into token-sized chunks. Actual calls are between roughly one per query and one per query-document pair, depending on content | Present a range and worst-case authorization, not a false exact call or cost figure |
| Calibration can show LLM reasoning | The 3.8 structured response contains document ID and rating only | Show disagreements and source fields, not invented reasoning |
| `buildQuery()` is a supported extension contract | `Magento\OpenSearch\SearchAdapter\Mapper::buildQuery()` is public, but its class is not marked `@api` | Use it in a compatibility spike and capture-only path; do not make live mutation a v1 promise |
| Search terms provide category, brand, price, or filter context | `search_query` provides aggregate term data, not request context | Start with query text and explicitly curated metadata. Observed context requires separate telemetry or UBI |
| SRW experiments are A/B tests | They are offline experiments over query sets, configurations, and judgments | Use `offline relevance experiment` throughout the Admin UI |

## 5. Hard product boundary

### 5.1 Version 1 may

- Read approved, store-scoped aggregates from Mage-OS `search_query`.
- Preview privacy filters and sampling before any term leaves Magento.
- Create immutable, namespaced SRW query sets, search configurations, judgment lists, and experiments.
- Reference an existing allowlisted ML Commons remote-model ID.
- Import human judgments.
- Poll and locally mirror remote state and results.
- Capture and parameterize the stock quick-search baseline if the equivalence harness passes.
- Compile allowlisted candidate changes from guided forms.
- Display aggregate, per-query, and before/after product evidence.
- Export a content-addressed proposal artifact.
- Delete only remote resources whose ownership record and current identity match this installation.

### 5.2 Version 1 may not

- Collect, display, retrieve, or store LLM connector credentials.
- Create or reconfigure production connectors.
- Accept caller-selected OpenSearch hosts, paths, indices, pipelines, store IDs, or arbitrary DSL.
- Apply a proposal to Mage-OS configuration or live search.
- Intercept and replace production query DSL.
- Activate or mutate an OpenSearch Hybrid generation.
- Edit `MageOS_OpenSearchHybrid` contract files.
- Depend on `MageOS_OpenSearchHybrid`.
- Claim live traffic, conversion, or revenue lift.
- Depend on the experimental Relevance agent.
- Run paid judgment work from cron without a prior, exact spend authorization.
- Delete non-owned SRW resources or system indices.

## 6. Merchant workflow

The complete v1 loop is:

1. **Preflight**: verify Mage-OS engine, OpenSearch version, installed plugins, SRW capability routes, target index, role permissions, and configured model allowlist.
2. **Preview terms**: choose store views, source window, minimum popularity, result-count strata, exclusions, sample size, and privacy rules. Show exact counts and in-Magento examples.
3. **Approve snapshot**: freeze a content-addressed query set. Approval covers this exact snapshot only.
4. **Capture baseline**: build the stock quick-search request using the target store and prove template round-trip equivalence.
5. **Build candidate**: apply typed, allowlisted changes to the captured baseline. Raw JSON remains read-only in v1.
6. **Calibrate**: rate a representative sample. Compare human ratings with the selected LLM before results can be called decision-eligible.
7. **Authorize spend**: show query count, union document bound, call range, token limit, disclosed fields, model identity, connector retry policy, cache policy, and any configured cost range.
8. **Generate judgments**: submit one bounded run, poll it, and keep failures and unrated pairs visible.
9. **Run offline experiments**: freeze baseline, candidate, query set, effective judgment list, index evidence, primary metric, and guardrails before submission.
10. **Review evidence**: show metric changes, query-level wins and regressions, known-item guardrails, coverage, failures, and product grids.
11. **Validate freshness**: require SRW input validation and unchanged physical-index evidence.
12. **Export proposal**: download a canonical artifact. No live configuration changes occur.

## 7. Architecture

### 7.1 Module layers

Keep dependency direction inward:

```text
Admin controllers, UI components, cron, CLI
        |
Application services and state machines
        |
Domain records and interfaces
        |
Mage-OS repositories, OpenSearch transport, persistence
```

Suggested package areas:

```text
Api/
  BaselineCaptureInterface.php
  IndexEvidenceProviderInterface.php
  JudgmentSourceInterface.php
  ProposalExporterInterface.php
  SearchRelevanceClientInterface.php

Model/
  Baseline/
  Capability/
  Experiment/
  IndexEvidence/
  Judgment/
  OpenSearch/
  Proposal/
  QuerySnapshot/
  Security/

Cron/
Console/
Controller/Adminhtml/
Ui/
view/adminhtml/
etc/
```

Domain services depend on interfaces. Mage-OS framework objects and the OpenSearch PHP client remain at adapter boundaries.

### 7.2 OpenSearch client boundary

Implement a narrow `SearchRelevanceClientInterface`. Its methods represent supported operations, not arbitrary method, path, or body input.

Required v1 operations:

- capability and version reads
- query-set create, get, search, and owned delete
- search-configuration create, get, search, and owned delete
- judgment create, get, search, and owned delete
- experiment create, get, search, validate, and owned delete
- target alias, physical-index, mapping, settings, and shard-sequence evidence reads
- approved remote-model metadata read without connector credentials

The first transport candidate is the low-level transport exposed through Mage-OS 3.4's public `Magento\OpenSearch\Model\SearchClient::getOpenSearchClient()`. Phase 0 must prove the exact `opensearch-php 2.5.1` call shape, deadlines, error mapping, and authentication behavior. If that fails, implement a dedicated client using the same server-side Mage-OS connection options. Do not expose a second Admin-configured host.

Every method must:

- hardcode or construct from validated opaque IDs the exact route it owns
- enforce request and response byte limits
- set bounded connection and overall deadlines
- reject unexpected status codes or response shapes
- redact query text, document content, credentials, and provider responses from logs
- attach a local correlation ID that contains no customer data

### 7.3 Capability detector

Preflight is read-only. It reports pass, fail, or unavailable for:

- selected Mage-OS engine is stock OpenSearch
- OpenSearch is `>=3.8.0,<4.0.0`
- Search Relevance and ML Commons plugins are present
- `plugins.search_relevance.workbench_enabled` is effective
- required SRW reads are authorized
- required target-index reads and searches are authorized
- configured remote-model IDs are deployed and usable
- the target store resolves to one unambiguous current search alias and physical index
- ElasticSuite or another non-stock engine is active

ElasticSuite and unknown engines are evaluation-blocked in v1. The UI explains the unsupported path rather than attempting a stock-Mage-OS export.

Do not mutate cluster settings from Magento. Show an operator-facing remediation note or exact reviewed command template.

### 7.4 Namespace and ownership

Every remote name contains a stable installation ID, store ID, resource type, and local content hash. OpenSearch IDs returned by the API are stored locally.

Ownership requires both:

- a local immutable ownership row, and
- matching remote name, type, and content hash at cleanup time.

If either side differs, cleanup fails closed. Uninstall preserves remote resources unless a separately approved cleanup preview is applied.

## 8. Local data model

Magento stores canonical inputs, remote IDs, denormalized results, and audit evidence. It must be possible to explain and reconstruct a proposal even when OpenSearch is unavailable.

### `osrw_query_snapshot`

- UUID, store ID, status
- source window and `(updated_at, query_id)` high-water boundary
- sampling and privacy-policy JSON
- source, selected, excluded, and redacted counts
- canonical SHA-256
- remote query-set ID
- approved by and approved at

### `osrw_query_snapshot_entry`

- snapshot UUID and stable ordinal
- query text ciphertext or encrypted-at-rest value if the platform facility supports it
- canonical query hash
- source query ID, popularity, result count, source updated time
- custom scalar fields JSON with provenance per field
- exclusion and redaction flags

Do not log entry content. If reliable application-level encryption is unavailable in the first slice, document the database trust boundary and minimize retention rather than inventing weak encryption.

### `osrw_index_evidence`

- UUID, store ID, alias, physical index, index UUID
- mapping and relevant-settings hashes
- primary-shard max sequence numbers and global checkpoints
- document count
- captured at and evidence SHA-256

### `osrw_search_configuration`

- UUID, store ID, kind (`BASELINE` or `CANDIDATE`)
- parent baseline UUID
- canonical template and transformation JSON
- index-evidence UUID
- pipeline identity
- rendered-sample hashes and validation state
- remote search-configuration ID

### `osrw_human_rating`

- calibration or override set UUID
- query snapshot UUID, query hash, document ID
- rating, source, reviewer, timestamp
- target index-evidence UUID

### `osrw_judgment_run`

- UUID, source type, state
- model ID and approved display metadata
- prompt, prompt hash, rating type, context fields
- token limit, cache policy, connector retry-policy snapshot
- estimated call range and spend range when configured
- remote judgment ID
- totals, successes, failures, unrated pairs
- effective imported-judgment ID when human overrides are materialized

### `osrw_experiment`

- UUID, type, state
- immutable input IDs and hashes
- registered primary metric and guardrail JSON
- remote experiment IDs
- SRW validation result
- local index-freshness result
- denormalized aggregate and per-query result JSON
- eligibility status and reason codes

### `osrw_proposal`

- proposal UUID and schema version
- source experiment UUID
- target type
- canonical artifact JSON and SHA-256
- evidence and warnings JSON
- created by and created at
- no applied state in v1

### `osrw_audit_event`

- append-only UUID, actor type and actor ID
- action, target type and target UUID
- before and after identity hashes
- result, reason code, correlation ID, timestamp

Raw connector credentials, raw vectors, provider tokens, and unrestricted `_source` never enter these tables.

## 9. Query snapshot pipeline

### 9.1 Exact Mage-OS 3.4 source

The verified `search_query` schema contains:

- `query_id`
- `query_text`
- `num_results`
- `popularity`
- `redirect`
- `store_id`
- `display_in_terms`
- `is_active`
- `is_processed`
- `updated_at`

Use the resource connection and explicit column selection. Do not scrape Admin grids.

### 9.2 Sampling defaults

Start with a bounded, per-store snapshot:

- exclude null, blank, control-character, and over-limit terms
- require active terms
- separate positive-result and zero-result strata
- require a configurable minimum popularity
- exclude redirect terms from relevance evaluation unless the merchant explicitly includes them
- cap each stratum and the total snapshot
- retain head and torso terms instead of selecting only the global top N
- reserve a merchant-pinned known-item slice
- default the first calibration snapshot to 20 queries and the first full run to no more than 200
- never exceed the cluster's detected query-set maximum, which defaults to 1,000 in the tagged plugin

Popularity is a noisy aggregate, not a verified human-traffic sample. Label it that way.

### 9.3 Privacy preview

Search terms may contain names, email addresses, phone numbers, addresses, order numbers, or other accidental personal data.

Before any upload:

- run bounded, tested detectors and redactors
- exclude low-frequency terms by default
- show counts and in-Magento examples to an authorized administrator
- never log excluded or raw terms
- record the exact privacy-policy version and rules
- require approval for the exact snapshot hash
- provide quarantine and retention controls

Redaction reduces risk. It is not a claim of anonymization.

### 9.4 Immutability and idempotency

Canonicalize entries with explicit key ordering, Unicode normalization, and stable numeric encoding. The content hash includes store ID, entries, custom-field provenance, sampling rules, and privacy-policy version.

Re-running the same source boundary and rules produces the same local identity. A snapshot referenced by a judgment or experiment is never mutated. New source data creates a new snapshot.

Scheduled sync is disabled until an administrator approves the source, rules, schedule, retention, and maximum snapshot size. Cron may prepare a draft snapshot. It may not approve it, start an LLM run, or apply a proposal.

### 9.5 Context provenance

Version 1 always supports `queryText`.

Custom Mustache values require one of these provenance labels:

- `MERCHANT_CURATED`
- `OBSERVED_TELEMETRY`
- `UBI`
- `CATALOG_CLASSIFIED_REVIEWED`

Do not infer category, brand, or price context from the term and present it as observed. The first vertical slice uses query text only. Merchant-curated scalar `category_id` and `brand_value` may follow after the custom-field contract test passes. Derived price ranges are post-v1.

## 10. Baseline capture and candidate compilation

### 10.1 Baseline invariant

A decision-eligible baseline must represent the request Mage-OS actually sends for stock quick search on the selected store.

Phase 0 proves this capture algorithm:

1. Enter a request-scoped capture context used only by an internal Admin or CLI probe.
2. Build the same stock quick-search request twice under store emulation with two collision-resistant sentinel terms.
3. Capture the arrays returned by `Magento\OpenSearch\SearchAdapter\Mapper::buildQuery()`.
4. Structurally diff the captures.
5. Replace only paths whose values change exactly with the sentinels by `{{queryText}}`.
6. Treat every other changing path as nondeterminism and fail capture until it is understood and normalized.
7. Split OpenSearch client parameters, search body, target index, and search pipeline into the exact SRW configuration contract.
8. Render at least five real snapshot queries.
9. Build fresh native requests for those queries and require canonical structural equality after an allowlisted normalization.
10. Record the target physical-index evidence and template digest.

The capture plugin performs one request-context check and no writes on ordinary storefront traffic. It must not become a general query logger.

### 10.2 Surface coverage

The spike must test:

- Luma quick search
- Hyva quick search when a fixture is available
- GraphQL products search
- store scope
- customer-group and website dimensions
- currency and price context
- pagination and sort paths used by quick search
- layered navigation only when the experiment explicitly models that context

If two surfaces produce materially different requests, they receive separate baseline types. Do not call one capture universal.

### 10.3 Candidate compiler

Candidates are typed transformations of a captured baseline. V1 guided transforms are limited to shapes proven against the target mapping:

- field boosts
- exact-match boost
- `minimum_should_match`
- bounded scalar term filters sourced from approved custom fields

Compiler rules:

- inspect the actual mapping before offering fields
- resolve Magento attribute codes through an allowlisted registry
- reject sensitive, non-searchable, dynamically mapped, or unknown fields
- accept scalar Mustache substitutions only
- reject partials, scripts, arbitrary indices, and caller-supplied pipelines
- render and execute every snapshot entry with hard size and time limits before an experiment
- store transformation and rendered-sample hashes

Raw JSON is visible to expert roles for diagnosis but read-only in v1.

## 11. Index freshness

SRW input validation is necessary but insufficient.

Capture this evidence immediately before judgment retrieval, immediately before experiments, and again before proposal export:

- resolved alias and physical index
- index UUID
- canonical mapping hash
- relevant analysis and search-setting hash
- primary-shard max sequence numbers and global checkpoints
- document count

Recheck it before proposal export.

All three evidence hashes must match for a decision-eligible run. Version 1 does not create a full cloned catalog index or claim snapshot isolation that OpenSearch does not provide. Private pilots should run in a declared quiet catalog window. A store that changes during the run gets a `STALE` result and must rerun. Phase 0 should measure how often this occurs before a frozen evaluation-index design is considered.

Mark the experiment `STALE` when:

- the alias resolves to a different physical index
- any primary sequence boundary changes
- mapping, relevant settings, or pipeline identity changes
- SRW `/validate` returns `DRIFTED` or `UNAVAILABLE`

`STALE` results remain reviewable but are not exportable as winners. A rerun against the new evidence is required.

## 12. Judgments and calibration

### 12.1 Credential and model boundary

V1 references an existing, allowlisted deployed model ID. OpenSearch administrators create connectors and deploy models outside this module.

Magento stores only:

- model ID
- administrator-approved display name
- provider class if known
- prompt and rating identities
- non-secret retry-policy summary if readable

The module never requests a connector credential endpoint or places a provider key in Magento configuration, browser payloads, logs, or tables.

### 12.2 Rating scale

Use `SCORE0_1` from the first run. The merchant UI offers:

- irrelevant: `0.0`
- partially relevant: `0.5`
- highly relevant: `1.0`

Keep the stored numeric rating visible in expert mode. This supports graded metrics without changing scales between calibration and full runs.

### 12.3 Calibration gate

An uncalibrated model may produce exploratory results. It may not produce a result labeled `WINNER`.

Initial proposed gate:

- at least 20 representative queries
- top 5 union documents per query, targeting at least 100 reviewed pairs
- known-item, ambiguous, torso, tail, and deliberately irrelevant examples
- frozen prompt, context fields, model ID, and rating type
- weighted kappa of at least `0.60`
- no unexplained material failure on the known-item slice

This threshold is preregistered and may be amended before results are viewed. Pilot evidence determines whether it is understandable and useful for merchants.

The disagreement screen shows query, product fields, human rating, and LLM rating. OpenSearch 3.8 does not provide a reasoning field, so the UI does not claim one.

### 12.4 Cost and disclosure authorization

Before submission, show:

- query count
- result depth per configuration
- upper bound on unique query-document pairs
- minimum and worst-case remote-call counts
- token limit
- exact context fields disclosed
- target model and provider display metadata
- connector retry summary
- cache policy
- elapsed-time limit for local polling
- estimated spend range only when reviewed pricing metadata is configured

Pricing metadata is volatile and optional. Label estimates with source and timestamp. The hard authorization is the bounded query, depth, token, and retry envelope.

The public 3.8 judgment API does not provide a reliable mid-run cancellation or billing meter. Once submitted, a run may continue inside OpenSearch. Therefore:

- cron cannot submit LLM work
- submission requires a dedicated spend ACL and fresh confirmation
- the module refuses a run whose worst-case envelope exceeds the configured approval cap
- connector rate and retry limits remain the operational backstop

### 12.5 Cache policy

Use `overwriteCache=true` unless all of these identities match a previously accepted run:

- model ID
- prompt hash and rating type
- context-field names and retrieved values
- query snapshot hash
- search-configuration hash
- physical-index evidence hash

Even when they match, the Phase 0 live test must prove cache hits and unchanged results before the UI promises reuse. Never promise that a rerun is free.

### 12.6 Failures and overrides

Keep failed and unrated document IDs visible. A run with coverage below its registered floor is `PARTIAL`, not complete.

OpenSearch 3.8 has no in-place judgment rating update. Store merchant overrides locally and materialize one new `IMPORT_JUDGMENT` list that contains the effective LLM plus human ratings. Experiments use that immutable effective list. Avoid relying on list-order overwrite behavior as a product contract.

## 13. Experiment rules

Use both experiment types for different questions:

- `PAIRWISE_COMPARISON` answers how different the result lists are.
- `POINTWISE_EVALUATION` answers how each configuration performs against the same effective judgments.

For a baseline and candidate decision, create:

- one pairwise comparison
- one pointwise evaluation for baseline
- one pointwise evaluation for candidate

The judgment run retrieves the union of baseline and candidate results so both pointwise arms have coverage.

Each experiment freezes:

- query snapshot
- baseline and candidate configuration IDs and hashes
- effective judgment ID and hash
- index-evidence hash
- result depth
- primary metric
- guardrails and slice definitions
- minimum judged coverage
- maximum provider failure rate
- tie and inconclusive rules

Initial proposed primary metric is `NDCG@10`. Initial guardrails include:

- known-item first-result and reciprocal-rank regressions
- judged coverage
- zero-result changes when the snapshot contains that stratum
- no declared store or curated-category slice below its floor

Do not collapse the first release into an unexplained 0 to 100 grade. Show metrics with plain-language descriptions and query-level evidence. A composite grade requires separate validation.

A result is `WINNER` only when:

- calibration passes
- the primary metric clears its preregistered improvement threshold
- every guardrail passes
- coverage and provider failure thresholds pass
- all declared slices are reported
- SRW validation returns `VALID`
- index evidence is unchanged
- the run is reproducible from frozen local identities
- the merchant explicitly accepts the evidence for export

All other outcomes are `EXPLORATORY`, `INCONCLUSIVE`, `PARTIAL`, `STALE`, or `FAILED` with reason codes.

## 14. Admin experience

Use a small set of monthly-workflow screens:

1. **Overview and preflight**: what changed, current compatibility, stale evidence, and work needing attention.
2. **Query snapshots**: preview filters, privacy effects, strata, curated fields, approval, and retention.
3. **Configurations**: captured baseline, guided candidate changes, rendered examples, and validation.
4. **Calibration and judgments**: human rating queue, agreement, disclosure, spend authorization, progress, and failures.
5. **Experiments**: aggregate evidence, per-query changes, product grids, guardrails, slices, and freshness.
6. **Proposals**: canonical artifact, warnings, target, hash, and download.

ACLs are separate for:

- view status and results
- preview query data
- approve and schedule snapshots
- curate metadata and human ratings
- manage configurations
- authorize paid judgments
- run experiments
- export proposals
- manage settings
- preview and clean up owned remote resources

Every mutation is POST-only, CSRF protected, scoped to an authorized store, and audited.

## 15. Proposal artifact

Export canonical JSON with this minimum schema:

```json
{
  "schema": "mageos-opensearch-relevance-proposal/v1",
  "proposal_id": "uuid",
  "created_at": "RFC3339 timestamp",
  "store_id": 1,
  "target_type": "review_only",
  "source": {
    "experiment_id": "local uuid",
    "query_snapshot_sha256": "sha256",
    "judgment_sha256": "sha256",
    "index_evidence_sha256": "sha256"
  },
  "baseline": {
    "configuration_sha256": "sha256"
  },
  "candidate": {
    "configuration_sha256": "sha256",
    "transformation": {}
  },
  "evidence": {
    "primary_metric": "NDCG@10",
    "guardrails": [],
    "eligibility": "WINNER"
  },
  "application": {
    "supported": false,
    "reason": "Version 1 is export only"
  },
  "warnings": []
}
```

Canonicalize and hash the artifact after all fields are present. The download filename includes proposal ID and a short hash. No signing claim is made until a real signing and verification design exists.

## 16. Boundary with `MageOS_OpenSearchHybrid`

The modules remain independent:

```text
OpenSearch Relevance Workbench
        |
        | proposal artifact
        v
Future optional hybrid adapter
        |
        | replacement-generation preview
        v
MageOS_OpenSearchHybrid validation, acceptance, activation, rollback
```

Rules:

- The hybrid module never depends on this module.
- This module never imports hybrid implementation classes.
- A future adapter package may depend on both modules.
- The adapter accepts only a versioned proposal schema and an allowlisted transformation subset.
- It may produce a replacement-generation preview. It may not edit frozen contracts in place.
- Generation creation, result-contract validation, explicit acceptance, activation, and rollback remain owned by the hybrid module.
- Unsupported three-way retrieval or optimizer shapes remain evidence only.
- Disabling either module must not alter stock quick-search behavior unexpectedly.

The current hybrid module preserves a native top-100 candidate universe and frozen result contract. Relevance workbench results do not override that contract.

## 17. Cron and job state

Use Magento cron as the visible control plane:

- snapshot preparer: creates draft snapshots only after scheduling was explicitly enabled
- remote poller: polls locally pending judgment and experiment IDs
- retention reporter: prepares cleanup candidates but does not delete them

Use `LockManagerInterface` and idempotency keys. One job per local immutable input hash may be submitted.

Suggested states:

```text
DRAFT -> APPROVED -> SUBMITTED -> RUNNING
                              -> COMPLETED
                              -> PARTIAL
                              -> FAILED

COMPLETED -> VALID
          -> STALE
          -> INCONCLUSIVE
          -> WINNER
```

Unknown remote states are stored as `REMOTE_UNKNOWN` and do not advance. Network failures do not erase the last known state.

Do not use SRW scheduled experiments in v1. One scheduler owns approval, polling, retention, and merchant-visible history.

## 18. Implementation sequence

### Phase 0: repository and live contract spike

Deliverables:

- module skeleton, license, Composer metadata, coding standards, static analysis, unit test harness, and CI
- public Mage-OS 3.4 fixture on PHP 8.4, MySQL 8.4, and OpenSearch 3.8 pinned by digest
- Search Relevance and ML Commons plugin readiness
- narrow client contract tests for every required route
- disposable local OpenAI-compatible stub plus test-only ML Commons connector
- exact least-privilege OpenSearch action list
- baseline sentinel capture and round-trip harness
- index-evidence capture
- judgment cache identity tests
- GraphQL and storefront baseline-path tests
- owned resource cleanup dry run

Exit criteria:

- create, read, poll, validate, and delete work against the pinned cluster
- raw client passes Mustache, pipeline, judgment, and experiment payloads unchanged
- baseline capture round-trips on stock quick search
- index drift is detected independently of SRW validation
- model-change and document-change cache cases are characterized
- no merchant UI and no production apply code

If baseline round-trip or safe transport fails, stop and revise the architecture before Phase 1.

### Phase 1: human-judged vertical slice

Deliverables:

- preflight Admin screen
- query preview, privacy filtering, immutable snapshot, and approval
- baseline capture review
- guided field-boost candidate
- human rating queue and effective imported judgments
- pairwise plus two pointwise experiments
- aggregate and per-query evidence
- review-only proposal export

Exit criteria:

- a merchant completes the loop without OpenSearch Dashboards
- no LLM connector or external spend is required
- every artifact is reproducible from local hashes
- no live search configuration changes

### Phase 2: LLM judgment source and calibration

Deliverables:

- allowlisted deployed-model selection
- frozen prompt and context-field configuration
- call, disclosure, retry, cache, and spend-range preview
- fresh spend confirmation
- polling, failure, unrated-pair, and partial-run UI
- human calibration and eligibility state
- materialized human override list

Exit criteria:

- external fields and maximum envelope match the approved preview
- connector credentials never enter Magento
- cache behavior matches the recorded identity policy
- an uncalibrated run cannot produce a `WINNER`

### Phase 3: merchant evidence UX and scheduled drafts

Deliverables:

- before/after product grids with moved, added, and dropped products
- known-item and regression inbox
- curated scalar query metadata with provenance
- scheduled draft snapshot preparation
- stale-index alerts and rerun workflow
- bounded owned-resource cleanup preview

Exit criteria:

- product ID resolution tolerates stale or deleted documents
- scheduled work cannot spend money or apply configuration
- monthly workflow is usable in pilot observation

### Phase 4: v1 release candidate

Deliverables:

- complete documentation, privacy model, threat model, operations guide, upgrade guide, and uninstall behavior
- compatibility matrix and known limitations
- Mage-OS 3.4 fixture evidence
- clean installation, upgrade, and disable tests
- release artifact and provenance report prepared locally

Exit criteria are defined in section 20. Publication remains separately approved.

## 19. Test strategy

### Unit tests

- canonical JSON and hash stability
- query normalization, sampling, strata, and high-water ordering
- privacy detector and redaction fixtures
- Mustache scalar allowlist and escaping
- baseline structural diff and nondeterminism failure
- candidate transformation compiler
- OpenSearch request and response validation
- state-machine transitions and idempotency
- metric eligibility and reason codes
- cost-range and approval-envelope calculations
- proposal schema and canonical hash
- ACL and store-scope checks

Watch each regression test fail for the intended reason before implementing its production behavior.

### Live OpenSearch integration tests

- exact OpenSearch 3.8 image and plugin versions
- security enabled with an allowlisted role
- every required SRW route and failure status
- workbench disabled returns an actionable capability failure
- query-set custom fields and Mustache rendering
- LLM chunking, connector retry, cache hit, overwrite, failure, and partial metadata
- model ID change and document update cache cases
- pairwise and pointwise results
- experiment validation states `VALID`, `DRIFTED`, and `UNAVAILABLE`
- local index-evidence drift when SRW still reports `VALID`
- namespaced cleanup refuses foreign or changed resources

### Mage-OS integration tests

- clean install and declarative schema status
- DI compilation
- cron locking and retry behavior
- exact `search_query` source selection by store
- mapper capture no-op outside explicit capture context
- Luma, GraphQL, and available Hyva request equivalence
- physical index rotation after full reindex
- customer-group, website, and price dimensions
- admin POST, form key, ACL, and store-scope enforcement
- proposal download contains no credential or raw vector data

### Browser tests

- preflight failure explanations
- privacy preview and approval binding
- calibration and disagreement workflow
- spend authorization details
- failures and unrated pairs remain visible
- experiment product comparison and stale state
- export action downloads the exact displayed proposal hash

### Performance and resilience

- snapshot preview on representative 100 thousand, 1 million, and 10 million row synthetic `search_query` tables
- bounded memory while importing up to 1,000 queries and 10,000 ratings
- poller backoff during OpenSearch outage
- Admin grids remain available from local mirrors while OpenSearch is down
- ordinary storefront search shows no material latency regression from the disabled capture hook
- all OpenSearch operations honor configured deadlines and response limits

## 20. V1 release gates

V1 is ready for a private pilot only when:

- Mage-OS 3.4 and OpenSearch 3.8 exact fixture tests pass.
- All required API routes and security actions are recorded from the tagged source and live cluster.
- Capability failures are actionable and never become generic Admin 500 errors.
- Query snapshots are immutable, content addressed, store scoped, privacy previewed, and idempotent.
- Baseline capture has round-trip equality for every supported request surface.
- Candidate compilation is limited to validated mappings and scalar templates.
- Index drift invalidates decision eligibility even when SRW input validation stays valid.
- LLM disclosure and authorization match the submitted envelope.
- No connector credential enters Magento storage, logs, or browser payloads.
- Cache reuse cannot cross a changed model, prompt, context value, query snapshot, configuration, or index-evidence identity.
- Partial and unrated judgments remain visible and cannot pass coverage gates.
- Uncalibrated LLM results remain exploratory.
- `WINNER` requires all registered metric, guardrail, coverage, freshness, and human-acceptance gates.
- Proposal export is reproducible and cannot apply configuration.
- Cron cannot submit paid work or mutate live search.
- Cleanup can affect only exact owned resources after a dry-run preview.
- Clean install, upgrade, disable, and uninstall behavior are documented and tested.
- No unresolved P0 or P1 defect remains.
- Product, license, trademark, affiliation, and privacy review is complete.

## 21. Post-v1 roadmap

Prioritize only after pilot evidence:

1. **Native Mage-OS application adapter**: support exact configuration mappings only, with diff, reindex impact, inverse values, fresh confirmation, apply, verification, and rollback. Requalify the Mapper seam on every supported Mage-OS release.
2. **Hybrid replacement-generation adapter**: convert an allowlisted proposal into the hybrid module's own preview and replacement-generation workflow.
3. **Search regression monitoring**: prepare scheduled runs, alert only on registered threshold changes, and suppress known reindex windows.
4. **Zero-result triage**: measured synonym and redirect proposals, still human approved.
5. **Observed context and UBI**: collect consent-reviewed query context and implicit judgments.
6. **Revenue guardrails**: separate live exposure and conversion attribution. Offline metrics predict; revenue decides.
7. **Hybrid optimizer UI**: only for supported two-clause hybrid configurations and only through a compatible target adapter.
8. **ElasticSuite evaluation adapter**: evaluation first, application only if exact integration contracts are proven.

Do not add live shopper traffic assignment to this roadmap without a separate privacy, experiment-design, attribution, and rollback plan.

## 22. Port to Mage-OS Lab

The temporary Rocket Web repository is the incubation surface. Moving to Mage-OS Lab is a separate release decision.

Before the port:

- freeze and verify the exact v1 source tree
- decide the accepted Magento module and Composer identities with Mage-OS Lab maintainers
- complete OSL-3.0, AFL-3.0, third-party notice, and trademark review
- remove Rocket Web-only CI, secrets, links, CODEOWNERS, package metadata, and internal assumptions
- scan the full history and release artifact for credentials and customer data
- reproduce the public fixture from a clean checkout
- verify Composer install, DI compile, schema, unit, integration, security, and browser tests
- decide whether Mage-OS Lab receives reviewed history or a fresh root snapshot
- prepare migration notes if package identity changes

Do not push, transfer, publish, tag, or release to Mage-OS Lab without explicit approval of the exact repository, artifact, history, and destination.

## 23. Open decisions before implementation

Phase 0 should resolve these, not hide them in later work:

1. Final module and Composer identity.
2. Exact standard OpenSearch 3.8 distribution and plugin image digest for support.
3. Low-level `opensearch-php 2.5.1` transport call and test seam.
4. Least-privilege Security plugin action list for read, run, and cleanup roles.
5. Whether managed Amazon OpenSearch Service can meet the same plugin, setting, connector, and permission contract.
6. Baseline capture equality across Luma, GraphQL, and Hyva.
7. A stable physical-index evidence fingerprint with acceptable read cost.
8. Cache behavior after model change, document update, index rotation, and prompt change.
9. Merchant-understandable calibration scale and agreement threshold.
10. Pilot limits for queries, depth, token envelope, retention, and polling duration.
11. Whether query text needs module-level encryption beyond the database trust boundary.
12. Product ID resolution for stock and hybrid indices.

## 24. Primary references

- [OpenSearch 3.8 release overview](https://opensearch.org/blog/whats-new-in-opensearch-3-8/)
- [OpenSearch 3.8 Search Relevance Workbench](https://docs.opensearch.org/3.8/search-plugins/search-relevance/using-search-relevance-workbench/)
- [OpenSearch 3.8 judgments](https://docs.opensearch.org/3.8/search-plugins/search-relevance/judgments/)
- [Search Relevance plugin tag 3.8.0.0](https://github.com/opensearch-project/search-relevance/tree/3.8.0.0)
- [Mage-OS releases](https://mage-os.org/product/releases/)
- [Mage-OS source tag 3.4.0](https://github.com/mage-os/mageos-magento2/tree/3.4.0)
- [ML Commons supported connector blueprints](https://docs.opensearch.org/3.8/ml-commons-plugin/remote-models/supported-connectors/)
