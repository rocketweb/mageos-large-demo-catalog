# Catalog realism review

This workflow prepares a local proposal, not a Magento import. It preserves the
raw WANDS source, SKUs, URL keys, categories, and the frozen relevance benchmark.
It does not call an LLM, generate images, assign brands, or change stock remotely.

## Build the sample

Run from the catalog repository. All input paths below are read-only.
Choose a new output directory for each review revision. Existing packets are
never overwritten. No virtual environment or additional Python packages are needed.

```sh
python3 dev/tools/wands_catalog/build_realism_review.py \
  --source-products /Users/matt/code/rocket-search/data/raw/wands/product.csv \
  --prepared-products /Users/matt/code/mageos-latest/var/wands/products.csv \
  --merchandising-dir /Users/matt/code/mageos-latest/var/wands/merchandising \
  --output-dir var/wands/realism-review
```

Normal execution writes nothing to the terminal. Follow progress separately:

```sh
tail -f var/wands/realism-review.log
```

Failures return a nonzero exit status and put the traceback in that log.
`--json` explicitly opts into a manifest on stdout. Logs live beside the output
directory, so a failed build still leaves a diagnostic log. Output packets are
staged and renamed only after the inputs have been rechecked for changes.

Open `review.html` inside the output directory. The packet contains:

| Artifact | Purpose |
| --- | --- |
| `products.review.jsonl` | 100 before/after proposals, source evidence, specifications, configurable child copy/prices and inventory scenarios |
| `bundles.review.jsonl` | All input bundles, compatibility flags, potential replacements and restrained description proposals |
| `variant-image-briefs.jsonl` | Reference-edit instructions, blocked until a correct family/geometry reference is approved |
| `brand-directions.json` | Fictional brand directions only, with no product assignments |
| `rules.json` | Versioned class price anchors and fact mappings |
| `manifest.json` | Input/output hashes, exact counts and approval gates |

The report compares local import artifacts, not a fresh live database snapshot.
Generated packets and logs remain under ignored `var/`; source and tests are
reviewable Git changes. Identical inputs and builder code produce identical
packet bytes. Timestamps occur only in the operational log.

## Priority rules and review gates

1. **Names:** preserve short source names, collections, quantities and product
   subtypes. Compact long keyword-stuffed names. Check every changed title for
   lost distinctions or options that contradict the family. This is intentionally
   not an automated approval to rename the entire catalog.
2. **Descriptions:** use only allowlisted source features with a single value.
   Escape source HTML. Keep selected child options separate from parent option
   lists. Sparse copy remains flagged for editorial work. Do not introduce
   certifications, warranties, performance or suitability claims.
3. **Prices:** match an explicit product class, never an unrelated word elsewhere
   in a title. All anchors and variation are synthetic USD lab assumptions, not
   current retail research. Every price needs sale-unit, pack-count, dimension,
   subtype and material-tier review. Color/finish does not change a price; size
   ordering is semantic and independent of option order. Unknown sizes hold the
   family. Large price movements receive an additional review flag.
4. **Images:** choose an approved reference before editing. Preserve construction,
   composition and geometry. A different light count, piece count or geometry
   requires its own approved reference; never independently regenerate a color
   family and assume it is the same product. No existing media is overwritten.
5. **Bundles:** split pipe-separated source class labels and compare exact class
   tokens. Never let `Patio Sofas` match indoor `Sofas` by substring. Flag price
   outliers against the option median. Replacement candidates are ranked by
   actual existing price distance, not random selection. They still need fit,
   palette and intended-use review. Audit every selectable combination, including
   bed/bedding sizes, table/chair counts, vanity/faucet fit and outdoor suitability.
   Nursery and older-child assortments must be separated before approval.
6. **Specifications:** withhold contradictory values and dimensions without
   explicit units. Withhold fixed source attributes that overlap a synthetic
   variation axis. Do not infer that all source properties apply to every child.
7. **Brands:** propose a small coherent direction, but do not relabel real brands.
   Audit source names/copy/features first. Fictional names are not checked for
   legal uniqueness and are only proposals for this private lab.
8. **Availability:** deterministic synthetic in-stock, low-stock, out-of-stock,
   backorder and clearance candidates. Configurable availability derives from
   children. Bundle availability depends on all required options having a salable
   choice. No promised restock dates, fabricated sales counts or bestseller claims.

## Acceptance before expansion or deployment

- Review the sample and approve the rules and any curated exceptions.
- Resolve title/subtype, sale-unit, specification and family contradictions.
- Approve specific reference images and review appearance side by side.
- Approve a complete compatible selection matrix for each bundle, not just its
  default configuration. Replacement candidates are not approved replacements.
- Expand the reviewed rules into a separate full-catalog proposal.
- Before live writes: fetch a fresh remote snapshot, present the exact dry-run
  diff and affected counts, retain a backup and inverse operation, and obtain
  explicit import approval. The builder deliberately emits no importable CSV.
- Following an approved import, separately verify Magento indexing, search,
  category/PDP rendering, configurable prices and bundle behavior on the remote.

## Tests

```sh
python3 -m unittest discover -s dev/tools/wands_catalog/tests -p 'test_*.py'
```

Tests cover title preservation, class token matching, pricing invariants, feature
conflicts, unit handling, variant facts, reference geometry, sampling, escaping,
quiet execution, deterministic packets, unchanged inputs and overwrite refusal.
