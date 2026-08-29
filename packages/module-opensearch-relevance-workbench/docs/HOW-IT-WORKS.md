# How the OpenSearch Relevance Workbench extension works

## Purpose and boundary

OpenSearch Relevance Workbench gives a Mage-OS administrator a controlled way to compare the stock catalog-search query with a narrowly modified candidate, judge exact results, and decide whether that candidate should serve storefront search.

The current private-lab build can activate one supported field-boost candidate and restore the immediately preceding live state. It is not production qualified. It does not provide a qualified LLM judgment workflow, accept arbitrary query DSL, manage connector credentials, change index aliases, or expose remote deletion. Human ratings are the supported judgment source.

The Admin page is under **Marketing > OpenSearch Relevance Workbench**. The module uses Mage-OS's configured OpenSearch client, so it does not introduce another OpenSearch credential store.

## Workflow at a glance

The Admin surface presents six steps and keeps one primary step visible at a time:

1. **Readiness:** run preflight and inspect runtime or regression blockers.
2. **Snapshot:** preview recent Magento search terms and approve an exact immutable query snapshot.
3. **Tune:** capture the stock Mage-OS query and create one candidate by changing approved field boosts.
4. **Judge:** rate the union of baseline and candidate results for five queries.
5. **Compare:** run the offline experiment, inspect NDCG@10, coverage, regressions, and index freshness, then explicitly accept qualifying evidence.
6. **Activate:** recheck exact index evidence, apply the accepted candidate, or restore the prior live state.

An accepted winner can also be downloaded as a content-addressed evidence package. That JSON is evidence, not an import format.

Each durable step stores immutable identities and an append-only audit event. If an upstream identity changes, downstream work is rejected or classified as stale instead of silently being reused.

## 1. Preflight

Preflight reads the configured cluster version, installed OpenSearch plugins, and Search Relevance Workbench statistics. It reports whether the human workflow is ready and includes reason codes when a capability is missing.

The current implementation always reports the LLM workflow as unavailable. Even if the cluster exposes relevant plugin capabilities, the module adds `LLM_JUDGMENT_RUNTIME_UNQUALIFIED` and does not expose an LLM run action.

## 2. Query snapshot preview and approval

The source is Magento's `search_query` table for one active customer store view and an exact date window. The preview policy controls:

- minimum popularity
- positive-result query limit
- zero-result query limit
- total query limit
- whether redirects are eligible

Source reads are ordered by `updated_at` and `query_id` and bounded to 100,000 rows. Preview then:

1. keeps active rows for the selected store;
2. rejects terms below the popularity floor;
3. rejects redirects unless explicitly included;
4. rejects terms matching the privacy policy, including email addresses;
5. normalizes accepted text to Unicode NFC;
6. sorts positive-result and zero-result strata deterministically;
7. applies the stratum and total limits;
8. records the source high-water boundary;
9. hashes the selected entries, policy, metadata, and boundary as canonical JSON.

The preview shows exclusions before anything is approved. Approval must submit the exact preview SHA-256. A different hash fails. Saving the same approved content again returns the existing local snapshot rather than creating another identity.

Optional category and brand metadata is accepted only for queries present in that exact preview. The stored values are marked `MERCHANT_CURATED`, become part of the immutable snapshot hash, and are flattened into remote query-set custom fields only after approval.

Scheduled collection uses the same preview logic, but it saves a local `DRAFT`. Cron cannot approve the draft.

## 3. Stock baseline capture

The baseline is captured from Mage-OS itself rather than reconstructed from assumptions about Magento search.

For the storefront path, the module starts frontend store emulation and executes the stock `quick_search_container` collection twice with two different collision-resistant sentinel terms. A late mapper plugin records the unchanged Mage-OS request for baseline capture before applying any currently active Workbench transformation to the real storefront request. This keeps each comparison anchored to stock behavior even when another candidate is live.

The template compiler compares the two requests recursively. Only locations that changed from sentinel one to sentinel two may become the reserved `{{queryText}}` variable. Any other difference, missing sentinel, reserved-token collision, or partial collision fails capture and reports the exact JSON pointer path.

The captured template is then rendered and executed for the first five approved snapshot queries. The validation evidence stores query hashes, request hashes, and result counts, not raw query text.

Baseline evidence also freezes:

- the target alias emitted by Mage-OS;
- the one physical index behind that alias;
- the OpenSearch index UUID;
- mapping and settings hashes;
- primary-shard boundaries;
- document count;
- mapped field capabilities;
- the exact request template and its hash.

The GraphQL mapper can be qualified through the separate GraphQL capture harness. Storefront and GraphQL requests have separate template identities because their structures are not assumed to be interchangeable.

## 4. Candidate construction

Version 1 supports one candidate transformation: a bounded field boost.

The administrator selects fields from the captured mapping registry. A field is eligible only when it is:

- present in the approved registry;
- searchable;
- non-sensitive;
- non-dynamic;
- mapped as `text` or `keyword`;
- actually present in the captured query template.

Each boost must be between `0.1` and `20.0`. The compiler changes only recognized query field lists and `match`, `match_phrase`, or `match_phrase_prefix` field clauses. It cannot introduce a new query structure, index, pipeline, script, or arbitrary JSON fragment.

The candidate is rendered and executed against the baseline's frozen physical index for the same first five approved queries. It is persisted only after all five validation searches complete.

## 5. Human rating queue

The queue rechecks that the current alias, physical index, mapping, settings, shards, and document count still match the baseline evidence. A changed index blocks rating and requires a fresh baseline.

For the first five approved queries, the module executes baseline and candidate templates to a depth of ten. It builds the de-duplicated union of both result lists and shows each product's name, SKU, baseline rank, and candidate rank.

The reviewer assigns one of three relevance grades:

- `0`: not relevant
- `0.5`: partially relevant
- `1`: relevant

The immutable judgment set binds every rating to the query hash, document ID, reviewer, rating time, query snapshot, and index evidence. Partial forms and changed identities are rejected.

## 6. Experiment execution

A human experiment requires one compatible approved snapshot, baseline, candidate, and judgment set. Compatibility checks require the same store and frozen index identity.

The module materializes owned OpenSearch Search Relevance Workbench resources with deterministic names and exact local-to-remote bindings:

- one query set;
- one baseline search configuration;
- one candidate search configuration;
- one imported pointwise human judgment;
- one pairwise experiment;
- one pointwise baseline experiment;
- one pointwise candidate experiment.

Before reusing an existing remote resource, the module reads it back and compares its name and content identity with the local immutable artifact. A mismatch fails closed. Repeating an experiment with the same inputs resumes the same local and remote identities.

The remote runs are polled to completion and validated through Search Relevance Workbench. The final decision evidence is computed locally from the bounded result lists and human ratings.

## 7. Evidence and acceptance

The primary metric is NDCG@10. The module also computes judged coverage over the baseline and candidate result union and checks known-item regressions.

The default eligibility sequence is:

1. `STALE` if index evidence changed.
2. `PARTIAL` if judged coverage is below `1.0`.
3. `INCONCLUSIVE` if a known-item query regressed.
4. `INCONCLUSIVE` if NDCG improvement is below `0.01`.
5. `EXPLORATORY` if the evidence otherwise qualifies but has not been accepted by a merchant.
6. `WINNER` only after explicit merchant acceptance.

Offline relevance evidence is not treated as evidence of revenue lift. Acceptance means the reviewer accepts this exact offline result as eligible for a separate activation decision. Acceptance alone does not change storefront search.

The evidence view reconstructs before-and-after product movement by document ID. If a product has since disappeared, it remains in the historical evidence as `Product unavailable`. The index is marked stale and proposal creation is blocked until the workflow is recaptured.

## 8. Evidence package

Proposal export requires an explicitly accepted `WINNER`. Immediately before export, the module rechecks the experiment, store, baseline hash, candidate hash, target alias, physical index, and current index evidence.

The downloaded JSON is canonical and content addressed. It contains the candidate transformation, immutable evidence identities, aggregate evidence, and warnings. It excludes approved query text. The original artifact schema still declares:

```json
{
  "target_type": "review_only",
  "application": {
    "supported": false
  }
}
```

There is no artifact import operation. Activation reads the already accepted, validated candidate and evidence from local persistence, so editing a downloaded JSON file cannot change storefront behavior.

## 9. Live activation and rollback

Activation is a separate POST action protected by the `apply_live_configuration` ACL. The activation service reloads the completed experiment and refuses the action unless all of these remain true:

- experiment state is `ACCEPTED`;
- evidence eligibility is `WINNER`;
- accepting administrator and time are present;
- experiment baseline, candidate, and SHA-256 identities match their persisted records;
- store, parent baseline, physical index, and index-evidence identities match exactly;
- a fresh evidence capture for the target alias has the same SHA-256 as the frozen baseline.

If the gate passes, the module appends an `APPLY` event and advances the store's current-state pointer in one database transaction. The event includes the store, accepted experiment, candidate, bounded transformation, candidate hash, index-evidence hash, target alias, actor, time, and previous activation UUID. The exact current candidate is not shown as actionable in Admin, and the repository rejects a duplicate apply. This preserves a meaningful rollback predecessor.

At storefront query time, the mapper plugin reads that store's current activation once per request. It applies only to the qualified `quick_search_container` surface; GraphQL and other mapper request types remain unchanged. `FIELD_BOOST` can only replace boosts in existing `fields`, `match`, `match_phrase`, and `match_phrase_prefix` structures. It cannot add a new index, pipeline, script, filter, or arbitrary clause. A missing state row means stock search. Any runtime read or validation failure is logged and returns the unchanged Mage-OS query.

Rollback does not edit or delete the old event. It appends a `ROLLBACK` event containing the restored transformation and advances the pointer. If the applied candidate had no earlier Workbench state, rollback restores stock search. Repeating rollback acts as an undo because every event records the state it replaced.

This is a private-lab mechanism. Production release still requires the roadmap's merchant observation, release, failure, and operational gates.

## 10. Scheduling and remote cleanup

The default cron job runs every 15 minutes and checks approved snapshot schedules that are due. A per-schedule lock prevents overlapping preparation. A due schedule can only save a new local draft and advance its next-run time. Failures are logged and do not approve or run anything.

Scheduled work cannot:

- approve a snapshot;
- create human or paid judgments;
- run experiments;
- accept evidence;
- export evidence;
- activate or roll back storefront search.

The cleanup area is also preview only. It enumerates remote resources bound to local artifacts, reads each remote resource, and verifies deterministic ownership and exact content identity. It reports eligibility and reason codes. No remote delete controller or service is exposed.

## Storage and audit model

The module creates twelve tables:

| Table | Purpose |
| --- | --- |
| `osrw_snapshot_schedule` | Approved draft-preparation policies and next-run state |
| `osrw_query_snapshot` | Draft and approved snapshot headers |
| `osrw_query_snapshot_entry` | Approved or draft query entries and curated metadata |
| `osrw_index_evidence` | Frozen alias, physical-index, mapping, settings, shard, and count evidence |
| `osrw_search_configuration` | Baseline and candidate templates and remote bindings |
| `osrw_human_rating` | Immutable query-document relevance grades |
| `osrw_judgment_run` | Imported judgment identity and remote binding |
| `osrw_experiment` | Immutable experiment inputs, remote IDs, and local evidence |
| `osrw_proposal` | Canonical non-executable evidence packages |
| `osrw_live_activation` | Append-only apply and rollback events with exact evidence and prior-state identity |
| `osrw_live_state` | One current activation pointer and monotonic version per store |
| `osrw_audit_event` | Append-only actor, action, identity, result, and correlation records |

The live tables contain only bounded transformation, evidence, actor, and pointer state. The schema has no credential, provider token, raw vector, arbitrary query DSL, or connector secret storage.

## Permissions

The Magento ACL separates viewing from each material preparation or approval step:

- view status and results;
- preview query data;
- approve snapshots;
- curate ratings;
- manage configurations;
- run and accept experiments;
- export evidence packages;
- activate and roll back a live configuration;
- authorize paid judgments, reserved but not implemented in the current workflow;
- manage schedules and settings;
- preview owned remote resources.

All state-changing Admin actions use POST requests and Magento form-key validation.

## Operating limits

- At least five approved queries are required for baseline capture, candidate validation, and the rating queue.
- The human rating workflow always evaluates five queries to depth ten in version 1.
- Snapshot preview can select up to the policy's configured limit, while source reads are capped at 100,000 rows.
- A catalog reindex, alias switch, mapping change, settings change, shard change, or document-count change invalidates frozen index evidence.
- The module can create owned evaluation resources in OpenSearch and apply one locally persisted field-boost transformation at query time. It cannot mutate aliases, mappings, index settings, search pipelines, or arbitrary remote search configuration.
- LLM judgment, automated paid work, production rollout, and revenue validation remain outside the qualified boundary.

## Verification

Run the local code gates:

```bash
composer test:unit
composer lint
composer analyse
```

Run the deterministic installed Mage-OS workflow:

```bash
composer fixture:mageos:up
MAGEOS_FIXTURE_ROOT=/private/tmp/osrw-mageos-contract \
MAGEOS_PHP_BINARY=/opt/homebrew/opt/php@8.4/bin/php \
dev/ci/run.sh
composer fixture:mageos:down
```

For the larger real-product catalog lane, see [Test catalogs](TEST-CATALOGS.md).
