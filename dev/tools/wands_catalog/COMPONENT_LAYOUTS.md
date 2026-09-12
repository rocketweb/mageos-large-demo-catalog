# Count-controlled component layout planning

The completed image-pilot tooling is committed as `56dbe81`. Its image review
remains three initial passes, two uncertainties and seven failures. This next
stage prepares component layouts for the five failed multi-piece sets. It does
not change those visual verdicts or generate replacement images.

## Current local packet

`var/wands/component-layouts-v2/review.html` shows five planning diagrams:

| Product | Physical positions | Component types | Layout |
| --- | ---: | ---: | --- |
| Ocean nursery textiles | 3 | 3 | Separate component envelopes |
| Copper-finish bakeware | 10 | 8 | Empty pieces, separate lid |
| Skaneateles flatware | 45 | 10 | Eight five-piece settings plus five servers |
| Merlyn outdoor furniture | 7 | 5 | Five furniture pieces plus two pillows |
| Skiatook lamps | 3 | 2 | One floor lamp and two table lamps on one floor line |
| Total | 68 | 28 | No component assets generated |

Rectangles represent synthetic component envelopes, not product silhouettes,
fabric cutting patterns, construction drawings or a physically installed
arrangement. The diagrams intentionally carry labels for reviewers. They must
not be used as product photos or sent directly to a model as conditioning
images. The original and failed candidate images are not used as references.

The layout planner expands each component quantity into exact named instances,
checks grouping and non-overlap, and preserves a common synthetic scale.
Repeated instances refer to one component requirement. This prepares reuse of
an accepted asset; no asset reuse or compositing has been executed yet.

The component briefs preserve the corrected parent options, specifications,
constraints, individual geometry, synthetic provenance and per-role construction
checks. Examples include elasticized sheet corners, a rectangular crib-skirt
platform with drop panels, a separate matching pan lid, distinct serving-utensil
types and complete lamp base/stem/socket/shade assemblies.

Correct slot counts do not prove correct objects in generated pixels. Asset
identity, construction, viewpoint, masking, lighting and the final composition
will still need visual acceptance. Original WANDS judgments do not validate
these synthetic media changes.

## Remaining pilot cases

The coverage file accounts for all 12 reviewed roots:

- Five failed assortments receive proposed component layouts.
- The bunk frame and empty pillowcase remain construction-specific repairs.
  A three-level frame must not be redefined as three separate saleable beds.
- Curtains and drawer construction still need focused clarity review.
- Fabric, the Black plastic nightstand and Abe dining set retain their initial
  local passes, without image-use or publication approval.

The other 77 deferred candidates and 465 planned gallery views are unchanged.

## Quiet, CPU-only use

Run in the tooling worktree:

```sh
cd /Users/matt/code/rocket-search/.worktrees/wands-merchandising

python3 dev/tools/wands_catalog/plan_catalog_component_layouts.py \
  --review var/wands/media-pilot-review-v1 \
  --selection dev/tools/wands_catalog/media_component_layout_selection.json \
  --output-dir var/wands/component-layouts-next

tail -f var/wands/component-layouts-next.log
```

Use a fresh output directory. Normal output and errors stay in the sibling log;
`--json` explicitly opts into terminal output. The command does not load a
model, use credentials, call a service, create raster images, update Magento or
overwrite source packets. The corrected v2 packet replaces v1 as the current
review target; the exploratory v1 files remain preserved.

Outputs are:

- `layouts.proposed.jsonl`: exact component instances, groups, envelopes and scale.
- `component-briefs.proposed.jsonl`: one pending asset requirement per component
  type, with parent context and construction checks.
- `coverage.jsonl`: the disposition of every reviewed root.
- `review.html`: readable planning diagrams, manifests and deferred cases.
- `manifest.json`: all input/output hashes, counts and explicit non-approval flags.

The planner rechecks the source review's pinned bytes and observation verdicts.
Stale definitions, duplicate or unknown selections, wrong component sums,
invalid dimensions, dropped/duplicated instances, overlap, scale drift or broken
place-setting groups fail validation. It rechecks input hashes before publishing
the packet locally. This is not an executable queue for the legacy image
generator or the bounded whole-product pilot runner.

## Next experiment, not yet authorized or implemented

Start with a small component-asset pilot and verify each individual component
before assembly. Use a consistent orthographic viewpoint and lighting. For
repeated items, reuse an accepted component at the planned scale and count.
Then inspect the resulting composition as a separate acceptance step.

Do not expand to all 28 component types automatically. The diagrams do not
establish whether image generation, masking or composition will meet the
required quality. Asset generation, image editing/compositing, use as model
references, retries and publication need a separately scoped next step.
