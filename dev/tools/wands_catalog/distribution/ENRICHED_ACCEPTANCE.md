# Enriched catalog acceptance

This is an internal, isolated Mage-OS 3.5.0 acceptance run, not official Mage-OS
certification. It does not update the public download or the demo store.

## Environment and boundaries

The approved September 13, 2026 batch uses a new `wands-lab35-enriched` Compose
project, with Hyvä Default 1.5.2 and stock OpenSearch 3.1.0. Its web endpoint binds
only to loopback port 18036. Medium and full use separate, freshly initialized
databases. The existing acceptance project and demo store are not import targets.

Application code was copied on the same server from the pinned installation,
excluding credentials, runtime directories, media and populated databases.
Composer lock SHA-256:

```text
8674885f1a076ed4f875d729cd7cf45ad54c474240a73bc15f208d6b9f8e4e7d
```

The new project retains its empty baseline, post-import backups, stage logs and
individual scenario before-states privately. No database dump or theme package
belongs in a release asset.

## Import correction and candidate identity

The first medium run exposed a native importer behavior mismatch. The module
used `add_update`, but Mage-OS's product-link processor preserves existing links
only for `append`. The media phase consequently removed merchandising links.
The module now uses native append behavior. A fifth CSV phase imports links after
all simple, configurable and bundle targets exist.

The failed medium receipt and pre-repair database remain available. Reimporting
the final link phase with the corrected module restored all 1,001 expected links.
The complete medium verifier then passed, including after commerce scenarios.

The original September 12 v1 archives remain unchanged. The September 13 v2
profiles differ only in the corrected `ProductImporter.php` and the new
`data/5-merchandising.csv`. Existing catalog CSVs and media bytes are unchanged.
Runtime acceptance uses that corrected module and final-link workflow. It is not
acceptance of an unmodified v1 module.

| Profile | v2 manifest SHA-256 |
| --- | --- |
| Medium | `93256f50f6a1e5070eab18dee3e28b2b348b5e92aba0fa35e3a5b22cb4aaa07a` |
| Full | `b525ca0441e7f04858613fdcba4d8e3ae18421240f4c25a757bf34fa5587951b` |

## Recorded results

| Check | Medium | Full |
| --- | ---: | ---: |
| Products | 5,000 | 53,844 |
| Configurable parents | 93 | 1,995 |
| Bundles | 50 | 50 |
| Configurable links | 500 | 10,736 |
| Bundle options / selections | 200 / 600 | 200 / 600 |
| Specification values | 14,848 | 205,527 |
| Related / complementary links | 884 / 117 | 54,482 / 10,893 |
| Total verifier assertions | 194,287 | 2,064,675 |
| Included enrichment assertions | 133,637 | 1,448,621 |
| Discrepancies | 0 | 0 |
| Eligible commerce cases passed | 88 | 400 |

Complete catalog verification passed both before and after the commerce cases.
The final full comparison reads the v2 package's staged CSVs. All 26 module files
match the installed module for each profile. The final-link CSVs match the tested
phases: 673 medium rows and 18,979 full rows. Rows can contain several links.

Six medium and 68 full source URL keys required the same normalization Magento
applies during import; the verifier uses Magento's native URL formatter, not a
blanket exception. All 11 full-profile indexes are Ready with no backlog after
the gallery work.

## Scope of commerce evidence

The 400 independent fixtures cover active and expired sales, out-of-stock products,
backorder notifications, tier pricing, unavailable configurable children and
unavailable required bundle options. The adapter uses native product/stock APIs,
reindexes affected records and restores each case before continuing.

Sale windows are translated to equivalent windows around the store's current
date; the October 15 reference date remains in receipts. The host clock is not
changed. Tier prices respect Magento's configured global or website price scope.
The full adapter checks MSI source items and reservations before and after each
case, together with the order count. All 3,680 assertions passed across the 400
full cases: 60 each of active sale, expired sale, out-of-stock, backorder and tier
pricing; 50 each of unavailable variant and required bundle-option availability.

The full pilot caught Magento's `SetSpecialPriceStartDate` observer changing an
originally null start date when saving an existing sale price. The test runner
stopped. The original value was recovered and verified from the before-state.
Restoration now captures all price/date fields even for tier-price cases and uses
the native product attribute resource to restore exact EAV values after product
save observers. Both the failed attempt and successful recovery remain recorded.

Quantity totals are the native final unit price multiplied by quantity. They are
not checkout, tax, shipping, saved-quote or payment tests. A tier-price assertion
does not establish that the baseline stock permits purchasing that quantity.
No customer accounts or orders were created. A separate browser check added the
White/Metal chair to a guest cart at $167.99, verified its selected options and
subtotal, then removed it. One empty guest quote remains; there are zero quote
items and zero MSI reservations. Checkout and order placement were not exercised.

## Gallery acceptance

All 71 assertions passed for 14 additional images on seven products: exact hashes,
individual captions, enabled entries, appended positions, unchanged prior entries
and unchanged base/small/thumbnail roles.

The first append exposed a CSV enclosure issue: native `FIELDS_ENCLOSURE` parsing
requires each caption to be quoted inside its CSV cell. The exporter now does so.
The original append and failed label receipt were retained; a native import of
the corrected CSV repaired the 14 labels without adding duplicate images.

The corrected gallery package retains all original image and provenance bytes:

```text
2026.09.13-gallery-v2
6c1f924b8e9f1e2048f48d0426a3e0e9de885b4e2cc004058a45fa3c08e60ce5
```

This evidence covers the original append followed by corrected-caption import,
not an assertion that an unmodified v1 package passed every check. Galleries
remain separate from both baseline profiles.

## Storefront checks

The installed full-profile storefront was exercised through its private tunnel,
using Hyvä's actual controls and links:

- `lamp` search retains Relevance sorting and specification filters. Selecting
  E26 returns the five advertised products.
- WANDS-000030 renders its specification disclosure and three related bookcases.
  The header's `/catalog/product_compare/index/` link renders the product's
  structured values and synthetic notice in the comparison table.
- WANDS-000251 White/Metal displays $167.99 and its matching variant image.
  Its guest-cart options and $167.99 subtotal agree with the source CSV.
- WANDS-BUNDLE-001 changes from $1,496.46 to $1,716.46 when the seating selection
  changes from Abida to Gatun, matching the $220 difference between components.
- WANDS-000007 shows Out of stock and no Add to Cart control.
- WANDS-000082 retains its original hero and exposes detail and room slides with
  their separate synthetic captions. The settled mobile room view was visually
  inspected; the displayed caption says styling is not included.
- The bundle and gallery pages fit a 390-pixel mobile viewport without horizontal
  overflow. Checked visible images load, and the browser session reports no
  JavaScript errors. Hidden Hyvä placeholder images are not broken-image failures.

The local suite passed 489 tests with native PHP checks and the loopback HTTPS
fixture enabled. These sampled browser checks are not an exhaustive visual
review of all 53,844 products.

## Remaining boundaries

The existing acceptance fixture still has 53,844 products, zero customers, zero
orders and its original Composer lock hash. No changes were applied to the demo
store. These are private acceptance results, not a push, publication or deployment.

Search checks establish functional behavior only. No ranking improvement is
inferred from synthetic specifications or generated relevance seeds. Existing
store updates, resumable Magento imports and a broad gallery rollout remain
outside this fresh-install acceptance.
