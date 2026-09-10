# Equal-area component framing experiment

This follows the single-component pilot, committed as `df52e2b`. The floor lamp
and cake server were recognizable but too wide against their explicitly
synthetic design envelopes. The next experiment tests canvas framing, not a
different model, altered product dimensions, or a revised description.

## Fixed scope

Exactly four local generation attempts, in this order:

| Component | Control | Treatment |
| --- | --- | --- |
| Skiatook floor lamp | 768 by 768 | 384 by 1536 |
| Skaneateles cake server | 768 by 768 | 384 by 1536 |

Each arm has 589,824 pixels. Both arms preserve the earlier exact prompt and
seed, cached FLUX.2 Klein 4B snapshot, 4-bit quantization, four steps, guidance
1.0 and WebP encoding. A seed identifies the random stream, not an identical
spatial noise tensor across differently shaped canvases. This two-product,
one-seed-per-product screen cannot establish a general model improvement.

The original square images are retained. New square controls test repeatability
under the current runtime. No references, image edits, cropping, stretching,
masks, composites, hosted calls, model downloads or catalog writes are involved.

## Quiet preflight and execution

From `/Users/matt/code/rocket-search/.worktrees/wands-merchandising`:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  /Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/run_catalog_framing_pilot.py \
  --source-review var/wands/component-image-review-v1 \
  --approved-source-sha256 9aa7a90f2ea2539aef72553e8bc920e7c114b562067de0860e676af615d7a877 \
  --output-dir var/wands/framing-pilot-v1

tail -f var/wands/framing-pilot-v1.log
```

The default only preflights. Add `--run` to execute the authorized fixed four
trials. `--json` opts into a terminal summary. All other runtime output goes to
the sibling log. The approval fingerprint binds the source bytes; it is not
independent permission to run a model.

Completed trials are verified and skipped. Each started trial consumes its one
attempt; interruption or failure stops resume instead of silently retrying.
Untracked files, changed source bytes, changed code, a different runtime or
changed candidate metadata stop the run. Keep the runner version used by a
frozen run. Candidate media and generated reports remain in ignored `var/`.

## Evaluation

Inspect all four images for complete objects, coherent construction, proportions,
edge clipping and extra objects/text. Compare each square control with its
historical image. Record findings against exact image and execution-case hashes.
Pixel-envelope measurements, if used, are diagnostics only: shadows and bright
metal can bias them. They are not segmentation masks or manufacturer dimensions.

Even a visually improved portrait candidate is not a finished assortment or an
approved storefront image. Full-set scale, matching materials, masking and final
composition must be evaluated independently. No publication approval follows
from this experiment.
