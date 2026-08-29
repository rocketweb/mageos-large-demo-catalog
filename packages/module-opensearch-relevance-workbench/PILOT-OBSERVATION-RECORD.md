# Phase 3 Pilot Observation Record

Copy this file for one observed pilot. Do not overwrite the template. Complete the preregistration section before experiment results are visible.

## Record identity

| Field | Value |
|---|---|
| Pilot identifier | |
| Observation identifier | |
| Participant code | |
| Observer | |
| Observation date | |
| Environment identifier | |
| Store ID | |
| Raw evidence location, restricted and opaque | |

## Preregistered limits and exit rule

| Field | Value |
|---|---|
| Quiet-window start and end in UTC | |
| Source query window | |
| Sampling limits | |
| Curated fields | |
| Candidate field and boost | |
| Primary metric and minimum improvement | |
| Maximum session duration | |
| Maximum clarifying assists | |
| Required return-session behavior | |
| Exact exit rule | |
| Approved by and approved at | |

## Environment evidence

| Evidence | Value |
|---|---|
| Mage-OS version | |
| PHP version | |
| OpenSearch version | |
| Search Relevance plugin version | |
| ML Commons plugin version | |
| Target alias | |
| Physical index | |
| Document count | |
| Starting index-evidence SHA-256 | |
| Ending index-evidence SHA-256 | |
| Catalog activity during observation | |

## Task record

Use one row per task from `PILOT-OBSERVATION-PLAN.md`.

| Task | Started | Ended | Result | Assistance | Confusion or error | Evidence identity |
|---|---|---|---|---|---|---|
| 1. Establish readiness | | | | | | |
| 2. Prepare and approve snapshot | | | | | | |
| 3. Capture baseline and build candidate | | | | | | |
| 4. Create human judgment | | | | | | |
| 5. Run experiments and review evidence | | | | | | |
| 6. Export review-only proposal | | | | | | |
| 7. Review scheduled work | | | | | | |
| 8. Preview cleanup eligibility | | | | | | |

## Artifact identities

| Artifact | UUID or SHA-256 |
|---|---|
| Query snapshot UUID | |
| Query snapshot SHA-256 | |
| Baseline UUID | |
| Candidate UUID | |
| Human judgment UUID | |
| Experiment UUID | |
| Proposal UUID | |
| Proposal SHA-256 | |
| Schedule UUID | |
| Scheduled draft UUID | |

## Participant interpretation

Record a close paraphrase. Do not copy raw query text or customer data.

| Question | Participant answer |
|---|---|
| What changed between baseline and candidate? | |
| What evidence would block acceptance? | |
| Is the index evidence fresh? How do you know? | |
| What did the schedule do? | |
| What did proposal export change on the storefront? | |
| Can this screen delete remote resources? | |
| Would this monthly workload be acceptable? Why? | |

## Findings

| Finding | Task | Severity | Evidence | Resolution required before exit |
|---|---|---|---|---|
| | | | | |

## Outcome

| Measure | Result |
|---|---|
| Total elapsed time | |
| Highest assistance level | |
| Clarifying assist count | |
| Tasks completed without takeover | |
| Safety comprehension passed | |
| Unresolved P0 count | |
| Unresolved P1 count | |
| Unresolved P2 count | |
| Preregistered exit rule passed | |
| Final result | `PASS`, `CONDITIONAL`, `FAIL`, or `INVALID_OBSERVATION` |

## Review

| Field | Value |
|---|---|
| Observer signature and date | |
| Product owner review and date | |
| Material protocol deviation | |
| Follow-up issue references | |
| Phase 3 findings updated | |

This record does not authorize a commit, push, deployment, release, live-search mutation, remote deletion, or Phase 4 start.
