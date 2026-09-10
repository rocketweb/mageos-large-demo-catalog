# Component completion checkpoint, 2026-09-10

All 28 planned component types across five pilot families now have a reviewed
candidate. This pass generated 25 new images, one attempt per selected component,
using cached local FLUX.2 Klein 4B, 4-bit, four steps and guidance 1.0. No model
downloads, hosted image calls, automatic retries, product imports or live media
replacements occurred. Catalog images remain outside Git.

## Results

| Batch | New images | Initial visual passes | Uncertain | Failed |
| --- | ---: | ---: | ---: | ---: |
| Table lamp | 1 | 0 | 1 | 0 |
| Flatware | 8 | 3 | 1 | 4 |
| Bakeware | 8 | 2 | 1 | 5 |
| Nursery | 3 | 1 | 1 | 1 |
| Outdoor | 5 | 1 | 1 | 3 |
| This pass | 25 | 7 | 5 | 13 |

Including three earlier passes, the inventory has **10 initial visual passes,
five uncertain components, 13 failed components, zero unattempted components**.
There are 35 reviewed attempts with 33 unique image hashes; two historical
square controls reproduced earlier bytes. Proposed reuse of the ten initial
passes would cover 33 of 68 physical positions, not 33 independently generated
images. No masks or complete sets have passed acceptance.

Current review: `var/wands/component-readiness-v2/review.html`.
It links to actual images, full reviews and the exact prompts/seeds. The five
generation folders are `var/wands/completion-{lamps,flatware,bakeware,nursery,outdoor}-v1`.
Each has frozen execution cases, image metadata and an attempt ledger.

## Rebuild the inventory without loading a model

Run from `/Users/matt/code/rocket-search/.worktrees/wands-merchandising`:

```sh
python3 dev/tools/wands_catalog/completion_readiness.py \
  --layouts var/wands/component-layouts-v2 \
  --baseline var/wands/component-image-review-v1 \
    var/wands/framing-review-v1 var/wands/framing-refinement-review-v1 \
  --completion var/wands/completion-lamps-review-v1 \
    var/wands/completion-flatware-review-v1 var/wands/completion-bakeware-review-v1 \
    var/wands/completion-nursery-review-v1 var/wands/completion-outdoor-review-v1 \
  --output-dir var/wands/component-readiness-next

tail -f var/wands/component-readiness-next.log
```

Use a fresh output directory. The v2 packet checks 626 input fingerprints and
three output hashes. Its four files reproduce byte for byte. Browser checks at
1920 by 1080 and 390 by 844 decoded all 28 images, found 28 cards, no page-width
overflow and no reported browser errors. Screenshots were inspected locally.

The separate `completion_review.py` is the working reviewer. The frozen
generation runner's old review mode expects a paired-experiment `arm` field;
using it for these nonpaired cases fails. The fix preserves original cases,
hashes and metadata instead of rewriting recorded generation evidence.

## Next repair order

1. Correct semantic failures first: crib skirt was interpreted as a wearable
   garment; serving fork has four instead of two tines; muffin tray has nine
   instead of twelve wells; outdoor chair became a chaise; pan lid reads as a
   tray. Each observation file records the exact offending image and case hash.
2. Correct geometry and camera failures: dinner knife, salad fork, spreader,
   rectangular and loaf pans, cooling rack, sofa and ottoman. Preserve synthetic
   definitions; do not stretch images to conceal a mismatch.
3. Resolve the five uncertain candidates: lamp width/height, slotted-spoon
   openings and proportions, baking-sheet proportions, empty fitted-sheet
   construction, and outdoor-table proportions.
4. Evaluate cutouts on the ten initially passing components, with a separately
   provisioned local removal model. No cached removal model or `rembg` runtime
   was found in the inspected image environment. The new read-only validator
   checks the file contract but does not make a mask or grant visual acceptance.
5. Match finishes, lighting, viewpoints and relative scale within each family.
   Only then assemble exact component counts using validated masks and uniform
   scaling. None of these five families is yet complete.

These results cover the five component-layout pilot families only. The broader
repair queue, remaining gallery views, Magento representation, enriched-catalog
search judgments and separately approved deployment remain subsequent work.
Original WANDS relevance judgments do not validate synthetic media or variants.
