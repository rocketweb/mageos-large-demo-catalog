# Catalog corrections and guarded expansion

The later [remaining-definition resolution batch](DEFINITION_RESOLUTIONS.md)
supersedes the held-definition counts below. It resolves the 41 remaining
family findings and eight overlapping holds in a new immutable local packet.
The figures in this document describe the earlier expansion-v3 checkpoint.

This phase turns the frozen depth pilot's repair queue into local, reviewable
product definitions. It then extends tested rules to explicitly reviewed
families outside the pilot. It never imports products, calls a model, uploads
media, installs attributes or changes the live store.

## Earlier local candidate

The September 9 candidate at `var/wands/catalog-expansion-v3` contains:

- 321 root products and 1,356 active child candidates. The original 300-root
  pilot remains a separate denominator; 21 additional families were examined.
- 49 corrected root definitions: 31 from the pilot and 18 from the expansion.
  Corrections cover nightstand widths, pillowcase dimensions and pack counts,
  short kitchen curtains, a shower liner, bed configurations, nursery-decor
  assortments, outdoor furniture sets, a lamp set, a wall unit and a fabric cut.
- 386 changed active records and 20 proposed child retirements, totaling 406
  distinct affected-record proposals. These are local model-record counts, not
  a claim about affected database rows on a remote store.
- 141 recovered source-backed facet values across 120 records: 108 style,
  28 material and 5 bulb-base values. These use exact normalization rules and
  retain the source evidence. Conflicting values remain withheld.
- 1,605 non-executable gallery briefs, including 245 rewritten for corrected
  definitions. Three byte-bound image-repair drafts address visually observed
  curtain, cabinet-finish and nursery-assortment errors. No images were generated.
- 49 prepared storefront acceptance cases and 306 existing recommendation
  candidates flagged for merchant review. These checks have not run in Magento;
  the recommendations and four collection drafts have not been installed.

Synthetic dimensions are available for 295 of the original 300 selected gallery
subjects, up from 268. Availability is not visual acceptance or a manufacturer
measurement. The expanded packet has 314 dimensional designs across 321 subjects;
some held definitions have geometry but still have unresolved identity or unit
problems. All selected references remain unapproved for the corrected variants.

The complete 2,000-family option scan flags 87 candidate issues. Forty-six of
those flagged families now have local correction candidates; 41 remain for
source/design review. The 49 total corrections also include three products not
represented by that family-audit count. Do not describe the scan as a full
semantic audit or the whole catalog as corrected.

## Build and verify

Run from the catalog repository, not the Mage-OS application directory:

```sh
cd /Users/matt/code/rocket-search/.worktrees/wands-merchandising

python3 dev/tools/wands_catalog/catalog_repairs.py \
  --depth-packet var/wands/depth-pilot-v9-synthetic-dimensions \
  --expand-tested-rules \
  --media-dir /Users/matt/code/mageos-latest/pub/media/import/wands \
  --output-dir var/wands/catalog-expansion-next

python3 dev/tools/wands_catalog/verify_catalog_repairs.py \
  --packet var/wands/catalog-expansion-next
```

Choose a fresh output directory every time. Omit `--expand-tested-rules` and
`--media-dir` to prepare only the original pilot corrections. The builder refuses
an existing destination or changed pinned inputs. Builds with identical inputs
and implementation produce byte-identical packet files.

Both commands are quiet by default, including runtime failures. Inspect their
exit status and sibling logs. Add `--json` only when terminal output is wanted.

```sh
tail -f var/wands/catalog-expansion-next.log
tail -f var/wands/catalog-expansion-next.verify.log
```

Open `review.html` for before/after cards, proposed descriptions, known image
issues, child retirements and dimension details. `pilot-review.html` shows all
candidate roots, including the added families when expansion is enabled.

## Evidence and safety rules

- `repair_designs.py` contains exact pilot identities and guarded expansion
  definitions. A Nightstands classification alone does not justify replacing
  end-table dimensions. Cylindrical cabinets retain equal width and depth.
- Pillowcase expansions require agreement on product type, sheet exclusions,
  subtype and all supplied quantity fields. A two-pack has two separately
  dimensioned components, not a misleading set-wide measurement.
- SKU and URL identities stay stable even when an old SKU/slug contains an
  obsolete size or finish. Current prices and inventory stay unchanged except
  the explicitly marked configurable-to-simple proposal described below.
- Source facts are never overwritten to fit a synthetic design. Geometry is
  labeled `Synthetic lab dimension, not a manufacturer measurement`.
  Options and new assortments have a separate synthetic-design disclosure.
- Assortment parent descriptions enumerate the included roles and quantities.
  Variable sets list only actually offered combinations. Accessory pillows do
  not inflate a furniture-piece count. Bed and nursery copy makes no safety,
  mattress-fit, installation, capacity or infant-sleep claim.
- `changes.proposed.jsonl` and `inverse.proposed.jsonl` contain matching forward
  diffs and full original records. The verifier rewinds and replays them, checks
  original family closure, compares the inverse to pinned catalog values, and
  verifies input/output hashes. This is not a database rollback implementation.
- `retirements.proposed.jsonl` proposes 20 redundant child retirements across five
  families. One root, Carrollton, would become simple. Its candidate stock and
  price come from an identified existing child; no actual stock transfer,
  deletion or type conversion is approved or performed.
- `specifications.sparse.proposed.jsonl` is set-only. Empty fields do not mean
  delete. Component payloads stay separate from product measurements. Actual
  import needs snapshot-aware clearing of replaced synthetic fields, storage
  for component specifications and disclosure-aware storefront rendering.
- Image observations are tied to exact reference hashes. Changed reference
  bytes cannot silently inherit a prior observation. Image drafts and gallery
  briefs stay non-executable until reference repair and visual acceptance.
- Original WANDS query/judgment hashes and the existing benchmark freeze stay
  unchanged. Old relevance judgments do not establish quality for rewritten
  products. Copied query seeds remain unjudged and need refresh before a new
  enriched-catalog evaluation.

## Remaining work at the earlier checkpoint

Eight definitions are explicitly held in this packet: a bakeware assortment,
flatware assortment, burger-press/fry-cutter kit, pillowcase/fitted-sheet identity,
conflicting outdoor-set count, conflicting pillowcase pack count, unknown
pillowcase-set quantity and a plastic nightstand with wood-finish choices.
Other full-catalog audit findings require their own source/component review;
class or piece count alone is not permission to invent a configuration.

Before publication: resolve the remaining definitions, visually reconcile
selected references, generate and audit approved galleries, implement the
disclosure/component storage and renderer, and refresh recommendations against
the final definitions. Then prepare a fresh destination snapshot, exact remote
diff, backup and inverse operation for approval. Code deployment, data import,
media upload and live acceptance remain separate steps. Product images stay
outside Git; this work does not change the existing distribution policy.
