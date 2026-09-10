# Repair and cutout checkpoint, 2026-09-10

This is partial progress, not completion of all 18 component repairs.

## Current result

- Eighteen new repair candidates were generated and directly reviewed. Only
  the table lamp gained an initial visual pass. The crib valance and cooling
  rack improved from failed to uncertain; other wrong results remain excluded.
- The 28-type inventory now contains 11 initial passes, six uncertain types
  and 11 failed types. Seventeen types still need a successful repair.
- Eleven selected components have candidate-specific cutout visual passes.
  Ten used the direct segmentation mask; the serving spoon required a targeted
  alpha-only correction after the model erased a bright handle reflection.
- One complete assortment, the three-lamp set, has an initial local assembly
  visual pass. Four assortments remain blocked: nursery has two unresolved
  types, bakeware six, flatware five, and outdoor four.

Review pages, all local and ignored by Git:

- `var/wands/component-repair-review-v1/review.html`: current 28-type inventory.
- `var/wands/component-repair-review-v1/repairs.html`: the 18 actual repair
  images, findings, prompts and seeds, including failed candidates.
- `var/wands/cutout-pilot-v1/review.html`: initial three-mask comparison.
- `var/wands/cutout-remaining-v1/review.html`: eight raw cutout comparisons.
  Its serving-spoon card deliberately retains the failed raw mask; the selected
  corrected result is `var/wands/cutout-solid-repair-v2/serving-spoon.png`.
- `var/wands/assortment-preview-v1/review.html`: lamp assembly and explicit
  blockers for the other four families. `assortment_visual_observations.json`
  binds the lamp visual review to the exact assortment data and screenshot.

## Local generation and interruption

The repaired prompts remove the shared instruction to make every object upright,
which conflicted with wide overhead products. They also distinguish a bedding
valance from a wearable skirt and state prong/well counts directly. This did not
solve FLUX Klein 4B's construction failures: merged muffin wells, an open tray
instead of a lid, phantom fork prongs, and incorrect camera views remain.

The main process exited 137 after saving 15 candidates, with no explanatory
Python traceback. The sofa attempt had started; table and lamp were unattempted.
No cause was confirmed. Three isolated one-image recovery processes completed
those products. The first run, its partial ledger and every saved image remain
unchanged. `run-states.json` retains the interrupted and unattempted states;
it never converts an interrupted attempt into a successful one.

Use the four run directories as inputs to `review_component_repairs.py`, with
the v2 readiness baseline, v2 layouts and `component_repair_observations.json`.
Use a fresh review output directory. Do not restart the interrupted run or edit
its ledger. The runner's strict no-repeat checks intentionally reject that.

## Segmentation and alpha repair

Runtime is isolated in ignored `var/wands/.venv-cutouts`, leaving the existing
FLUX environment unchanged. Installed versions: rembg 2.0.84, ONNX Runtime
1.30.0, Pillow 12.3.0. CPU inference uses four intra-op threads and one inter-op
thread. The model is BiRefNet general, downloaded from rembg's official release;
weights SHA256:

`58f621f00f5d756097615970a88a791584600dcf7c45b18a0a6267535a1ebd3c`

Weights remain outside Git in `var/wands/cutout-models`. The generation wrapper
uses only the specified existing weights. It attaches predicted alpha to a copy
of the original decoded RGB without recoloring, resizing or overwriting sources.
See the [rembg project](https://github.com/danielgatis/rembg) and its
[BiRefNet adapter](https://github.com/danielgatis/rembg/blob/main/rembg/sessions/birefnet_general.py)
for the upstream implementation. No claim of catalog-wide segmentation quality
or redistribution licensing approval is made by this experiment.

Every raw cutout passed the structural validator, yet direct review caught the
serving-spoon handle hole. This demonstrates why a contract pass is insufficient.
The first solid-mask repair required fully opaque boundaries and changed zero
pixels. A regression test reproduced the soft-alpha leak. The second repair
uses alpha confidence 128 to identify enclosed gaps for this explicitly solid
product only, changing 27,336 alpha pixels while preserving RGB and the exterior
edge. It was rechecked on white, dark and pink. Do not apply this operation to
objects with real holes or openings.

## Assortment acceptance limits

The lamp preview contains exactly one floor lamp and two table lamps. It reuses
the table-lamp asset twice; that is two physical instances, not two independently
generated images. Both component images are uniformly fit into validated slots
and baseline-aligned. Actual displayed heights are 91.63 and 90.86 percent of
their nominal synthetic slot heights. No independent-axis stretching occurs.
The result is a coordinated bronze set, not identical base designs or exact CAD.

The table-lamp repair prompt included proportionally equivalent 60.5/35 cm
values instead of the definition's actual 52/30 cm values. This is retained in
the original prompt evidence, not rewritten. The preview uses the unchanged
corrected definition and layout. Generated imagery does not establish physical
dimensions or manufacturer facts.

The assortment packet reproduces byte for byte. Desktop 1920x1080 and mobile
390x844 checks found exactly three rendered instances, no horizontal overflow
and no reported browser errors. Screenshots were directly inspected. The full
Python suite passes 352 tests, including the soft-alpha regression.

## Remaining decision and boundary

The existing local model still fails the 17 remaining components. A question
was sent asking whether built-in generation may be used for stubborn cases;
no switch is authorized by this checkpoint. Do not weaken count, identity or
camera checks to promote the failures. Local cutouts and count-controlled
assembly can be reused with better candidates once produced and reviewed.

Nothing was pushed, deployed, imported into Magento or assigned as live media.
Original WANDS judgments do not validate these synthetic assets or variants.
