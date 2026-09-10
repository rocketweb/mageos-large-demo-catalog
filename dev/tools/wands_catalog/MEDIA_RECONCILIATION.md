# Corrected-definition media reconciliation

The definition checkpoint is committed as `17c436b`, and the initial media
reconciliation checkpoint as `cc32066`. The follow-on media work is local
preparation, not a generation run, image approval or catalog deployment.

`var/wands/media-reconciliation-v3` consumes the independently verified
`var/wands/catalog-definitions-v3` packet without editing it or its source images.
It extends the nine findings in `media-reconciliation-v2` with visual triage of
all 38 remaining high-priority references from the newly resolved definitions.
That pass found 33 additional clear mismatches and five uncertain cases.
Historical packets remain intact; their pinned producer versions differ from
the current tool and should not be represented as current-code rebuilds.

## Current evidence

- **93 corrected roots:** every reference decodes as a single supported image,
  with matching original bytes. There are no exact duplicate image groups in
  this set. This is a technical file check, not visual acceptance.
- **93 hero review briefs:** selected options, explicit geometry, sale units,
  specification provenance and exact component quantities are bound to a
  definition fingerprint. Fifty-four roots have component assortments.
- **47 visually reviewed roots:** 42 confirmed defects and five uncertain cases.
  The other 46 references have not yet received visual triage for the corrected
  definitions. None of the 93 references is accepted for generation.
- **465 dependent gallery views:** the five planned views for each corrected
  root remain blocked pending reconciliation. Unchanged roots in the larger
  357-root packet are outside this media pass.
- **Zero model calls, generated images, accepted references or live writes.**

### Initial nine defects and repair directions

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

These are observations of lab imagery, not manufacturer validation. The six
initial supplemental observations live in `media_reconciliation_findings.json`.
The next 38 live in `media_reconciliation_priority1_observations.json`. Neither
file embeds images or absolute media paths. Every observation is tied to the
exact image SHA-256, selected SKU and corrected-definition fingerprint. A changed
definition or reference requires reviewing the observation again; the tool fails
rather than carrying it forward. Sidecars accept failures or uncertainties only
and cannot grant image approval. Duplicate root observations are rejected,
including across separate input files.

Priority 0 now contains 42 defects. Priority 1 contains five reviewed-but-uncertain
references. Priority 2 contains 46 earlier corrected definitions still awaiting
visual review. All 44 newly resolved definitions have now received initial visual
triage: 39 failures and five uncertainties. This overlaps the full packet's
47 reviewed roots, rather than adding another population.

### Findings from the 38-reference pass

Many outdoor assortments were depicted as generic joined sectionals instead of
their named sofas, loveseats, chairs, modules, ottomans and tables. Bistro examples
had square tops or extra chairs where the approved design specifies round or
half-round tables and only two chairs. Other defects include stationary chairs
substituted for rockers, stale finishes, excluded bedding, and nonsensical printed
measurement graphics. Each affected root has its own observation and repair
direction in the review; these are not blanket class-level failure assignments.

The five uncertainties are:

- Ocean Baby (`WANDS-000056`), Pink Chocolate (`WANDS-003817`), Lewis Penguin
  (`WANDS-030143`) and Dreamit (`WANDS-035175`): folded textiles obscure the
  individual component roles and quantities. Hidden components are not declared
  absent simply because the photo does not reveal them.
- Paralimni (`WANDS-027653`): the single end-table identity looks plausible, but
  the corrected geometry and material/construction details still need focused
  review. No automatic replacement is proposed for this reference.

Uncertainty remains distinct from a defect, an unreviewed image and approval in
the JSON status, summary counts, HTML and conditional repair instructions.
These results describe deliberately selected corrected roots, not a random
sample or a full-catalog/model error-rate estimate.

## Quiet rebuild

Use a Python environment with Pillow installed. The existing image-generation
environment includes it, but running this tool never loads an inference model.

```sh
cd /Users/matt/code/rocket-search/.worktrees/wands-merchandising

python3 dev/tools/wands_catalog/reconcile_catalog_media.py \
  --definitions var/wands/catalog-definitions-v3 \
  --findings dev/tools/wands_catalog/media_reconciliation_findings.json \
  --findings dev/tools/wands_catalog/media_reconciliation_priority1_observations.json \
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

Review the remaining 46 references and resolve the five uncertain cases against
their selected designs. Then prepare
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
