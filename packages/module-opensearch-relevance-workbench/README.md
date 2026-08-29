# OpenSearch Relevance Workbench for Mage-OS

This repository contains a locally verified human workflow, a controlled private-lab activation path, and the Phase 3 technical deliverables for merchant-facing search relevance evaluation on Mage-OS 3.4 and OpenSearch 3.8.

It is not production ready. A task-oriented Magento Admin workflow covers the human-judged offline evaluation loop, evidence review, merchant-curated metadata, draft-only scheduling, accepted-candidate activation, current live-state visibility, and rollback. Activation is limited to the module's bounded field-boost transformation and requires a fresh, explicitly accepted winning experiment. There is no qualified LLM judgment path or connector credential handling. Phase 3 still requires observed pilot usability before it can exit.

## What is proven locally

- Query sets, Mustache search configurations, imported human judgments, pointwise experiments, validation, and owned cleanup work against the exact pinned OpenSearch 3.8 image.
- An administrator can move through Readiness, Snapshot, Tune, Judge, Compare, and Activate without OpenSearch Dashboards. Only one primary workflow step is visible at a time.
- An explicitly accepted winner can be activated for its store view after an immediate exact index-evidence recheck. The active candidate, actor, evidence hash, target alias, and prior state are visible and append-only audited. An exact already-live candidate cannot be applied again.
- Storefront field boosts are applied to Mage-OS's mapped OpenSearch query at runtime. Missing or unreadable activation state fails open to the unchanged stock query.
- Rollback creates another immutable activation event and restores the immediately preceding live state, including stock search when no earlier candidate exists.
- The offline decision gate computes local NDCG@10, requires complete judged coverage, rejects known-item regressions and sub-threshold improvements before merchant acceptance, and rechecks physical-index evidence.
- Local experiment identities freeze the exact snapshot, baseline, candidate, judgment, index evidence, result depth, metric, and improvement threshold. A rerun reuses the exact owned remote IDs and refuses changed accepted evidence.
- Evidence-package export requires an explicitly accepted winner, verifies its persisted artifact hash on read, excludes query text, and remains non-executable. Live activation uses the accepted persisted candidate directly rather than importing JSON.
- Physical index evidence detects catalog drift independently of Search Relevance Workbench validation.
- Before-and-after product evidence classifies moved, added, and dropped results, preserves known-item regressions, and tolerates deleted documents as unavailable context.
- Proposal creation rechecks frozen baseline, store, target alias, physical-index evidence, and current index state even when a proposal already exists.
- Optional category and brand metadata is merchant curated, provenance labeled, included in the immutable snapshot hash, and flattened into the remote query-set payload only after exact approval.
- An approved schedule can prepare local query snapshot drafts only. Cron cannot approve snapshots, run judgments or experiments, export evidence, spend money, or activate search.
- The owned-resource cleanup surface is an exact-identity preview for bound query sets, configurations, judgments, and experiments. No remote delete action is exposed.
- A restricted OpenSearch Security role can use the tested routes without reading catalog documents or cluster settings.
- Mage-OS 3.4 on PHP 8.4 compiles with the module installed and reaches Search Relevance through the store-configured OpenSearch client.
- Luma, licensed Hyvä 1.5.2, and GraphQL mapper requests each pass two-sentinel compilation and five-query round-trip validation.
- Storefront and GraphQL produce different templates and remain separate baseline types.

Start with [How the extension works](docs/HOW-IT-WORKS.md) for the operator and developer workflow. [Roadmap status](ROADMAP-STATUS.md) records the current phase gates. [Test catalogs](docs/TEST-CATALOGS.md) explains the exact eight-document contract fixture and the opt-in real-product catalog lane. [Pilot runbook](PILOT-RUNBOOK.md) is the execution sequence for the remaining Phase 3 observation gate.

The live contract evidence is in [PHASE-0-FINDINGS.md](PHASE-0-FINDINGS.md). The completed local human workflow is in [PHASE-1-FINDINGS.md](PHASE-1-FINDINGS.md). The Phase 3 technical evidence and remaining pilot gate are in [PHASE-3-FINDINGS.md](PHASE-3-FINDINGS.md). The prepared pilot protocol and record template are in [PILOT-OBSERVATION-PLAN.md](PILOT-OBSERVATION-PLAN.md) and [PILOT-OBSERVATION-RECORD.md](PILOT-OBSERVATION-RECORD.md). The full product boundary is in [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md).

## Requirements

- PHP 8.3, 8.4, or 8.5 for the module quality gates
- Mage-OS 3.4.x
- OpenSearch 3.8.0 with Search Relevance Workbench and ML Commons 3.8.0.0
- Docker for live integration fixtures

## Local quality gates

```bash
composer install
composer test:unit
composer lint
composer analyse
```

## Live OpenSearch contracts

```bash
composer fixture:up
composer test:integration
composer fixture:down

composer fixture:security:up
composer test:security
composer fixture:security:down
```

The LLM cache probe is intentionally excluded from the passing gate. The untouched OpenSearch 3.8.0 distribution does not provide a qualified LLM judgment path for this module. The diagnostic derivative is not a supported production image. See the findings documents for the exact failures and release boundary.

## Mage-OS qualification

The public fixture installs Mage-OS 3.4.0 on PHP 8.4 with MySQL 8.4 and the exact pinned OpenSearch image. It verifies the baseline surfaces, the complete persisted Phase 1 workflow, and the Phase 3 technical safety gates:

```bash
composer fixture:mageos:up
MAGEOS_PHP_BINARY=/opt/homebrew/opt/php@8.4/bin/php dev/ci/run.sh
composer fixture:mageos:down
```

Use a new `MAGEOS_FIXTURE_ROOT` for every run. The runner refuses to overwrite an existing path.

The fixture uses deterministic catalog and rating data, including an explicit test acceptance, to prove the state machine, export gate, stale-product behavior, exact cleanup preview, metadata provenance, and draft-only scheduling. It is not evidence of merchant usability or revenue lift.

The deterministic lane uses eight synthetic OpenSearch documents rather than Magento products. The verified opt-in Mage-OS catalog contains 1,200 Magento product entities, 816 storefront-indexed documents, and 100 product-derived query terms. Run `dev/ci/run-large-catalog.sh` as documented in [Test catalogs](docs/TEST-CATALOGS.md).

Licensed Hyvä qualification is opt-in and credential-free in this repository. See [dev/ci/README.md](dev/ci/README.md) for the exact environment contract. The verified Mage-OS 3.4.0 and Hyvä 1.5.2 lane activates `Hyva/default` and produces the same storefront baseline digest as Luma.

## License

The package declares OSL-3.0 and AFL-3.0. See [LICENSE.txt](LICENSE.txt) and [LICENSE_AFL.txt](LICENSE_AFL.txt).
