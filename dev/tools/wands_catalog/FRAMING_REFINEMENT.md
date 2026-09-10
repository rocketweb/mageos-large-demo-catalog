# Bounded product-specific framing refinement

The equal-area review is committed as `27c6b12`. Both square controls reproduced
their original bytes. The 4:1 portraits retained coherent objects but did not
match either synthetic target: the lamp stayed too wide and the cake server
became too narrow. This follow-up makes exactly one new attempt per product.

The calculator multiplies the previous canvas aspect by target silhouette ratio
divided by observed silhouette ratio. It then selects multiples of 16 with
pixel area within 1% of 768 squared. This assumes similar frame occupancy; that
is a test hypothesis, not a guaranteed geometric constraint. No product
dimensions, prompts, seeds or source images are changed.

The preflight selects 336 by 1744 for the floor lamp (0.65% fewer pixels) and
432 by 1376 for the cake server (0.78% more pixels). These are new text-only
generations, not resized or distorted versions of the earlier images.

The runner reuses the tested generation, ledger and no-overwrite functions. All
three earlier runners and their frozen evidence remain unchanged. Every started
attempt is consumed; there are no automatic retries, masks or composites.

## Quiet execution

From `/Users/matt/code/rocket-search/.worktrees/wands-merchandising`:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  /Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/refine_catalog_framing.py \
  --source-review var/wands/framing-review-v1 \
  --approved-source-sha256 370df521257c6e5b2dc6548cef806800a3df576a55a602bab8c243cfed189632 \
  --output-dir var/wands/framing-refinement-v1

tail -f var/wands/framing-refinement-v1.log
```

The default preflights without a model load. Add `--run` for the authorized two
attempts. Output stays in the sibling log unless `--json` is explicitly set.
The full runtime, calculated canvas choices, actual prompts, source observations
and execution cases are retained. Completed runs verify and skip both images.

## Review without GPU use

After directly inspecting both images, record exact trial IDs, case hashes,
image hashes, the six visual checks and approximate subject bounds. The same
script can build the review with the three source/run arguments above plus:

```sh
--observations dev/tools/wands_catalog/media_framing_refinement_observations.json \
--review-dir var/wands/framing-refinement-review-v1
```

Use `python3` for this CPU-only review mode and a fresh review directory. Review
does not alter execution metadata or grant mask, assembly or publication
approval. Candidate media and generated review pages remain outside Git.

If this refinement still fails proportions, stop aspect-only iteration. Further
work should test explicit geometric conditioning or a render-based approach in
a separately scoped local prototype, not continue guessing aspect ratios.
