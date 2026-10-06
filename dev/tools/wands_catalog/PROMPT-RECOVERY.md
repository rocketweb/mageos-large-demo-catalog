# Source recolor recovery, October 1, 2026

The shared variant prompt previously instructed every product to retain fabric,
chains and rings. Failed variants showed those invented components on tables,
desks, mugs and bowls. It also forced opaque paint on natural finishes and changed
white variants to a gray background. Retrying the same recipe exhausted the
three-attempt budget without addressing the cause.

`source_recolor_prompt()` now edits the clean accepted source, preserving its
existing parts, texture, background and lighting. It does not describe the source
as a defective candidate. Explicitly upholstered furniture changes only its
upholstery; visible frames and feet retain their original colors and materials.
Studio and both remote coordinators use the same central prompt planner. Remote
model code, package pins, quantization, resolution and inference steps are unchanged.

Retained-source review, repair and repair review now prioritize sources that block
pending or held products. The complete retained-media audit remains required.

## Evidence

Artifacts are in `var/catalog-expansion-20260918/prompt-recovery-20261001/`:

- `index.html`: source, old prompt, revised Studio and revised laptop comparison.
- `comparison-mlx-v2/` and `comparison-cuda-v2/`: frozen prompts, source bytes,
  seeds, results and unchanged OCR/vision review evidence for eight paired cases.
- `direct-comparison-review.json`: direct observations bound to output hashes.
- `admission-benchmark.json`: exact code and artifact pins admitting this recipe.
- `mini-parity.json`: both mini checks match Studio output bytes exactly.
- `tests.log`: 621 tests completed, 615 passed and six skipped.
- `ledger-before.sqlite`: consistent pre-recovery ledger backup. Do not restore
  it over later progress.

The old prompt passed one of 16 comparisons across the two renderers. The revised
prompt passed 14 of 16 after direct review. Both remaining images reproduced a
solid-back bookcase source where the design requires an open back. That source
job, `e87978d573166c7c726b60744c1f40f7b302b102049885e9e748ba4269efdd5c`,
was held with a concrete correction. Its dependent variants cannot use it until
the replacement passes review. This diagnostic sample is not a catalog-wide
acceptance-rate forecast.

The first two live recovery batches preserved their previous attempts and returned
eight new attempt-4 images. Seven passed ordinary QA and direct inspection; one
outdoor seating set remained rejected. Evidence is in
`live-recovery-validation.json` and `smoke-direct-review.json`.

The continuous Studio, mini and laptop workers resumed at 2026-10-01 10:26 UTC.
Actual processes and fresh batch states were verified. At that checkpoint, 42,901
of 48,844 new images were accepted. These are historical checkpoint counts;
consult the live ledger and process state for later progress. The first prioritized
64-source review batch covers 320 waiting products, versus five in the previous
ordering; source rejection can still prevent those products from proceeding.

## Finite recovery admission

`source_prompt_recovery.py` prepares a preview. Activating the reviewed preview as
`run-v3/source-recolor-recovery.json` enables **2,915 specifically listed exhausted
variants**, with at most **two additional attempts each**. This file does not
change job state or grant acceptance.

Each entry binds the original failed attempt, metadata, request, accepted source
and revised prompt by hash. Missing or changed history fails closed. An unrelated
later correction cannot inherit the allowance. The immutable benchmark and run
identity are rechecked, including after an earlier successful cached read.
Accepted images, unlisted jobs and standalone retries receive no new allowance.
Attempts keep increasing; prior files and rejection evidence remain intact.

All returned images enter the ordinary generated queue. OCR, vision, component
checks and manual holds remain mandatory. No measurements, text, numerals,
dimension marks, logos or watermarks are permitted in generated catalog images.

To stop or roll back this recovery, request safe stops with `STOP`, `REMOTE_STOP`
and `REMOTE_STOP-laptop`, verify all processes and reservations, and drain/import
any completed batch under the current prompt first. Then archive the admission
file outside its active name. Do not reset attempts, remove prior candidates,
restore the old ledger, or change the planner while a remote manifest is active.
An active reservation must finish or be explicitly cancelled with the existing
validated cancellation tool before changing its inputs.

The expanded catalog still requires the remaining new-image and retained-image
quality work before export and installation. This recovery does not deploy a
catalog or create another installation.
