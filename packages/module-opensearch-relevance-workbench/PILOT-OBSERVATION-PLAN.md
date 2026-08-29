# Phase 3 Pilot Observation Plan

Date prepared: 2026-08-27

Status: prepared for review, not yet approved or executed

Execution sequence: [PILOT-RUNBOOK.md](PILOT-RUNBOOK.md)

This protocol is the evidence boundary for the remaining Phase 3 exit criterion: the monthly workflow is usable in pilot observation. It does not itself satisfy that criterion. A fixture run, developer browser test, or observer completing the tasks on the merchant's behalf is not pilot usability evidence.

## 1. Objective

Observe whether a merchant operator can complete and understand the human-judged monthly workflow in Magento Admin without OpenSearch Dashboards and without changing live storefront search.

The observation must answer:

1. Can the operator find and complete the required steps?
2. Can the operator explain what the evidence says and what it does not say?
3. Can the operator recognize stale or incomplete evidence and recover safely?
4. Can the operator distinguish a scheduled draft from an approved snapshot?
5. Can the operator export a review-only proposal without believing it was applied?
6. What assistance, elapsed time, and support burden does the workflow require?

## 2. Scope and safety boundary

The pilot covers the existing human-only workflow:

- preflight
- query preview and exact snapshot approval
- stock baseline capture
- guided field-boost candidate creation
- human rating queue
- offline experiments and evidence review
- explicit acceptance of otherwise-winning evidence
- review-only proposal export
- scheduled local draft preparation and review
- exact owned-resource cleanup preview

The pilot does not cover:

- an LLM judgment source or external model spend
- connector creation or credentials
- proposal application
- live configuration mutation
- OpenSearch Hybrid activation or generation changes
- remote resource deletion
- production claims, conversion claims, or revenue claims

Any unexpected live-search mutation, paid request, credential exposure, or ability to delete a resource is a stop condition.

## 3. Pilot environment prerequisites

Complete these checks before inviting a participant:

- [ ] Use a customer-owned non-production environment or an explicitly approved production-like evaluation environment.
- [ ] Record the exact Mage-OS, PHP, OpenSearch, Search Relevance, and ML Commons versions.
- [ ] Confirm the participant has only the ACLs needed for the observed tasks.
- [ ] Confirm the module cannot apply a proposal or mutate live search configuration.
- [ ] Confirm no LLM connector or paid judgment path is configured for this protocol.
- [ ] Declare a quiet catalog window with start and end times in UTC.
- [ ] Pause or account for catalog imports, reindexing, and other writes that would invalidate physical-index evidence.
- [ ] Confirm the current target alias, resolved physical index, document count, and index-evidence SHA-256.
- [ ] Select a representative store view and exclude customer-specific or sensitive query terms.
- [ ] Agree where restricted raw observation notes may be stored. Do not put customer data or raw query text in this repository.
- [ ] Verify a rollback is unnecessary because the workflow has no apply path. Prepare exact owned-resource cleanup preview instructions for evaluation artifacts.

## 4. Preregistration

The pilot owner must complete and approve this section before the participant sees experiment results.

| Field | Preregistered value |
|---|---|
| Pilot identifier | |
| Participant code | |
| Participant role | |
| Prior Magento Admin experience | |
| Prior search-relevance experience | |
| Store ID and store label | |
| Environment identifier | |
| Quiet-window start and end in UTC | |
| Source query window | |
| Minimum popularity | |
| Positive-result limit | |
| Zero-result limit | |
| Total snapshot limit | |
| Included curated fields | `category_id`, `brand_value`, neither, or both |
| Candidate field | |
| Candidate boost | |
| Primary metric | `NDCG@10` |
| Minimum improvement | `0.01`, unless the implementation plan is explicitly revised before results |
| Maximum session duration | |
| Maximum clarifying assists | |
| Required return-session behavior | |
| Approved observer | |
| Approved exit rule | |

### Proposed minimum exit rule

This is a recommendation for approval, not a settled product decision:

1. One merchant operator completes an initial end-to-end session and a return session that begins from a scheduled draft.
2. The observer never takes control of the interface.
3. No unresolved P0 or P1 usability defect remains.
4. The operator correctly states that no live search change, remote deletion, or paid judgment occurred.
5. The operator identifies at least one improved query, one regression or guardrail state, and the current freshness state from the evidence screen.
6. The operator handles a stale or unavailable product case without treating it as fresh decision evidence.
7. The operator distinguishes `DRAFT`, `APPROVED`, `EXPLORATORY`, `WINNER`, and `STALE` at the point each matters.
8. Assistance count and session duration remain within the preregistered limits.

If this proposed rule is changed after results are visible, record the original rule, revised rule, reason, approver, and time. Do not silently move the gate.

## 5. Participant briefing

Read this briefing without demonstrating the controls:

> This Magento Admin workflow compares a captured stock search configuration with one guided candidate using offline evidence. It can create local evaluation records and owned Search Relevance evaluation resources. It cannot apply a proposal, change live storefront search, delete remote resources, or submit paid model work. Please work as you normally would. Think aloud when something is unclear. Ask for help when you need it. We are testing the workflow, not you.

Do not tell the participant where each button is or how to interpret a result unless they request assistance. Record assistance immediately using the levels below.

## 6. Observation tasks

### Task 1: Establish readiness

Ask the participant to open the Workbench and determine whether the human workflow is ready.

Observe whether they can:

- run the read-only preflight
- identify the target store and OpenSearch compatibility state
- distinguish human-workflow readiness from LLM-workflow readiness
- explain whether the workflow can change live search

### Task 2: Prepare and approve an exact query snapshot

Ask the participant to prepare a snapshot using the preregistered source and sampling limits.

Observe whether they can:

- review source and selected counts
- notice privacy exclusions
- add only merchant-curated category or brand values when preregistered
- rebuild after metadata changes
- understand that metadata provenance changes the displayed SHA-256 identity
- approve only the exact displayed snapshot

### Task 3: Capture the baseline and build one candidate

Ask the participant to capture the stock baseline and create the preregistered field-boost candidate.

Observe whether they can:

- choose an eligible snapshot
- understand target alias versus physical index evidence
- select an allowlisted mapped field
- interpret validation success or failure
- recognize that raw query DSL is not editable

### Task 4: Create the human judgment

Ask the participant to prepare and complete the rating queue.

Observe whether they can:

- understand the baseline and candidate result union
- apply `0.0`, `0.5`, and `1.0` consistently
- identify the query and product context needed for a rating
- finish without assuming an LLM supplied the result
- estimate whether the manual workload is acceptable for a monthly workflow

### Task 5: Run experiments and review evidence

Ask the participant to run or resume the offline experiments and decide whether the evidence is acceptable for export.

Observe whether they can:

- distinguish pairwise and pointwise remote experiments from the local decision gate
- find baseline NDCG@10, candidate NDCG@10, delta, and coverage
- inspect moved, added, dropped, and unavailable products
- find known-item regressions and reason codes
- identify `FRESH`, `STALE`, `PARTIAL`, and `UNAVAILABLE` evidence
- understand when merchant acceptance is allowed and when it is blocked

### Task 6: Export the review-only proposal

Ask the participant to export the accepted evidence.

Observe whether they can:

- distinguish evidence acceptance from live application
- identify the source experiment and artifact SHA-256
- explain what another reviewer would need to verify the proposal
- state what changed on the storefront as a result of export

The correct answer to the final item is: nothing changed on the storefront.

### Task 7: Review scheduled work

Use a due schedule or an already prepared scheduled draft. Ask the participant to review what cron prepared.

Observe whether they can:

- distinguish schedule approval from snapshot approval
- recognize that cron prepared a local draft only
- inspect the draft query count before approval
- approve the exact draft separately or leave it unapproved
- explain whether cron spent money, ran experiments, exported a proposal, or changed live search

### Task 8: Preview owned-resource cleanup eligibility

Ask the participant to inspect the cleanup preview without deleting anything.

Observe whether they can:

- identify local and remote resource identities
- interpret exact match versus a failed identity gate
- explain why a mismatched resource must fail closed
- confirm that no delete action is available

## 7. Assistance levels

Record the highest assistance level used for each task:

| Level | Definition |
|---|---|
| `A0` | No assistance |
| `A1` | Participant asks for terminology clarification; observer does not identify a control |
| `A2` | Observer points to the correct screen or section |
| `A3` | Observer explains the next action or interpretation |
| `A4` | Observer takes control or completes the action |

An `A4` means the participant did not independently complete that task. It is not a pass hidden behind observer assistance.

## 8. Defect severity

| Severity | Definition | Required action |
|---|---|---|
| `P0` | Potential live mutation, paid request, credential exposure, privacy breach, or unauthorized deletion | Stop the pilot immediately |
| `P1` | Core workflow cannot be completed, or the interface causes a materially wrong decision | Block Phase 3 exit |
| `P2` | Workflow completes only with repeated assistance, misleading terminology, or a material support burden | Fix or explicitly accept before exit |
| `P3` | Localized clarity, layout, or polish issue with a safe workaround | Track with evidence |

## 9. Evidence handling

The shareable observation record may contain:

- participant code, never a customer name
- task timing and assistance levels
- module-local UUIDs and SHA-256 identities
- status labels and reason codes
- sanitized defect descriptions
- the participant's paraphrased interpretation

It must not contain:

- connector credentials, tokens, cookies, or session identifiers
- raw query text
- customer names, emails, addresses, or order data
- unrestricted product descriptions or screenshots
- unpublished commercial terms

Store consented raw notes and recordings in an approved restricted system. Link them by an opaque evidence identifier only.

## 10. Decision procedure

After the observation:

1. Freeze the completed observation record before fixes are discussed.
2. Classify every finding by severity and task.
3. Separate product defects from environment failures and observer mistakes.
4. Compare actual assistance and duration with the preregistered limits.
5. Confirm every safety-comprehension answer from contemporaneous notes.
6. Apply the preregistered exit rule without amendment.
7. Record one result: `PASS`, `CONDITIONAL`, `FAIL`, or `INVALID_OBSERVATION`.
8. A `CONDITIONAL` result does not exit Phase 3 until every stated condition is verified.
9. Update `PHASE-3-FINDINGS.md` only after the result and evidence record are reviewed.
10. Do not start Phase 4 merely because the participant completed some tasks.

Use [PILOT-OBSERVATION-RECORD.md](PILOT-OBSERVATION-RECORD.md) for each observed session.
