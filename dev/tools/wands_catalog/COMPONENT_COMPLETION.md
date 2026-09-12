# Complete the component candidate coverage

This fixed selection covers the 24 unattempted types and the one uncertain table
lamp from `component-readiness-v1`. Existing passed component candidates remain
untouched. The 25 attempts are split into five batches: lamps (1), flatware (8),
bakeware (8), nursery (3), and outdoor furniture (5). Each component gets one
attempt, without automatic retries or original-image replacement.

The table lamp preserves its earlier exact prompt and seed, changing only the
canvas to 832 by 704. Other component-specific appearance instructions are
explicitly synthetic visual choices, not recovered manufacturer specifications.
They preserve the corrected product identity, roles, quantities and dimensions.
The twelve-well muffin pan is a visual design choice, not twelve sale units.
All nursery components are shown separately, with no infant, mattress or crib.

Every new candidate needs direct visual review. An individual pass does not
establish material consistency across the family, physical fit, mask quality,
complete-set geometry or publication readiness. The furniture views are top
views for the planned layout, not ordinary three-quarter hero photographs.

## Quiet run and resume

Run from `/Users/matt/code/rocket-search/.worktrees/wands-merchandising`:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  /Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/component_completion.py \
  --layouts var/wands/component-layouts-v2 \
  --readiness var/wands/component-readiness-v1 \
  --selection dev/tools/wands_catalog/component_completion_selection.json \
  --selection-sha256 ba8e1a6b2d0c0a6938cf19f7614f1a17aaaf77440193150c3eed2a86db046c35 \
  --batch lamps \
  --output-dir var/wands/completion-lamps-v1

tail -f var/wands/completion-lamps-v1.log
```

The default preflights without model loading. Add `--run` for the authorized
batch. Use the matching batch and output directory for each subsequent pass.
The generator runs the cached FLUX.2 Klein 4B model, four-bit, four steps,
guidance 1.0, with bounded component-specific canvases. No hosted service or
download is used. `--json` explicitly opts into terminal output.

Completed images are hash-verified and skipped. Started but interrupted or
failed attempts are consumed and stop resume. Changed inputs, code, metadata,
runtime or images stop the batch. Frozen earlier runners remain unchanged.

## CPU-only review

Use the same arguments with `python3`, omit `--run`, and add the matching
`--observations` JSON file and a fresh `--review-dir`. Observation files bind
image and execution-case hashes to six visual checks and approximate subject
bounds. The report retains actual prompts, seeds and the synthetic disclosure.

## Cutout boundary

The inspected local image environment has no cached segmentation weights,
`rembg` or `onnxruntime`. No packages or weights were downloaded. A background
removal model must be set up and tested before mask execution. White backgrounds
and contrast-envelope diagnostics are not usable alpha masks; bright metal,
thin stems and fork tines require particular care. Until then, no component is
mask-ready and no complete assortment is assembly-ready.
# Review entry point

Use `completion_review.py` for review, with the same layout, readiness,
selection, batch and output arguments, plus `--observations` and `--review-dir`.
The generation runner remains frozen because its hash is part of recorded runs.
Its original review mode reused a paired-experiment reviewer and raised
`KeyError: 'arm'` on nonpaired completion cases. The separate reviewer accepts
the original cases and hashes without inventing an experiment arm or changing
any generated metadata. The regression test reproduces that failure first.
