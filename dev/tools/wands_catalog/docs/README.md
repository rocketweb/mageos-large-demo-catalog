# Catalog documentation

Start with the guide for your task. Installation and review guides begin with
reader-facing essentials; implementation contracts and recorded evidence follow
below them. Short policies stay short. Historical reports retain their original
claims and commands, with their scope marked at the top.

## Catalog status at a glance

| Scope | What exists | Where to read |
| --- | --- | --- |
| Stable October catalog | Full: 107,815 records, six types, expansion media and 127 QA fixtures | [Install a release](../../../../README.md#quick-start) |
| Completed expansion | 107,688 base records on both existing stores; included in the October release | [Completion](../EXPANSION-CHECKPOINT.md) |
| Test coverage | Both existing stores: 107,815 WANDS records, all six core types and 127 named QA fixtures | [QA suite](../QA-CATALOG.md), [coverage audit](../PRODUCT-COVERAGE.md) |
| Image work | Completed run stopped; feedback and acceptance evidence retained | [Human review](../HUMAN-IMAGE-REVIEW.md) |

Installation acceptance for the expansion was recorded October 6, 2026. This
index describes the documented artifact states, not a live process monitor.

## Pick a reading path

- **Install and try it:** [root quick start](../../../../README.md#quick-start) →
  [recipient installation](../distribution/PRODUCTION_RELEASE.md) →
  [current acceptance and limits](../distribution/PRODUCTION_RELEASE.md#acceptance-and-practical-limits).
- **Plan test coverage:** [product audit](../PRODUCT-COVERAGE.md) →
  [QA fixture guide](../QA-CATALOG.md) → [expansion scope](EXPANSION.md#verification-and-remaining-coverage).
- **Review images:** [review guide](../HUMAN-IMAGE-REVIEW.md) →
  [feedback correction record](../FEEDBACK-REPROCESSING.md).
- **Change or operate the tooling:** [source map](../README.md#developer-map) →
  [expansion contracts](EXPANSION.md) → [contribution checks](../../../../CONTRIBUTING.md).
- **Prepare a release:** [build recipes](../distribution/BUILDING.md) →
  [sharing checklist](../../../../SHARING.md) → [license scope](../../../../NOTICE.md).

## How to read status and evidence

A data candidate is not an accepted export. An accepted export is not an installed
store. A source push is not a media release. A browser or cart-model check is
not checkout/payment or search-ranking qualification. Read each report against
its exact profile, manifest, destination and date.

Paths under `var/` refer to ignored private artifacts in the original workspace.
They are evidence pointers, not broken download links. Historical workers, SSH
addresses, PIDs, approval scopes and timers must be refreshed before operation.
The source checkout does not include model weights or product media.

## Detailed reference index

The tables below cover the catalog's guides and reports. The separate
[Workbench snapshot](../../../../packages/WORKBENCH_SOURCE.md) has its own
upstream documentation. GitHub issue and pull-request templates remain short
submission forms rather than technical guides.

### Current catalog and contribution guides

| Document | Purpose and scope |
| --- | --- |
| [Current stable release](../distribution/PRODUCTION_RELEASE.md) | October package, installation, acceptance and limits |
| [WANDS catalog tooling](../README.md) | Tooling entry point and source map |
| [Catalog expansion completion](../EXPANSION-CHECKPOINT.md) | Completed two-store installation and acceptance limits |
| [The doubled catalog](EXPANSION.md) | Expansion architecture, artifact contracts and recovery |
| [Product coverage audit](../PRODUCT-COVERAGE.md) | Existing store types and remaining behavioral coverage |
| [QA product suite](../QA-CATALOG.md) | 127 installed fixtures, six types, expected outcomes and verification |
| [Contributing](../../../../CONTRIBUTING.md) | Development checks and documentation conventions |
| [Sharing the catalog](../../../../SHARING.md) | Sharing and new-release checklist |
| [Security reports](../../../../SECURITY.md) | Private vulnerability reporting |
| [Licenses and attribution](../../../../NOTICE.md) | License scope and WANDS citation |

### Image review and worker operation

| Document | Purpose and scope |
| --- | --- |
| [Human image review](../HUMAN-IMAGE-REVIEW.md) | Keep/Redo workflow, keyboard controls and feedback storage |
| [Mac mini image worker](../MINI-WORKER.md) | Apple Silicon worker operation and dated setup evidence |
| [Linux laptop image worker](../LAPTOP-WORKER.md) | CUDA worker operation and dated setup evidence |
| [Human correction pass, 2026-10-02](../FEEDBACK-REPROCESSING.md) | October 2 and 3 correction patterns, exact scope and rollback |
| [Source recolor recovery, October 1, 2026](../PROMPT-RECOVERY.md) | October 1 recolor correction and finite admission |

### Published profiles and release tools

| Document | Purpose and scope |
| --- | --- |
| [WANDS catalog for Mage-OS Lab](../distribution/README.md) | Empty-store recipient installation |
| [GitHub release assets](../distribution/GITHUB_RELEASE.md) | Pinned GitHub assets and anonymous download |
| [Downloading a pinned catalog](../distribution/DOWNLOADS.md) | Direct HTTPS mirror tool and verification |
| [Building a catalog release candidate](../distribution/BUILDING.md) | Pinned candidate recipes and rc2 handoff builder |
| [Optional detail and room galleries](../distribution/GALLERIES.md) | Optional 14-image addition for the enriched full profile |
| [Dataset card](../distribution/DATA_CARD.md) | Source corpus, synthetic fields and reproducibility |
| [Distribution terms](../distribution/TERMS.md) | Distribution terms and excluded third-party packages |

### Release-specific acceptance evidence

| Document | Purpose and scope |
| --- | --- |
| [Public-download recipient acceptance](../distribution/PUBLIC_RECIPIENT_ACCEPTANCE.md) | September 13 anonymous download and fresh recipient installation |
| [Enriched catalog acceptance](../distribution/ENRICHED_ACCEPTANCE.md) | Enriched medium/full artifact pins and isolated runtime results |
| [Existing demo enrichment acceptance](../distribution/DEMO_ENRICHED_ACCEPTANCE.md) | September 13 existing-demo update acceptance |
| [Enriched v2 public release audit](../distribution/PUBLIC_RELEASE_AUDIT.md) | September 13 source, asset and repository-settings audit |
| [Mage-OS compatibility evidence](../distribution/ACCEPTANCE.md) | Earlier rc2 starter/full Mage-OS acceptance |
| [Mage-OS 3.5 with Hyvä: storefront verification](../distribution/HYVA_ACCEPTANCE.md) | Hyvä on the populated rc2 full-profile fixture |
| [Mage-OS 3.5 acceptance result](../LAB35_ACCEPTANCE.md) | Earlier rc2 installation result |
| [README screenshot sources](screenshots/README.md) | Exact capture environment and storefront states |

### Historical expansion and distribution records

| Document | Purpose and scope |
| --- | --- |
| [Expansion history, September to October 2026](EXPANSION-HISTORY.md) | Full September/October expansion and recovery chronology |
| [Earlier tooling workflows and progress notes](LEGACY-WORKFLOW.md) | Original base, image and merchandising recipes and progress notes |
| [GitHub catalog release assets](../GITHUB_RELEASE_PUBLISHED.md) | September 12 rc2 publication receipt and original private access state |
| [Mage-OS Lab private release candidate](../LAB_RELEASE_CANDIDATE.md) | Earlier private candidate scope |
| [Mage-OS Lab offline handoff](../LAB_HANDOFF_READY.md) | Earlier offline rc2 handoff |
| [Sharing the catalog with Mage-OS Lab](../COMMUNITY_DISTRIBUTION.md) | Portable-package design before publication |
| [Catalog publication preparation](../DEPLOYMENT_READINESS.md) | Earlier artifact validation and phased deployment planning |
| [Private Mage-OS 3.5 acceptance instance](../distribution/acceptance/README.md) | Private release-acceptance fixture operation |
| [Enriched catalog acceptance: approved remote scope](../distribution/acceptance/ENRICHED_ACCEPTANCE_PLAN.md) | September 13 isolated enriched-acceptance scope |
| [Existing demo enrichment update](../distribution/acceptance/DEMO_UPDATE.md) | Earlier existing-demo update and stock-side-effect recovery |

### Earlier data and realism workflows

| Document | Purpose and scope |
| --- | --- |
| [Catalog realism review](../REALISM_REVIEW.md) | Review-only realism proposal |
| [Full-catalog realism workflow](../FULL_REALISM.md) | Earlier full-profile data recipe |
| [Catalog depth pilot](../CATALOG_DEPTH.md) | Specification and gallery-depth pilot |
| [Catalog corrections and guarded expansion](../CATALOG_REPAIRS.md) | Corrected definitions and guarded proposals |
| [Remaining product-definition resolutions](../DEFINITION_RESOLUTIONS.md) | Source-supported and explicitly synthetic conflict resolutions |
| [Definition migration checkpoint, 2026-09-11](../DEFINITION_MIGRATION_CHECKPOINT.md) | Definition migration rehearsal and inverse receipts |
| [Pilot definition update scope](../PILOT_DEFINITION_UPDATE_SCOPE.md) | September 11 proposed update boundary |
| [Bulk test-catalog completion](../BULK_COMPLETION.md) | Earlier 667-SKU media update |
| [Bulk catalog enrichment](../BULK_ENRICHMENT.md) | Specifications, merchandising and gallery enrichment |

### Component, framing and media experiments

| Document | Purpose and scope |
| --- | --- |
| [Corrected-definition media reconciliation](../MEDIA_RECONCILIATION.md) | Visual triage against corrected definitions |
| [Bounded corrected-hero repair pilot](../MEDIA_REPAIR_PILOT.md) | Bounded corrected-hero experiment |
| [Count-controlled component layout planning](../COMPONENT_LAYOUTS.md) | Exact piece-count layout planning |
| [Local single-component image pilot](../COMPONENT_IMAGE_PILOT.md) | Four single-component candidates |
| [Equal-area component framing experiment](../FRAMING_PILOT.md) | Equal-area framing comparison |
| [Bounded product-specific framing refinement](../FRAMING_REFINEMENT.md) | Bounded silhouette-driven follow-up |
| [Component readiness after the framing passes](../COMPONENT_READINESS.md) | Dated inventory across 28 planned types |
| [Complete the component candidate coverage](../COMPONENT_COMPLETION.md) | Pilot generation and resume procedure |
| [Component completion checkpoint, 2026-09-10](../COMPONENT_COMPLETION_RESULTS.md) | September 10 generation results |
| [Component cutout handoff](../COMPONENT_CUTOUTS.md) | Cutout asset and mask contract |
| [Repair and cutout checkpoint, 2026-09-10](../REPAIR_AND_CUTOUT_CHECKPOINT.md) | Partial repair and segmentation results |
| [Built-in component repair checkpoint, 2026-09-11](../BUILTIN_COMPONENT_CHECKPOINT.md) | Built-in component repairs |
| [Nursery completion checkpoint, 2026-09-11](../NURSERY_COMPLETION_CHECKPOINT.md) | Nursery and five-assortment local completion |
| [Repaired references and gated bulk generation](../REFERENCE_BULK.md) | Earlier immutable reference-based queue |
| [Selected reference repairs](../assets/reference-repairs-v2/README.md) | Selected repair-image provenance, without Git media |

### Native Magento and storefront rehearsals

| Document | Purpose and scope |
| --- | --- |
| [MariaDB rehearsal checkpoint, 2026-09-11](../MARIADB_REHEARSAL_CHECKPOINT.md) | Captured-schema database and rollback rehearsal |
| [Mage-OS model rehearsal checkpoint, 2026-09-11](../MAGEOS_MODEL_REHEARSAL_CHECKPOINT.md) | Native model acceptance for the isolated pilot |
| [Inventory lifecycle checkpoint, 2026-09-11](../INVENTORY_LIFECYCLE_CHECKPOINT.md) | Stock indexing and recovery |
| [Guest price-index lifecycle checkpoint, 2026-09-11](../PRICING_LIFECYCLE_CHECKPOINT.md) | Native price indexing and rollback |
| [Unsaved guest-cart checkpoint, 2026-09-11](../CART_MODEL_CHECKPOINT.md) | Unsaved cart-model scenarios |
| [Native Hyva options checkpoint, 2026-09-11](../HYVA_OPTIONS_CHECKPOINT.md) | Initial option display/runtime checks |
| [Ordered configurable options checkpoint, 2026-09-11](../ORDERED_OPTIONS_CHECKPOINT.md) | Corrected option labels and ordering |
| [Native Hyva browser component checkpoint, 2026-09-11](../BROWSER_COMPONENT_CHECKPOINT.md) | Pilot desktop/mobile interaction checks |
| [Approved remote theme capture, 2026-09-11](../REMOTE_THEME_CAPTURE_CHECKPOINT.md) | Read-only theme and schema capture |
| [Native media rehearsal stage, 2026-09-11](../NATIVE_MEDIA_STAGE_CHECKPOINT.md) | Five-JPEG native-import staging packet |
| [Storefront media checkpoint, 2026-09-11](../STOREFRONT_MEDIA_CHECKPOINT.md) | Earlier storefront media scope and destination drift |
