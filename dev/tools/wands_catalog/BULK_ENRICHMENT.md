# Bulk catalog enrichment

The September 12 bulk pass prepares new local candidates from the accepted rc2
catalog. It does not change the demo store, published assets or repository
visibility. Catalog IDs, URLs, prices, stock, configurable options and bundle
selections are preserved. This is a fresh-install candidate, not a live-update
CSV or a claim of resumable Magento import.

## Completed in this pass

| Output | Result |
| --- | ---: |
| Baseline product records retained | 53,844 |
| Enabled non-bundle records examined | 53,730 |
| Products with structured specifications | 49,763 |
| Specification values | 205,527 |
| Explicitly synthetic specification values | 111,870 |
| Products with merchandising links | 18,979 |
| Related-product links | 54,482 |
| Complementary-product links | 10,893 |
| Independent commerce fixtures | 400 |
| Unjudged search-query seeds | 500 |
| Medium-profile records | 5,000 |
| Accepted additional gallery images | 14, across 7 products |

The medium profile contains 4,857 simple products, 93 configurable parents and
all 50 bundles, with 500 configurable links and 600 bundle selections. All 5,000
products have media assignments, using 4,688 distinct images. Its four archives
are about 228 MiB. Profiles are alternatives for separate empty installations,
not successive imports into one database.

### Specifications

The builder normalizes the existing 21-field specification schema across the
current catalog. It retains 1,865 matching records from the corrected-definition
packet instead of rebuilding their definitions from conflicting raw WANDS text.
Child option values come from current configurable relationships, never from
historical tokens in SKUs. Source values retain evidence; synthetic values retain
their rule and disclosure. Unknown or conflicting values stay absent.

Numeric, controlled-option and care fields are written into a new full CSV set.
Descriptions include per-field synthetic labels. The new
`AddSpecificationDisclosure` patch adds a visible, comparable notice; the
`lab_spec_disclosure` value accompanies products containing synthetic facts.
Complete per-field and component provenance also travels inside the catalog
archive. Component dimensions are not flattened into a misleading set-wide size.

Not every product has a supported dimension design. The 23,201 records classified
as `needs_identity_or_component_review` retain available non-dimension facts and
explicit exceptions. This includes unsupported class profiles; it is not a claim
that 23,201 product definitions are broken. No measurements are manufactured to
fill every empty field. Likewise, partial-family ranges are not promoted to a
single parent value.

### Merchandising

Related products require the same product class, a compatible price band and
shared source-backed appearance evidence. Complements use explicit product-role
rules, such as sofas with accent pillows or lamps. Hidden children, disabled
products, self-links and adult/child-use mismatches are excluded. These are
synthetic merchandising choices, not physical compatibility or fit claims.

An indexed, bounded candidate pool keeps the full-catalog pass practical. The
medium profile retains full product dependencies and removes merchandising links
to products outside that profile.

### Commerce and search fixtures

The 400 commerce cases cover active and expired promotions, tier pricing,
out-of-stock products, notification backorders, unavailable configurable children
and required bundle options with no available selection. Each has its own fixed
clock, preconditions, exact changes, baseline inverse and expected result.

These are independent test specifications, not a combined import. Restore the
baseline between cases. No fixture has been applied to Magento in this pass;
MSI behavior, native tier-price import, taxes and cart calculations still need
runtime acceptance. No checkout qualification is implied.

The 500 search seeds combine real catalog attributes with product classes.
Their judgments are deliberately null. They are not an independent relevance
benchmark, and source-family partitions alone do not eliminate semantic overlap.
Review shopper intent, deduplicate and freeze a holdout, pool results from the
compared engines, and obtain fresh judgments before reporting ranking gains.

### Gallery results

Local MFLUX 0.19.1 generated 21 reference-based candidates with FLUX.2-klein-4B,
4-bit quantization, four steps and 768 × 768 output. Direct visual review kept
seven, excluded seven redundant views and requested seven targeted repairs.
All seven repairs passed the subsequent visual review. The resulting 14 images
give seven products one detail and one room view each.

The original heroes are unchanged. The new package contains a seven-row
additional-gallery CSV, per-image prompts, seeds, reference/output hashes,
model/runtime metadata and notices. No image was placed in Git. Room styling is
not included in the product; exact manufacturer appearance and scale are not
verified. The native gallery-append operation still needs isolated acceptance.

Two papasan-labeled chair references were excluded before generation because
they depicted conventional armchairs. This pass does not silently propagate or
claim to repair those original reference mismatches.

## Local artifacts and verification

All paths below are relative to the catalog repository root:

- `var/wands/bulk-enrichment-20260912-v2/`: full enrichment packet and data archive.
- `var/wands/bulk-enrichment-20260912-v2-repro/`: byte-identical second build.
- `var/wands/bulk-enrichment-v2-verification.json`: 4,052,138 passing data checks.
- `var/wands/lab-medium-enriched-20260912-v1/`: standalone medium candidate.
- `var/wands/lab-full-enriched-20260912-v1/`: standalone full candidate.
- `var/wands/gallery-package-20260912-v1/`: gallery archive and final HTML review.
- `var/wands/gallery-review-20260912-v1/`: first-pass accept/reject evidence.

Manifest SHA-256 pins:

```text
enrichment 10dbf3c4d4b25e680b152d683e4ca0b8d84ef6eafc4d02355a82a8aea7cc7d66
medium     6e83c128538a3c0bf336c06c4135aa2b19ad01abcd8754d707e9bedc62f6ef68
full       9ad4b9ed1a65d6253db2119f61a11e20eb6e3e1cec55da5a8519fd43d157fe8c
galleries  8f0cb669b9bea8aea7aa616cdfc9509c0584755d09969fba404847fc13c20c2f
```

The suite passed 475 tests with PHP checks and the local HTTPS fixture enabled.
The disclosure patch passed PHP lint and fixture tests for configuration,
idempotency and conflicting storage. The actual medium archive's controlled
options passed the PHP setup-option check. Medium, full and gallery archives
passed the standalone byte/member verifier. These are local data, packaging and
source checks, not a fresh Magento installation.

Full-profile media archives are hard-linked to the immutable baseline on the
same filesystem to avoid a second multi-gigabyte copy. Never modify archive
contents in place. Builders require new destination directories.

## Rebuild and verify

Run from the catalog repository root. Substitute your own source paths and new
output directories. Existing candidates cannot be overwritten.

```sh
python3 dev/tools/wands_catalog/bulk_enrichment.py \
  --release-dir var/wands/lab-release-20260911-full-rc2 \
  --manifest-sha256 9bf76000f3de8816459638ba2f396af805eaaa83c504886000e1b3c32adcf19d \
  --source /path/to/WANDS/product.csv \
  --definitions var/wands/catalog-definitions-v3 \
  --output var/wands/enrichment-new

shasum -a 256 var/wands/enrichment-new/manifest.json
```

Use the resulting pin with `verify_bulk_enrichment.py --baseline DIR --candidate
DIR --manifest-sha256 PIN --report NEW_REPORT.json`. Use
`build_medium_catalog.py --baseline DIR --enrichment DIR --enrichment-sha256 PIN
--repository "$PWD" --output NEW_DIR --release NEW_VERSION` for the medium
candidate; add `--profile full` for full packaging. Full packaging currently
requires baseline and output to be on the same filesystem for media hard links.

For a packaged profile, use the normal standalone verifier:

```sh
python3 dev/tools/wands_catalog/distribution/release.py \
  var/wands/lab-medium-enriched-20260912-v1 \
  --manifest-sha256 6e83c128538a3c0bf336c06c4135aa2b19ad01abcd8754d707e9bedc62f6ef68
```

Progress stays in adjacent `.log` files. The gallery worker writes `gallery.log`,
`generation-events.jsonl` and `status.json` in its run directory. Rerunning the
same job/audit/output command reuses hash-verified completed images. This does
not make Magento imports resumable. Both image workers finished in this pass;
no scheduled continuation or unattended deployment was created.

## Remaining release work

1. Import the new medium candidate into a separate empty Mage-OS 3.5 instance.
   Verify stored specification values, disclosure rendering, filters, comparisons,
   related products, bundle dependencies and original identifiers.
2. Exercise the commerce fixtures in that isolated instance and test the gallery
   append against an existing hero/gallery, with a before-state and inverse.
3. Extend GitHub download/profile publishing support for the medium candidate,
   rebuild the current recipient toolkit and publish only under new release IDs
   after approval. The existing rc2 assets remain unchanged.
4. Build independent search judgments and a measured comparison. Do not turn the
   generated seed queue into claimed ranking improvement.

Resumable live imports and a broad gallery rollout are not implemented here.
The current source and artifacts are local and uncommitted; no push, merge,
release publication or demo deployment is part of this pass.
