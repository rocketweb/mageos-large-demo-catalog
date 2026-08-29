# Phase 3 pilot execution runbook

Status: execution ready, not approved or executed

This runbook turns the observation protocol into an operating sequence. It does not replace `PILOT-OBSERVATION-PLAN.md`, and it does not allow a developer rehearsal to count as merchant evidence.

## The outcome required

Observe one merchant operator completing the human-only monthly workflow in Magento Admin. The operator must complete an initial session and a return session beginning from a scheduled draft. The observer records time, assistance, confusion, safety comprehension, and immutable artifact identities without taking control of the interface.

The observation answers one question: is the monthly workflow usable and correctly understood by the merchant?

It does not evaluate revenue lift, production capacity, LLM quality, or live search application.

## Roles

| Role | Responsibility |
| --- | --- |
| Pilot owner | Approves the exact environment, participant, protocol, limits, and evidence location |
| Merchant participant | Uses the workflow and explains what the evidence means |
| Observer | Reads the briefing, records evidence and assistance, and never completes a task for the participant |
| Environment owner | Provides the approved non-production or production-like environment and declares the quiet catalog window |
| Product owner | Reviews the frozen record and applies the preregistered exit rule |

One person may hold more than one owner role. The merchant participant cannot also be the observer.

## Choose the right environment

A valid pilot uses a customer-owned non-production environment or an explicitly approved production-like evaluation environment with a representative catalog and approved search terms.

The generated large-catalog fixture is useful for rehearsal only. It proves that 1,200 Magento product entities and 816 storefront-indexed documents work through the technical flow. Its generic products and synthetic query history cannot satisfy the merchant-observation gate.

Do not install or deploy the module to a customer environment without approval for that exact environment and source artifact.

## Before scheduling the participant

The pilot owner and environment owner complete these steps:

1. Approve the exact environment, module source artifact, participant, observer, date, and evidence location.
2. Record Mage-OS, PHP, OpenSearch, Search Relevance, and ML Commons versions.
3. Confirm the environment uses stock Mage-OS OpenSearch for the selected store.
4. Confirm the participant has only the ACLs required for the eight observation tasks.
5. Confirm no LLM connector, paid judgment path, proposal apply path, or remote delete action is available.
6. Select a quiet catalog window and pause or account for imports, reindexing, and other catalog writes.
7. Select a representative store view and a privacy-reviewed source query window.
8. Decide whether `category_id`, `brand_value`, neither, or both will be curated.
9. Select one eligible candidate field and boost before experiment results are visible.
10. Approve the maximum session duration, clarifying-assist limit, return-session behavior, and exact exit rule.
11. Prepare an approved restricted location for raw notes or recordings. Do not store customer data or raw query text in this repository.

Stop preparation if any exact environment, role, data, or evidence-location approval is missing.

## Technical readiness check

Run these checks in the approved environment before inviting the participant:

1. Open **Marketing > OpenSearch Relevance Workbench**.
2. Run the read-only preflight.
3. Confirm `human workflow ready` and record every reason code.
4. Confirm the LLM workflow remains unavailable for this protocol.
5. Record the target alias, resolved physical index, document count, and starting index-evidence SHA-256.
6. Preview the approved query source window without approving it.
7. Confirm privacy exclusions and representative safe terms are available.
8. Confirm no live search change, remote deletion, or paid request occurs during readiness checks.

If readiness requires a workaround, record it before the session. A hidden workaround invalidates the observation.

## Freeze preregistration

Copy `PILOT-OBSERVATION-RECORD.md` to the approved evidence location. Complete every field in **Preregistered limits and exit rule** before the participant sees experiment results.

Record the file identity or approved document revision. After this point, do not silently change:

- the source query window or sampling limits;
- the curated fields;
- the candidate field or boost;
- the primary metric or minimum improvement;
- the session or assistance limits;
- the return-session behavior;
- the exit rule.

If a change is necessary, preserve the original, record the replacement, reason, approver, and time, then classify the observation under the preregistered decision procedure.

## Initial observation session

Read the participant briefing from `PILOT-OBSERVATION-PLAN.md` without demonstrating any controls. Then ask the participant to complete Tasks 1 through 6 in order:

1. establish readiness;
2. preview and approve the exact query snapshot;
3. capture the baseline and build the preregistered candidate;
4. complete the human rating queue;
5. run or resume experiments and review evidence;
6. export the review-only proposal.

For every task, record:

- start and end time;
- result;
- highest assistance level;
- confusion or error;
- relevant local UUID or SHA-256 identity.

The observer may answer terminology questions at `A1`. Any assistance above `A1` must be recorded at the moment it occurs. `A4` means the participant did not independently complete the task.

## Return observation session

The return session must begin from a scheduled draft prepared under the preregistered policy. Ask the participant to complete Tasks 7 and 8:

7. review what the schedule prepared and decide whether to approve the exact draft;
8. inspect owned-resource cleanup eligibility and confirm that no delete action is available.

The participant must distinguish schedule approval from snapshot approval and state that cron did not spend money, run experiments, export a proposal, or change live search.

## Stop conditions

Stop immediately and preserve evidence if the participant or observer encounters:

- a live search mutation;
- a paid request;
- a connector credential, token, or session secret;
- customer data outside the approved boundary;
- an available remote delete action;
- an environment change that invalidates the quiet window;
- an index-evidence change that is presented as fresh;
- an observer takeover required to continue a core task.

Classify potential mutation, spend, credential, privacy, or unauthorized deletion as `P0`. A core workflow failure or materially wrong decision is `P1`.

## Freeze the record before discussing fixes

After the return session:

1. record the ending index-evidence SHA-256 and catalog activity;
2. complete the participant-interpretation table using close paraphrases;
3. classify every finding by task and severity;
4. complete the outcome measures;
5. record `PASS`, `CONDITIONAL`, `FAIL`, or `INVALID_OBSERVATION`;
6. freeze the record identity;
7. only then discuss fixes or protocol changes.

Do not rewrite the observation after learning which result is more convenient.

## Apply the roadmap gate

Phase 3 exits only when the approved exit rule passes and no unresolved P0 or P1 remains. A `CONDITIONAL` result remains open until every condition is separately verified.

After review, update `PHASE-3-FINDINGS.md` with the sanitized result and evidence identities. Do not include raw query text, customer data, credentials, unrestricted screenshots, or private commercial terms.

Even a valid Phase 3 pass does not start Phase 4 while Phase 2 remains blocked. Starting a human-only release candidate requires an explicit revision to `IMPLEMENTATION-PLAN.md`. Waiting for a qualified LLM runtime preserves the existing plan.

No pilot result authorizes commit, push, deployment, release, proposal application, connector changes, paid judgments, or remote deletion.

## Local rehearsal

Use the generated catalog only to rehearse the mechanics before involving a participant:

```bash
composer fixture:mageos:up
MAGEOS_FIXTURE_ROOT=/private/tmp/osrw-mageos-pilot-rehearsal \
MAGEOS_PHP_BINARY=/opt/homebrew/opt/php@8.4/bin/php \
dev/ci/run-large-catalog.sh
composer fixture:mageos:down
```

Label the result `REHEARSAL`. Do not copy its generated products, synthetic queries, deterministic ratings, or fixture acceptance into a merchant observation record.
