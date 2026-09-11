# Nursery completion checkpoint, 2026-09-11

The remaining valance is repaired. All 28 component types in the five-family pilot
now have initial visual passes and reviewed cutouts. All five complete assortments
have initial local visual acceptance, covering 68 physical pieces. This is pilot
completion, not catalog-wide media acceptance or deployment.

## What changed

The previous four prompt-only valance attempts could not hold consistent panel
depths. `prepare_valance_reference.py` now derives a five-panel geometry reference
from the unchanged synthetic definition: a 133x71 cm deck and four 30 cm drops.
The flat SVG is a tool input, not a substitute catalog image. ImageMagick rendered
it to a PNG reference, then the built-in image generator rendered the actual textile.
Only one new generated candidate was needed for this pass.

The new image shows four connected, evenly sized drops. Its approximate deck ratio
is 1.88 against the design ratio 1.87; visible drop depths vary by about five percent.
Those are visual proportion checks, not measurements of a real product. The native
PNG and failed historical candidates remain unchanged. Model version and seed were
not exposed and are not invented. Actual prompt, input role and hashes are in
`valance_geometry_observations.json`.

BiRefNet's existing local CPU runtime produced a usable cutout directly. The deck's
checked interior alpha is 254, so its slight translucency is below one percent.
Review on white, dark and pink found no missing panels, interior holes or objectionable
fringe. No manual alpha repair or product RGB editing was needed.

## Presentation, not a product-definition change

An unfolded valance has a 193x131 cm display envelope. Putting that cross into the
old folded-under 71x133 cm slot would misrepresent relative size. The new
`build_nursery_assortment.py` creates a separate layout with explicit derived-envelope
metadata, three count-checked positions, non-overlapping slots and uniform scaling.
It preserves the old definitions, old layout packet and all prior review evidence.

The nursery proof contains one quilt, one empty elasticized sheet and one unfolded
valance. The four drop panels are attached parts of one valance, not four extra
products. Pale-blue ocean patterns coordinate but do not use identical motifs.
The sheet shows its elasticized reverse while the quilt is face-up; these are useful
inclusion-proof views, not a styled in-use bedding scene. There is no crib, mattress,
infant, fit claim or sleep arrangement.

## Review and saved files

Paths are relative to the repository root:

- `var/wands/nursery-assortment-v1/review.html`: complete three-piece nursery proof.
- `var/wands/assortment-preview-v2/review.html`: the other four previously accepted
  assortments. Its historical nursery blocker is intentionally unchanged.
- `var/wands/valance-component-review-v1/review.html`: current 28-type component
  inventory, 78 historical reviewed attempts, zero failed/uncertain/unattempted types.
- `var/wands/valance-component-review-v1/attempts.html`: new candidate and actual prompt.
- `var/wands/valance-built-in-v1/WANDS-000056-skirt-geometry-v1.png`: native image.
- `var/wands/valance-cutout-v1/`: original-RGB cutout, model provenance and raw review.
- `var/wands/valance-visual-evidence-v1/`: reviewed mask and assortment screenshots.

`nursery_assortment_observations.json` binds the visual acceptance to exact data,
HTML and screenshot hashes. It is separate from the immutable preview's pending
family-acceptance field. The older four-family acceptance remains in
`builtin_assortment_observations.json`; together these cover all five pilot families.

## Rebuild and checks

From the repository root, choose a fresh output directory:

```sh
python3 dev/tools/wands_catalog/build_nursery_assortment.py \
  --layouts var/wands/component-layouts-v2 \
  --inventory var/wands/valance-component-review-v1 \
  --geometry var/wands/valance-geometry-v1 \
  --previous-masks dev/tools/wands_catalog/builtin_cutout_observations.json \
  --mask-reviews dev/tools/wands_catalog/valance_cutout_observations.json \
  --output-dir var/wands/nursery-assortment-new

tail -f var/wands/nursery-assortment-new.log
```

Routine output stays in log files. The generated review, segmentation and assembly
terminal-capture logs are empty. Initial setup errors are retained in logs: the
review output guard rejected a geometry PNG placed in the common `var/wands`
parent, so its identical bytes were copied into an isolated reference directory;
the segmentation weights path was corrected to the existing nested model file.
Neither error triggered image regeneration or source overwrites.

`diff -rq var/wands/nursery-assortment-v1 var/wands/nursery-assortment-v1-repro`
confirms the four-file packet reproduces byte for byte. The full Python suite passes
368 tests, including new geometry, complete-count, uniform-fit, containment and
overlap checks. Browser checks at 1920x1700 and 390x844 load all three image references,
show no horizontal overflow and report no page errors. Full-article desktop and
full-page mobile captures were directly inspected.

## Next stage and boundary

The unresolved-component repair stage is complete for this pilot. Next is preparing
storefront-oriented compositions and raster exports, then separately reviewing
product/media assignments and deployment preflight. These layout proofs are not
automatically approved storefront hero images.

No catalog image is tracked in Git. No push, merge, publication, Magento import or
live media assignment occurred. Original WANDS judgments do not validate these
synthetic assets, dimensions, variants or rewritten copy.
