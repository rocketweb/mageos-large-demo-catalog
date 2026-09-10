# Corrected-definition media reconciliation

The definition checkpoint is committed as `17c436b`. The follow-on media work is
local preparation, not a generation run, image approval or catalog deployment.

`var/wands/media-reconciliation-v2` consumes the independently verified
`var/wands/catalog-definitions-v3` packet without editing it or its source images.
It supersedes the preliminary `media-reconciliation-v1` review by adding six
new, visually inspected defects to the three already recorded in the definition
packet. Historical packets remain intact.

## Current evidence

- **93 corrected roots:** every reference decodes as a single supported image,
  with matching original bytes. There are no exact duplicate image groups in
  this set. This is a technical file check, not visual acceptance.
- **93 hero review briefs:** selected options, explicit geometry, sale units,
  specification provenance and exact component quantities are bound to a
  definition fingerprint. Fifty-four roots have component assortments.
- **Nine confirmed defects:** three earlier findings and six additional local
  inspections. The other 84 references have not been visually accepted for the
  corrected definitions. Do not interpret absence of a finding as a pass.
- **465 dependent gallery views:** the five planned views for each corrected
  root remain blocked pending reconciliation. Unchanged roots in the larger
  357-root packet are outside this media pass.
- **Zero model calls, generated images, accepted references or live writes.**

### Confirmed defects and repair directions

| Root SKU | Observed problem | Required corrected hero |
| --- | --- | --- |
| WANDS-003897 | Two nested handled pans | All ten named bakeware components, including the separate lid |
| WANDS-012133 | Loose spice spoons on a board | Two actual fabric curtain panels with the spice-spoon print |
| WANDS-014741 | Gold-colored cabinet | The selected Oak three-drawer nightstand |
| WANDS-017842 | Incomplete, malformed utensils | Eight five-piece place settings plus five named serving utensils |
| WANDS-022607 | Translucent purple-tinted plastic | The selected Black plastic nightstand |
| WANDS-022642 | Burger inside an appliance-like form, loose fries, branding | One assembled burger press and one separate assembled fry cutter |
| WANDS-034345 | Filled pillow on extra folded bedding | One empty pillowcase; no insert or sheets |
| WANDS-038422 | Wrapped box-like object | The twelve separately countable nursery-decor pieces |
| WANDS-042749 | Rectangular table, six chairs, cushions and vase | One round table and four chairs; no cushions |

These are observations of lab imagery, not manufacturer validation. The six new
observations live in `media_reconciliation_findings.json`, without embedded
images or absolute media paths. They are tied to the exact image SHA-256, selected
SKU and corrected-definition fingerprint. A changed definition or reference
requires reviewing the finding again; the tool fails rather than carrying it
forward. The sidecar accepts failures only and cannot grant image approval.

Priority 0 contains nine defects. Priority 1 contains the other 38 newly resolved
definitions. Priority 2 contains 46 earlier corrected definitions awaiting
visual reconciliation. The six new defects are also among the 44 newly resolved
definitions, so those categories must not be added as independent populations.

## Quiet rebuild

Use a Python environment with Pillow installed. The existing image-generation
environment includes it, but running this tool never loads an inference model.

```sh
cd /Users/matt/code/rocket-search/.worktrees/wands-merchandising

python3 dev/tools/wands_catalog/reconcile_catalog_media.py \
  --definitions var/wands/catalog-definitions-v3 \
  --findings dev/tools/wands_catalog/media_reconciliation_findings.json \
  --output-dir var/wands/media-reconciliation-next

tail -f var/wands/media-reconciliation-next.log
```

Use a fresh output directory. Normal results and runtime errors go to the sibling
log; `--json` explicitly opts into a terminal summary. This does not modify the
input packet, original media, model configuration or Magento. No credentials or
network service are used.

Outputs:

- `review.html`: responsive reference/contact-sheet review with exact selected
  options, countable component lists, findings and expandable draft instructions.
- `hero-review-drafts.jsonl`: 93 non-executable, definition-bound review briefs.
- `gallery-dependencies.jsonl`: 465 blocked view-to-hero relationships.
- `image-integrity.json`: byte checks, full decoding and exact duplicate groups.
- `definition-verification.json`: the independent definition verifier's result.
- `manifest.json`: pinned inputs, output hashes, counts and Pillow version.

The drafts deliberately lack the generator's `prompt`, `output_file` and
`reference_images` job fields. They cannot be passed straight to the existing
reference generator. An `executable: false` flag alone would not provide that
boundary because the historical generator does not enforce that field.

## Next acceptance boundary

Review the remaining references against their selected designs. Then prepare
and approve a separate, bounded hero-repair run with versioned output files and
visual acceptance before creating derivative views. In particular:

- Use actual corrected option values, never historical SKU fragments such as
  `30-IN`, `OAK`, `FULL` or `2-PIECES`.
- Preserve original conflicting WANDS evidence outside the generation prompt.
  The chosen synthetic definition and exact component manifest drive the brief.
- Reject incomplete assortments, duplicated furniture, malformed utensils and
  stale finishes. A representative handful is not a complete-set hero.
- Do not claim physical measurements from pixels. Keep explicit synthetic
  geometry and scope in metadata, and avoid fit, capacity or safety claims.
- Keep nursery-decor assortments laid out, without an infant or sleeping setup.
- Recheck reference bytes and definition fingerprints at any later approval or
  generation step. Old WANDS-based image audits do not validate rewritten designs.

Catalog images stay outside Git. The renderer links to the local original files
without copying or embedding them. This review is not a portable community media
release; distribution remains a separate versioned-media packaging task.
