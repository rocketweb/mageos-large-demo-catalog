# Human correction pass, 2026-10-02

The October 2 and 3 feedback pass corrected 99 exact jobs from human Redo notes and matching patterns. All 99 passed; its overall catalog counts are historical.

> Earlier workflow or dated evidence. For current scope, see the
> [documentation index](docs/README.md) and [expansion completion](EXPANSION-CHECKPOINT.md).
> Recorded paths, process IDs and remaining boundaries below belong to that scope.

Matt requested that the additional review notes be applied to matching, currently
unapproved images and queued for reprocessing. The pass analyzed 171 Keep and
44 Redo decisions. It activated 99 exact jobs: all 44 Redos plus 55 matching jobs.
No human Keep or previously accepted job was changed by activation.

| Correction | Jobs |
| --- | ---: |
| Empty candle holders with usable wells and flat bases | 24 |
| Narrow Twin bed proportions | 24 |
| Functional under-desk cable trays with mounting flanges | 18 |
| Recolor chair upholstery while preserving wooden frames | 8 |
| Preserve smooth cubby finishes without invented grain | 8 |
| Recolor mirror frames while preserving reflective interiors | 7 |
| Show the specified metal dining-chair frame | 4 |
| Colored decorative vases | 2 |
| Preserve velvet pile when recoloring | 1 |
| Correct the explicitly reviewed Full bed proportions | 1 |
| Compact, stable dining table for two | 1 |
| Elongated dining table for six | 1 |

The queue contains 75 new photographs, 21 source edits and three exact source
reuses. At activation, five source edits were waiting for an accepted source;
the other 91 generation/edit jobs were immediately eligible. The three cubby
images reuse the exact earlier source Matt preferred, as new immutable attempts
awaiting ordinary QA. These are queued corrections, not automatic approvals.

Repeated candle-holder notes request opaque ceramic rather than glass. The
relevant corrected briefs use Ceramic. One mirror note explicitly requests a
black frame in place of Navy. To keep product details consistent with imagery,
33 represented product SKUs have exact material/color patches staged for the
eventual catalog export, including configurable variation reconciliation.
Frozen candidate CSVs remain unchanged. The patches were dry-run against all
107,688 products without duplicate configurable options.

Construction/material corrections use the revised product brief independently
of a flawed source shape. Recolors preserve their source dependency. Every
prompt retains the ban on visible measurements, text, numerals, units, labels,
rulers, diagrams, logos and watermarks. OCR, visual and component QA still apply.

## Evidence and implementation

Paths below are relative to the repository root.

- Immutable preview: `var/catalog-expansion-20260918/feedback-patterns-20261002/preview-v1.json`
- Activation directory: `var/catalog-expansion-20260918/run-v3/feedback-reprocessing/4e2d5bcbd507bdd5/`
- Preview SHA-256: `4e2d5bcbd507bdd5ed5cfc15a15fb2a07581dafb4a0f87a2e3d519f3f72864fc`
- Activation directory contains the copied manifest, `ledger-before.sqlite`,
  `rollback-before.json`, `activation.json`, `verification.json` and `restart.json`.
- Full test log: `var/catalog-expansion-20260918/feedback-patterns-20261002/tests.log`

`feedback_reprocessing.py` records immutable, exact-job admissions in the
ledger. `bulk_expansion_images.generation_input()` uses them for both Studio
and remote workers. Each generated or edited correction gets at most two new
attempts. Existing attempt counters and files are retained. Reapplying the
same admission cannot reset the retry budget. The exporter applies the staged
product patches only when the catalog passes its existing export gates.

Activation verification compared every job with the backup: exactly 99 changed,
all 46,976 accepted jobs and all 171 human Keeps were unchanged. All original
selected image hashes were preserved. All 99 prompts passed the actual model
tokenizer budget and image policy validation. The complete unit suite ran 645
tests successfully, with six skipped. The existing Studio, mini and laptop
workers were restarted; both remote workers produced fresh correction images.

## Scoped rollback

Stop and drain all three workers before rollback. The command below restores
only untouched pending jobs whose baseline attempt, image and revised request
still match. It preserves any correction that has started or advanced and every
image file. Do not replace the live ledger with the backup after work resumes.

```sh
/Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/feedback_reprocessing.py rollback-unstarted \
  --run var/catalog-expansion-20260918/run-v3 \
  --manifest var/catalog-expansion-20260918/feedback-patterns-20261002/preview-v1.json
```

Subsequent feedback passes need a new reviewed preview and explicitly reconciled
admissions. An existing job admission cannot be silently replaced or given an
unlimited retry allowance. New notes do not mutate an in-flight batch.

## Completion of the remaining six, 2026-10-03

After the first pass, 93 jobs were accepted, three Twin beds were still rejected
and three Engineered Wood chair variants lacked an accepted source. Matt
explicitly authorized repairing these six remaining jobs.

`execute_image_corrections.py` generated one new chair-source repair with visible
engineered-wood construction and three targeted bed edits. The chair source and
two bed edits passed ordinary QA. The mini then generated the three chair color
variants from the approved source. The remaining Ketcham bed needed a fresh,
narrow single-bed composition after width editing retained its broad silhouette.
That image and all three chair variants passed ordinary QA as well.

All **99 correction jobs are now accepted**. Overall image acceptance is
**47,075 / 48,844**; other catalog holds still prevent completion. No export or
deployment occurred. No QA policy or model was changed for this pass.

The exact prompts, seeds, generation/QA logs, backup, final image hashes and
direct visual observations are retained in
`var/catalog-expansion-20260918/focused-corrections-20261003/`. Its
`verification.json` confirms exactly six changed job records, unchanged baseline
source bytes, and preservation of all 47,069 previously accepted jobs and the
293 human Keeps present at verification. `RESULTS.md` describes the outcomes.
