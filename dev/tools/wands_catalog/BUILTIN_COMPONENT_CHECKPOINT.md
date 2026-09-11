# Built-in component repair checkpoint, 2026-09-11

This supersedes the current-status section of `REPAIR_AND_CUTOUT_CHECKPOINT.md`.
That earlier checkpoint remains unchanged as historical evidence.

## Result

The approved built-in image generator produced 24 candidates for the 17 remaining
component types. Direct review accepted 16 types; the crib valance remains uncertain
after four attempts. Earlier unsuccessful images and their findings are retained.

The five-family pilot now has 27 accepted component types and 27 visually reviewed
cutouts out of 28 required types. Accepted types cover 67 of 68 physical positions.
The incomplete nursery family is not assembled, so the four complete previews
actually render 65 instances, not 67 or 68.

| Assortment | Required physical pieces | Local visual result |
| --- | ---: | --- |
| Nursery, WANDS-000056 | 3 | Blocked by valance |
| Bakeware, WANDS-003897 | 10 | Initial visual pass |
| Flatware, WANDS-017842 | 45 | Initial visual pass |
| Outdoor, WANDS-030335 | 7 | Initial visual pass |
| Lamps, WANDS-035295 | 3 | Initial visual pass, unchanged assets rechecked |

These are count-controlled HTML/SVG review proofs, not finished raster hero images,
manufacturer measurements, catalog-wide acceptance or publication approval.
Repeated physical pieces deliberately reuse accepted component images.

## Where to review

All paths below are relative to this worktree. Generated files remain ignored.

- `var/wands/builtin-component-review-v1/review.html`: all 28 component types.
- `var/wands/builtin-component-review-v1/attempts.html`: all 24 built-in images,
  actual prompts and direct observations, including rejected attempts.
- `var/wands/builtin-component-repairs-v1/`: unchanged native generated PNGs.
- `var/wands/assortment-preview-v2/review.html`: four complete assortments and
  the nursery blocker. The immutable packet still says family acceptance is pending;
  `builtin_assortment_observations.json` supplies the separate hash-bound visual review.
- `var/wands/builtin-assortment-review/`: the eight accepted desktop/mobile
  screenshots. Earlier element-scoped screenshots inside `assortment-preview-v2`
  are blank or cropped and explicitly excluded from acceptance evidence.
- `builtin_cutout_observations.json`: exact final source/cutout pairs for all 27 types.
  The raw comparison pages intentionally retain failures; do not select masks from
  those pages instead of this reviewed manifest.

## Provenance and reproducibility

`builtin_component_observations.json` records the actual tool prompts, reference
roles, native/reference hashes and direct findings. Seeds, exact model versions and
token usage were not exposed by the tool; no values are invented. Native PNGs remain
unchanged. Lossless WebP derivatives preserve every decoded RGB pixel and canvas.
The review adapter restores all prior history, rather than only the last repair
packet's rows: 77 reviewed attempts, including the 24 new candidates.

The review rebuild produces byte-identical WebP derivatives. Its JSON/HTML results
match after normalizing their own output-directory prefixes; input hashes and
counts match. This is deterministic packaging of existing images, not reproducible
image generation from an undisclosed seed.

The assortment packet reproduces byte for byte: `assortments.json`, `review.html`,
`accepted-masks.json` and `manifest.json` match `assortment-preview-v2-repro`.
Neither old scripts nor previously pinned artifacts were rewritten to accommodate
new observations.

## Cutout repairs

All 16 new raw BiRefNet masks passed the structural contract. Visual inspection on
white, dark and pink backgrounds nevertheless rejected six: three erased reflective
utensil handles and three omitted dark woven furniture frames.

- `repair_cutout_handle.py` repairs only an explicitly confirmed solid handle ROI.
  It preserves RGB and alpha outside that ROI, including genuine head openings.
  Corrected salad/serving forks have no enclosed false holes of at least 16 pixels;
  the slotted spoon retains exactly three true openings. Changed alpha counts are
  38,233, 35,642 and 36,989 respectively.
- `repair_dark_frame_cutout.py` recovers dark frame alpha from the unchanged source
  only with explicit opaque-dark-frame-on-white confirmation. A 120..160 luminance
  ramp is unioned with the raw mask, then enclosed solid interiors are repaired.
  Chair, sofa and table alpha changes are 314,857, 284,224 and 675,682 pixels.
  Their original RGB is untouched and raw masks remain available.
- This is not a general transparency classifier. Do not apply solid-interior
  repair to transparent products, lace or genuine openings. Frame recovery also
  needs visual review; white corner checks do not prove the entire background.
- Cutout work used the existing isolated CPU runtime and pinned local BiRefNet
  weights. No local image-generation GPU run or new model download was needed.

The selected final masks pass both the contract and direct visual review. This
distinction is intentional: a structural pass alone missed material visual damage.

## Verification

`python3 -m unittest discover -s dev/tools/wands_catalog/tests` passes 361 tests,
including nine new tests for built-in provenance/conversion/history and scoped
handle/frame repair. The negative-path tests intentionally log simulated failures.

Browser verification at 1920x1600 and 390x844 found 65/65 loaded SVG image references,
unique physical-instance IDs per family, no horizontal overflow and no reported
page errors. All eight final screenshots were directly inspected. Mobile flatware
is too small for construction-detail acceptance; full-size component, mask and
desktop review provide that evidence. Copper/silver finishes are coordinated, not
identical across independently generated components. Uniform scaling preserves
image ratios, but cannot make synthetic photographs dimensionally exact.

Scripts log to files and emit no routine terminal output. For a fresh rebuild,
run from the repository root, choosing output directories that do not exist:

```sh
python3 dev/tools/wands_catalog/review_builtin_components.py \
  --records dev/tools/wands_catalog/builtin_component_observations.json \
  --layouts var/wands/component-layouts-v2 \
  --baseline var/wands/component-repair-review-v1 \
  --output-dir var/wands/builtin-component-review-new

python3 dev/tools/wands_catalog/build_assortment_preview.py \
  --layouts var/wands/component-layouts-v2 \
  --inventory var/wands/builtin-component-review-v1 \
  --mask-reviews dev/tools/wands_catalog/builtin_cutout_observations.json \
  --output-dir var/wands/assortment-preview-new

tail -f var/wands/assortment-preview-new.log
```

These commands package existing local images; they do not generate replacements.
The reviewed mask manifest is bound to the original inventory paths/hashes, hence
the second command intentionally uses that inventory, not the demonstration rebuild.

## Remaining work and boundary

The valance's 133x71 cm center deck and four 30 cm drop panels are still not
consistently depicted. Attempt four nearly matches the deck ratio, but its top
drop is about 25 percent shallower than the sides and the bottom about 14 percent
shorter. It remains uncertain, not promoted because the other 16 repairs succeeded.
Further work should use a geometry-constrained panel reference, not more blind
prompt retries. An unfolded cross would have a derived 193x131 cm envelope, unlike
the existing folded-under layout; changing that presentation requires a new
validated layout and fresh review, not stretching the candidate into the old slot.

Once the valance is repaired, complete the nursery cutout and assortment review.
Then prepare storefront-quality composition/raster export and verify any intended
media assignments separately. No new user decision is needed merely to continue
the approved local image-repair work, but the design method needs to change.

Code, prompts, tests and observation manifests are committed as Matt MacDougall
with the Rocket Web email. No catalog images are tracked. Nothing was pushed,
deployed, imported into Magento or assigned as live media. Original WANDS judgments
do not validate these synthetic assets, generated variants or rewritten copy.
