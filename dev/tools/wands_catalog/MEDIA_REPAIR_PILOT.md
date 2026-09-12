# Bounded corrected-hero repair pilot

The complete media-triage checkpoint is `d92d8de`; the bounded proposal is
committed as `6690e6d`. The proposal remains immutable and non-executable.
A separately authorized local run is complete, with results below. No image
publication or bulk expansion is approved.

## Focused review outcome

All 12 uncertain references now have a byte- and definition-bound proposed next
action. The original `media-reconciliation-v4` packet remains unchanged:

- Retain four plausible furniture candidates: Mirefield (`WANDS-004880`),
  Cornell (`WANDS-015548`), Paralimni (`WANDS-027653`) and Colrain (`WANDS-039471`).
  Exact physical size cannot be established from a photo and is not, by itself,
  grounds for regeneration. Synthetic dimensions remain metadata.
- Prepare clearer views for eight references: Ocean Baby (`WANDS-000056`), Pink
  Chocolate (`WANDS-003817`), Pineapple fabric (`WANDS-008286`), Blew
  (`WANDS-011019`), Retro Dots (`WANDS-012070`), Hance (`WANDS-019888`), Lewis
  Penguin (`WANDS-030143`) and Dreamit (`WANDS-035175`). Folds conceal sale-unit
  identity or component boundaries. This is a clarity proposal, not proof that
  hidden items are absent.

Together with the 81 confirmed defects, this creates 89 repair/clarification
candidates. Four references are proposed for retention. None is approved for
conditioning, publication or derivative-image generation.

## Proposed pilot

`var/wands/media-repair-plan-v2/plan.md` lists 12 exact roots: ten confirmed
defects and two clarity improvements. The pilot includes nursery textiles,
fabric, curtains, bedding, nightstands, outdoor furniture, mixed-height lamps,
ten-piece bakeware and 45-piece flatware. It is a deliberately selected stress
test, not a representative estimate of catalog-wide quality.

Proposed settings retain the existing local generator's defaults: FLUX.2 Klein
4B, 4-bit quantization, 768 by 768, four steps, one image per root. There are no
automatic retries, derivative views, uploads or imports. A run must stop after
the 12 images; the other 77 repair candidates are deferred. These settings are
an incumbent baseline, not a new model comparison or quality guarantee.

The pilot proposes text-only generation from corrected definitions. Bad or
unclear originals must not become conditioning references. The original images
remain available as evidence and are never overwritten. Every proposed filename
is fingerprinted from its definition, instruction and settings. Changing any of
those creates a different basename.

Every generated candidate would need explicit acceptance against identity,
selected options, exact components, exclusions, geometry, artifacts, safe staging
and synthetic metadata. Pending, failed or uncertain checks cannot be treated as
acceptance. Preserve the actual image hash with its definition fingerprint. A
failed challenge blocks expansion for that challenge; even a fully successful
pilot does not authorize bulk generation or publication.

## Quiet local preparation

```sh
cd /Users/matt/code/rocket-search/.worktrees/wands-merchandising

python3 dev/tools/wands_catalog/plan_catalog_media_repairs.py \
  --review var/wands/media-reconciliation-v4 \
  --decisions dev/tools/wands_catalog/media_reconciliation_focused_decisions.json \
  --pilot-selection dev/tools/wands_catalog/media_repair_pilot_selection.json \
  --output-dir var/wands/media-repair-plan-next

tail -f var/wands/media-repair-plan-next.log
```

Use a fresh directory. Normal output and runtime errors go to its sibling log;
`--json` explicitly opts into a terminal summary. No model, network service or
credentials are used by the planner.

The planner rechecks the source packet's hashes, independently verifies the
definition packet and reconstructs every corrected media contract. Unknown,
duplicate, missing or stale focused decisions are rejected. A retained candidate
cannot enter the pilot. The pilot must contain one to twelve unique known roots.
All inputs are checked again before the output directory is published locally.

Outputs:

- `plan.md`: readable exact pilot and focused-review dispositions.
- `dispositions.proposed.jsonl`: all 93 roots with their proposed next action.
- `pilot.proposed.jsonl`: only the 12 proposed pilot roots and complete contracts.
- `acceptance.pending.jsonl`: 12 blank acceptance records; no prefilled passes.
- `manifest.json`: input/output hashes, exact counts and proposed settings.

These files omit the legacy generator's `prompt`, `output_file` and
`reference_images` fields and are not directly runnable queues. The separately
authorized generation step uses a bounded, hash-bound runner and verifies the
current local model/runtime before use. Merely setting an `executable` flag
would not enforce this boundary in the historical generator.

The exploratory `media-repair-plan-v1` packet is historical; use `v2` for the
current producer. Catalog media and generated packets remain outside Git. The
tracked JSON files contain observations, hashes and pilot choices, not images.

## Completed local pilot

On 2026-09-10, the authorized 12-root run completed in
`var/wands/media-repair-pilot-v1`: 12 images, one attempt each, no retries.
It used the existing `/Users/matt/code/mageos-latest/.venv-imagegen` environment:
mflux 0.19.1, MLX 0.32.2, Pillow 12.3.0, transformers 5.16.1 and
huggingface-hub 1.29.0. The cached FLUX snapshot is recorded in `run.json`.
No hosted service, oMLX endpoint, credential, download, media import or original
image replacement was used.

The installed FLUX text encoder accepts 512 tokens. Seven planning drafts
exceeded that limit when wrapped in its actual chat template. The runner
compiles concise visual instructions from the corrected contracts and rejects
over-budget prompts instead of silently truncating them. All 12 actual prompts
fit at 131 to 306 tokens. Full definitions, nonvisual facts and synthetic
disclosures remain in the metadata. This finding does not establish that
truncation caused every historical catalog-image defect.

Direct visual inspection of the generated bytes found:

| Initial screen | Count | Products |
| --- | ---: | --- |
| Pass | 3 | Pineapple fabric, Black plastic nightstand, Abe five-piece dining set |
| Uncertain | 2 | Short curtain proportions, Remillard drawer construction |
| Fail | 7 | Nursery set, bakeware, three-level bunk, flatware, Merlyn furniture, empty pillowcase, lamps |

These are challenge-selected cases, not a representative quality sample. A
pass means no visible contradiction was found in this initial lab screen,
not manufacturer verification, exact measurement or publication approval.
The failures show that compact prompts alone do not reliably enforce component
counts, excluded items or complex geometry at these settings.

`media_pilot_visual_observations.json` records each check, finding and proposed
next direction, bound to image, definition and actual-prompt hashes. The
CPU-only `review_catalog_media_pilot.py` independently verifies the plan/run,
original bytes, candidate bytes, metadata, exact observation coverage and
completed attempt ledger before producing a before-and-after page. It derives
the verdict from the checks; an input cannot set approval flags. Historical
plan checklists and generated metadata remain pending and unchanged.

Current local review: `var/wands/media-pilot-review-v1/review.html`.
It links originals and new candidates without copying any catalog image.
Generated packets, media and local acceptance screenshots remain outside Git.

## Quiet execution and resume

Run from the tooling worktree, not the Magento root. This command is a
CPU-only preflight of the already completed pilot; it does not load the image
model or generate another image:

```sh
cd /Users/matt/code/rocket-search/.worktrees/wands-merchandising

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  /Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/run_catalog_media_pilot.py \
  --plan var/wands/media-repair-plan-v2 \
  --approved-plan-sha256 b2771512ffede64023bb4c75fe34eb88457118c98e9dab5106e2e2a953b23048 \
  --output-dir var/wands/media-repair-pilot-v1

tail -f var/wands/media-repair-pilot-v1.log
```

For an explicitly authorized pilot, adding `--run` enables generation of only
never-attempted cases. A completed run has zero pending cases and exits without
loading the model. An interrupted or failed attempt is consumed, not retried.
Changed inputs, runtime versions, runner bytes, candidates or metadata stop
resume. Do not edit a frozen runner and expect an old run to resume. Preserve
the original runner commit and create a separately approved new run when needed.

The runner uses an exclusive lock, records each attempt before generation and
publishes candidate files without overwrite. Runtime output, progress bars,
warnings and errors go to the sibling log by default. `--json` is the only
opt-in terminal summary. The full actual prompts, seeds and filenames are in
`execution-cases.jsonl`; candidate names incorporate the compiled prompt, so
they differ from the proposal's draft-only basenames.

Regenerate the review into a fresh directory, without a model:

```sh
python3 dev/tools/wands_catalog/review_catalog_media_pilot.py \
  --plan var/wands/media-repair-plan-v2 \
  --run-dir var/wands/media-repair-pilot-v1 \
  --observations dev/tools/wands_catalog/media_pilot_visual_observations.json \
  --output-dir var/wands/media-pilot-review-next

tail -f var/wands/media-pilot-review-next.log
```

## Next development boundary

Do not expand the one-shot workflow to the remaining 77 candidates or retry the
failed cases automatically. The next proposed experiment is controlled layout
and component assembly for assortments, plus construction-specific geometry for
the bunk, lamps, drawer and textiles. Evaluate exact count and structure before
polishing appearance. This is a proposed approach, not an implemented pipeline
or authority to make additional model calls. Keep the three initial passes
local until their intended image-use scope is explicitly approved.
