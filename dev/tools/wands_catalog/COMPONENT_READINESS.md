# Component readiness after the framing passes

This is the current local component-development inventory, not a live catalog
assignment. It covers five proposed assortment layouts, 28 component types and
68 physical positions. The original catalog images and Magento records remain
unchanged.

## Current evidence

| Status | Component types | Meaning |
| --- | --- | --- |
| Initial visual pass | 3 | Dinner fork, refined floor lamp, refined cake server |
| Uncertain | 1 | Table lamp proportions remain unresolved |
| Unattempted | 24 | No single-component candidate has been generated |
| Mask ready | 0 | No mask has been produced or evaluated |
| Assembly ready | 0 | No complete set is ready to compose or publish |

The three visual passes cover ten planned physical positions if eventually
accepted for reuse. They are not ten independently generated or verified
images. Ten component attempts have been reviewed across the three review
packets, containing eight distinct image hashes: two square controls exactly
reproduced their earlier candidates. Failed historical attempts remain in the
inventory even when a later candidate passes.

The proposed candidate pointer prefers the latest initial visual pass, otherwise
the latest uncertainty or failure, in the explicitly ordered review packets.
It never changes original media or grants mask, composition, conditioning or
publication approval. Counts of unattempted components are scoped to this
single-component workflow, not the earlier whole-product attempts.

## Rebuild without a model

Run from `/Users/matt/code/rocket-search/.worktrees/wands-merchandising`:

```sh
python3 dev/tools/wands_catalog/build_component_readiness.py \
  --layouts var/wands/component-layouts-v2 \
  --reviews var/wands/component-image-review-v1 \
    var/wands/framing-review-v1 \
    var/wands/framing-refinement-review-v1 \
  --output-dir var/wands/component-readiness-next

tail -f var/wands/component-readiness-next.log
```

Use a fresh output directory. The builder verifies input and image fingerprints,
binds every reviewed candidate back to its exact component brief, rejects
conflicting provenance, and preserves all prior attempts. It emits an asset
inventory, per-family missing-component lists, a review page and a manifest.
Output is quiet unless `--json` is requested. Media and generated reports remain
in ignored `var/`; only tooling, tests, instructions and observations enter Git.

## Next execution order

1. Resolve the uncertain table lamp geometry and its visual match to the refined
   floor lamp. A coherent individual lamp does not establish a matching set.
2. Prototype mask evaluation on the three initial passes. Preserve thin stems,
   fork tines and bright metallic edges. Do not turn the contrast-envelope
   diagnostics into a production mask or erase all near-white pixels.
3. Generate and review the remaining flatware component types using the existing
   corrected briefs. Check shared material, viewpoint and construction before
   multiplying any component into its planned repeated positions.
4. Build initial component candidates for the other three planned assortments,
   with separate checks for each component identity and synthetic dimensions.
5. Compose only when all required components and masks for a family pass. Use
   uniform scaling, exact counts and the validated layout; never stretch an
   image independently in width and height to conceal a geometry failure.
6. Reconcile the finished media with the corrected catalog definitions, then
   prepare a separately approved media/import deployment with rollback and
   storefront verification. Local candidate selection does not authorize it.

Start a later review at `var/wands/component-readiness-v1/review.html`. Its image
cards link to the full comparison pages and actual prompts. The successful
refinement comparison is at `var/wands/framing-refinement-review-v1/review.html`.

## Verification

The full Python suite passes 331 tests. The readiness packet verifies 533 input
hashes and three output hashes; all four files, including its manifest, match a
fresh rebuild byte for byte. All local image and review links resolve. Browser
checks at 1920 by 1080 and 390 by 844 find 28 cards, four decoded images, no page
overflow and no reported browser errors. Both generation runs verify zero
pending work on resume, without loading the image model again.
