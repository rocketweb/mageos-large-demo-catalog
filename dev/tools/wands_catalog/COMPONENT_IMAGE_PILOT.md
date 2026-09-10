# Local single-component image pilot

The component-layout planner is committed as `c9dd1b5`. The next bounded
development run generated four component candidates on 2026-09-10, using the
existing local FLUX.2 Klein 4B runtime: 4-bit, 768 by 768, four steps.

There was one attempt per selected component, no retries, no reference images,
no downloads, no hosted calls, no oMLX calls, no original-image replacement and
no Magento writes. No credentials were needed. The four candidates are opaque
RGB WebP files, not transparent cutouts.

## Scope and outcome

The exact selection is in `media_component_pilot_selection.json`, fingerprint:

`39e5662baec6b4d3c9655e167cf0004f34f7e2a59fe2a8ba890f3f6dc953879f`

It selects the floor lamp and table lamp from Skiatook, plus the dinner fork
and cake server from Skaneateles. The runner generates one image per component
type, not one image per planned repeated instance. The other 24 component types
remain unattempted.

| Component | Single complete object | Initial visual result | Remaining issue |
| --- | --- | --- | --- |
| Floor lamp | Pass | Fail | Silhouette too wide for the synthetic envelope |
| Table lamp | Pass | Uncertain | Proportion alignment needs closer review |
| Dinner fork | Pass | Pass | Mask and full-set consistency remain untested |
| Cake server | Pass | Fail | Blade too wide for the synthetic envelope |

All four candidates have recognizable, coherent single-object construction and
no visible extra pieces or text. This does not establish a catalog-wide success
rate or an equal-condition model comparison. Generating one component is a
different task from the earlier whole-assortment attempt.

The geometry observations include approximate hand-estimated subject bounds.
Their height/width ratios diagnose image-to-design drift, not real-world
measurements, accurate masks or a new automatic acceptance threshold. The full
catalog dimensions were not changed to accommodate the generated images.

Current local artifacts:

- `var/wands/component-image-pilot-v1/`: four images, metadata, actual prompts,
  seeds, runtime versions and an append-only attempt ledger.
- `var/wands/component-image-review-v1/review.html`: component candidates beside
  the earlier whole-set attempts, with findings, prompts and fingerprints.
- `media_component_pilot_observations.json`: tracked, hash-bound visual findings.
  The actual catalog media remains outside Git.

The existing whole-product review remains three passes, two uncertainties and
seven failures. This component pilot does not approve or repair either whole
assortment yet. Zero masks and zero composites have been produced.

## Quiet preflight and resume

Run from the tooling worktree. The following command only verifies the existing
run and reports zero pending components to its sibling log:

```sh
cd /Users/matt/code/rocket-search/.worktrees/wands-merchandising

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  /Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/run_catalog_component_pilot.py \
  --layouts var/wands/component-layouts-v2 \
  --selection dev/tools/wands_catalog/media_component_pilot_selection.json \
  --approved-selection-sha256 39e5662baec6b4d3c9655e167cf0004f34f7e2a59fe2a8ba890f3f6dc953879f \
  --output-dir var/wands/component-image-pilot-v1

tail -f var/wands/component-image-pilot-v1.log
```

For an authorized, exact selection, `--run` enables generation. There is a hard
limit of four selected assets and one attempt per asset. The selected-file hash
binds the inputs; supplying a hash is not a substitute for human authorization.

Completed candidates are hash-checked and skipped. Failed or interrupted
attempts are consumed, not automatically retried. Changed inputs, runtime,
runner code, prompts, candidates or metadata stop resume. Preserve the runner
version used by a frozen run. The old whole-product runner and its historical
packets are unchanged.

The installed text encoder has a 512-token limit. All four actual prompts fit
at 162 to 169 tokens. The new compiler keeps family quantities, parent set names,
legacy SKU tokens and repeat-placement instructions out of the model prompt.
It passes one selected component, visible appearance, viewpoint and a
dimensionless proportion guide. Full definitions and construction requirements
remain in metadata.

Output, progress bars, warnings and errors go to the sibling log by default.
`--json` explicitly opts into a terminal summary.

## Rebuild the review without a model

```sh
python3 dev/tools/wands_catalog/review_catalog_component_pilot.py \
  --layouts var/wands/component-layouts-v2 \
  --selection dev/tools/wands_catalog/media_component_pilot_selection.json \
  --run-dir var/wands/component-image-pilot-v1 \
  --observations dev/tools/wands_catalog/media_component_pilot_observations.json \
  --output-dir var/wands/component-image-review-next

tail -f var/wands/component-image-review-next.log
```

Use a fresh output directory. The builder verifies pinned layout/definition
inputs, reconstructs execution cases, verifies the attempt ledger, decodes each
image and checks the original metadata. Observations must cover the exact assets
and match image, brief and actual-prompt hashes. Visual verdicts cannot grant
mask, assembly, conditioning or publication approval.

## Next development step

The object-count and missing-assembly problems improved in this small sample.
Proportion control is the next bottleneck. A separately scoped follow-up should
test silhouette or framing control on the failed components before any bulk
generation. Do not stretch width and height independently or quietly rewrite
the catalog dimensions to fit a candidate.

Only after component geometry is acceptable should masking and composition be
tested. A white background is not transparency, a diagnostic bounding box is
not a mask, and one passed component does not validate a complete product set.
No masking, image editing, composition, retries, further generation or
publication is authorized by this document.

## Verification record

The Python suite passes all 306 tests. A fresh CPU-only resume verifies the four
completed candidates and reports zero pending work. The run ledger contains
four starts and four successful generation records, with no retries.

The review verifies 500 pinned inputs and two output fingerprints. All three
review files, including the manifest, are byte-identical to a fresh rebuild.
Desktop (1920 by 1080) and mobile (390 by 844) browser checks decode all eight
comparison images, with no horizontal overflow or reported browser errors.
All five captured command-output logs are empty; details remain in sibling logs.
