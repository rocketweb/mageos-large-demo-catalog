# Catalog depth pilot

This is the next local realism phase, separate from prior catalog releases and
the frozen September 5 search study. It prepares a review packet. It does not
import products, install attributes, change the live site, run inference, or
spend image-generation quota.

## What is implemented

- A deterministic 300-root acceptance set: 30 products in each of ten departments.
  Existing configurable families are preferred, balanced across classes, then
  standalone products fill departments without enough families. Selection does
  not depend on search scores or image quality.
- One shared 21-attribute schema for the Python builder and Magento data patch.
  Source values become controlled material, style, shape, pattern, finish,
  placement and lighting facets, plus explicit-unit measurements and care text.
- Parent and child specification records with original evidence, normalized
  values, synthetic-option flags and per-field withholding reasons.
- An explicitly approved, opt-in synthetic dimension layer for this pilot.
  Class-specific fictional design anchors cover furniture, textiles, tile,
  lighting, selected kitchen items and appliance/fixture exteriors. These are not manufacturer measurements,
  market-derived averages, fit guarantees or recovered WANDS facts.
- Five gallery briefs per selected root: existing-hero audit, alternate angle,
  detail, room context and dimensions. A single deterministic salable-first child
  represents a configurable family for this pilot. This is not a full gallery
  for every child. The original parent reference is identified as such and is
  not silently treated as an approved image of the selected variant.
- Up to three alternatives and three complementary candidates per root, with
  matching appearance evidence, exact class/role rules, stock and price checks.
  These are review candidates, not assertions of physical fit or installed links.
- Four curated shopping drafts, historical source-rating display proposals and
  a new unjudged merchant-query seed queue. No invented customer reviews.

## Build from the catalog repository

Working directory:
`/Users/matt/code/rocket-search/.worktrees/wands-merchandising`

```sh
python3 dev/tools/wands_catalog/catalog_depth.py \
  --source-products /Users/matt/code/rocket-search/data/raw/wands/product.csv \
  --prepared-products /Users/matt/code/mageos-latest/var/wands/products.csv \
  --merchandising-dir /Users/matt/code/mageos-latest/var/wands/merchandising \
  --realism-packet var/wands/realism-stock-explicit-v5 \
  --media-dir /Users/matt/code/mageos-latest/pub/media/import/wands \
  --benchmark-dir /Users/matt/code/rocket-search/data/prepared/wands \
  --synthetic-dimensions \
  --output-dir var/wands/depth-pilot-v9-synthetic-dimensions
```

Always choose a new output directory. The prepared packet, source/family inputs,
schema, implementation dependencies, reference bytes and original benchmark
files are hash-pinned. Inputs are checked again before publishing the local
packet. The command refuses existing output and changed packet lineage. Repeated
runs with identical inputs/code produce byte-identical packet files.

Normal output and runtime failures go to the sibling log, not the terminal:

```sh
tail -f var/wands/depth-pilot-v9-synthetic-dimensions.log
```

`--json` explicitly opts into terminal output. No background process, server
upload, scheduler or GPU run is started by the builder.

## Review packet

| File | Purpose |
| --- | --- |
| `review.html` | Local product cards, existing references, proposed facts, withheld evidence and recommendations |
| `products.jsonl`, `children.jsonl` | Root/child facts and unchanged identity records |
| `specifications.proposed.csv` | Review-only wide proposal, excluding synthetic dimensions; not authorized for direct import |
| `synthetic-dimensions.proposed.csv` | Separate long-format dimension proposal; every value carries its synthetic label, scope, rule version and evidence |
| `component-dimensions.proposed.csv` | Separate component-scoped measurements, quantities and inclusion evidence; never a set-wide EAV value |
| `dimension-exceptions.jsonl` | Exact root/child exceptions, including unsupported classes, incompatible options and kits requiring component dimensions |
| `dimension-repair-proposals.jsonl` | Non-executable repair queue grouped by root, with exact affected SKUs/counts, current options, source context and recommended resolution |
| `gallery-briefs.jsonl` | Non-executable briefs with reference hashes and explicit blockers |
| `recommendations.jsonl` | Alternatives and complementary candidates, not live product links |
| `collections.json` | Source-backed candidate sets and explicit price scope |
| `coverage.json` | Root and child denominators, missing/withheld evidence, gallery blockers |
| `benchmark-freeze.json` | Original query/judgment hashes and the prohibition on reusing old scores for changed content |
| `new-judgment-seeds.jsonl` | Unjudged product-name seeds, requiring merchant intent queries and fresh human judgments |
| `manifest.json` | Exact counts, provenance, output hashes and remaining release gates |

## Important evidence rules

Unitless `Width: 84` is unknown unless the original source title independently
states the same numeric value with an explicit unit and named dimension, such
as `84-inch wide`. A conflicting `Width: 90` keeps the whole attribute withheld.
No size, package weight, warranty, safety or certification is inferred from an
image. Unknown enum values are reported rather than forced into a nearby option.

Source measurements are withheld when a generated geometry axis varies them.
Material/finish changes also withhold affected construction and care facts.
Synthetic color/material/finish options remain labeled synthetic in the evidence.
The source ratings refer only to the original product, never generated child
products or supposed verified purchases.

### Approved synthetic dimensions

The September 9 approval covers local, explicitly synthetic dimension proposals.
The feature is off unless `--synthetic-dimensions` is supplied. It changes neither
sampling nor product identity, copy, price, stock, recommendations or benchmarks.

`synthetic_dimensions.py` has its own hash-pinned rule version and family seed.
Rule version 2 retains the version-1 seed, so expanding coverage does not
randomize previously prepared geometry. Explicit named-axis measurements in
new fixture/shed titles constrain the fictional exterior design, but remain
synthetic, never overwrite accepted source facts, and do not override generated
size/width options. Unitless numbers are still not interpreted as inches.
Color and finish changes preserve geometry. Numeric generated size options use
their explicit units, but remain synthetic because the options are generated.
Small/Medium/Large designs scale monotonically; furniture height changes less
than its footprint. Seat dimensions stay inside overall dimensions. Tile pack
counts do not multiply a tile's dimensions. Class-design bounds prevent an
implausible source measurement from being used to complete a fictional design.

Existing accepted source measurements and evidence are preserved verbatim. A
dimension conflict fails closed without replacing them. Bunk-frame exteriors,
stowed trundles, hanging daybed bodies and flat bed packages exclude mattress fit,
motion, rigging, load ratings and safety clearances. Misclassified options and
unresolved assortments retain explicit exceptions. Do not interpret a populated dimension as approval of the product's
name, option combination, reference image or real-world safety.

Bounded component rules cover named mortar/pestle pairs, two-piece shaker sets,
explicit bowl/lid counts, exact individual flatware roles, explicitly counted
shelf sets, source-confirmed chair/ottoman pairs and the explicit 15-piece bath
assortment. Each component has its own dimensions, quantity, disclosure and
inclusion evidence. Bowls and their lids share nominal diameters. A shelf-set
width option defines the largest shelf, not the installed span. A bath-set size
option applies only to its bath mat, not the shower curtain or every component.
Component quantities are source-grounded interpretations, not independently
verified manufacturer claims. Conflicting totals and unspecified roles fail
closed. A generic outdoor-set piece count never invents chairs or tables.

Configurable parents expose child ranges in review metadata. A single numeric
parent value is added only when every child has a complete design and the value
is common to all children. Partial coverage never becomes a parent scalar.
Dimension scopes distinguish a single tile from its pack, one panel from a window,
the primary comforter from a bedding set, and a fixture body from its suspension.
No mounting, capacity, load-rating or installation-clearance claims are added.
Component families show per-component child ranges in review metadata and retain
the full per-child evidence. They never become a single numeric set-wide size.

Every synthetic value carries this exact display label:
**Synthetic lab dimension, not a manufacturer measurement**.
Dimension-diagram briefs require it visibly on the diagram. Room briefs require
it in media metadata and never claim source-verified scale. All gallery jobs stay
non-executable until the selected product reference and geometry are reconciled.
Synthetic approval removes only the missing-dimension gate where a design exists.

Do not strip the provenance columns or combine the synthetic CSV with source
specifications for import. A future importer must persist a companion disclosure
attribute and render it beside synthetic measurements in Hyva, with rollback for
both the values and disclosure. That importer and live UI are not implemented or
authorized by this proposal. No new PHP attribute is needed for local review.
The component CSV additionally needs component-aware storage and rendering; it
must not be fed into a product-level attribute importer.

Missing specifications are blank in the review CSV, not delete instructions.
Before any future import, build sparse per-attribute updates, explicitly preserve
existing unknown fields, and validate the installed importer semantics. Do not
blindly pass this proposal into the old full-catalog import script.

The Magento patch adds only missing `lab_spec_*` definitions and refuses existing
storage-type conflicts before writing. It does not populate products or change
existing attributes. Numeric measurements are display/comparison fields, not
pretend numeric-range facets. Controlled select fields are filterable. Text
search is intentionally disabled for these new fields until a separately measured
search configuration change. The JSON schema must deploy with the PHP patch.

## Acceptance and next boundaries

1. Review `coverage.json` and `dimension-exceptions.jsonl`. Synthetic dimensions
   are approved for the local pilot, not source-verified. Unsupported class rules,
   conflicting options and component assortments remain explicit work items.
   Never rewrite source facts to fit incorrect images.
2. Approve the actual selected-variant references. Every gallery brief is
   non-executable and unapproved, including when an image file already exists.
   Room-scale and dimension briefs have additional evidence gates. Before any
   generation, convert only approved briefs into the existing audit-gated runner's
   job format and check its reference hashes. This packet is not that conversion.
3. Review every proposed related product and collection. Matching style does not
   prove installation compatibility, furniture clearance, size or palette fit.
4. Test the schema patch and sparse updates in an isolated remote clone. Reindex
   `catalog_product_attribute` and the affected search index after approved facet
   changes; verify the actual Hyva product page and layered navigation.
5. Take a fresh live snapshot, show exact affected records/fields, retain backup
   and inverse updates, then obtain deployment/import/media approval. No local
   Magento product import is part of this phase.
6. Freeze a new enriched-catalog evaluation only after merchant-authored queries
   and human judgments exist. The earlier 8.2% result does not certify this packet.

Purchasing simulation, live ratings UI, live collection pages and whole-catalog
expansion remain later phases. Existing inventory/price scenarios are inputs,
not altered by this builder.

## Local verification

```sh
python3 -m unittest discover -s dev/tools/wands_catalog/tests -p 'test_*.py' \
  > var/wands/depth-python-tests.log 2>&1
WANDS_MAGEOS_ROOT=/Users/matt/code/mageos-latest \
  /opt/homebrew/bin/php /Users/matt/code/mageos-latest/vendor/bin/phpunit \
  --no-configuration --no-progress --do-not-cache-result \
  --bootstrap dev/tools/wands_catalog/phpunit_bootstrap.php \
  app/code/RocketWeb/LabCatalog/Test/Unit/Setup/Patch/Data \
  > var/wands/depth-php-tests.log 2>&1
```

The PHP tests use Mage-OS's unit-test bootstrap for factory mocks, not its
application/database bootstrap. Generated test classes are isolated under this
repository's ignored `var/wands/phpunit/`, never the dependency installation's
compiled application cache. Composer autoload alone cannot reliably provide
generated factories on a fresh checkout. Set `WANDS_MAGEOS_ROOT` to a checkout
with unit-test dependencies installed; it defaults to this repository root.
PHP lint and mocked setup tests are not live schema/import acceptance.
