# Bounded corrected-hero repair pilot

The complete media-triage checkpoint is `d92d8de`. The next stage is a local,
non-executable proposal, not a model run or image approval.

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
`reference_images` fields and are not directly runnable queues. The next
authorized generation step must add a bounded, hash-bound runner and verify the
current local model/runtime before use. Merely setting an `executable` flag
would not enforce this boundary in the historical generator.

The exploratory `media-repair-plan-v1` packet is historical; use `v2` for the
current producer. Catalog media and generated packets remain outside Git. The
tracked JSON files contain observations, hashes and pilot choices, not images.
