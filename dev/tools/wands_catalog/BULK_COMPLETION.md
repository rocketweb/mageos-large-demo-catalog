# Bulk test-catalog completion

Matt delegated the remaining synthetic product and image decisions on September
11, 2026. Complete this as bulk test data, not another series of per-product
approval gates. Retain practical backups and batch checks. Public community
publication, purchases, unrelated infrastructure and NetSuite remain out of scope.

## Current batch

- `var/wands/bulk-completion-v1`: 603 product updates and 64 retained, disabled
  children, totaling 667 existing SKUs. Five configurable roots become simple.
- 93 corrected media families have 424 specific product/variant views: five
  reviewed assortments reused and 419 new local FLUX images.
- `var/wands/bulk-completion-images-v1`: resumable image run. Check `status.json`,
  `events.jsonl` and `bulk.log`. The single-instance lock prevents duplicate runs.
  Image outputs are ignored and never belong in Git.
- `var/wands/bulk-native-import-v1`: native CSVs for 505 simple updates, 98 parent
  updates and 64 disabled children, plus the structure and snapshot request.
- `var/wands/bulk-demo-before-v1`: actual read-only demo before-state captured at
  2026-09-11T21:46:32Z. All 667 SKUs exist. Remote private staging is
  `/tmp/wands-bulk-completion-20260911` inside `farm-relevance-php-1` on comtom.

The demo has `RocketWeb_LabCatalog=1` and `MageOS_NetSuiteConnector=0`. The local
clone's NetSuite failure is not a reason to add or modify NetSuite on the demo.
The earlier isolated native-media probe remains diagnostic, not successful import
evidence. Its unsuccessful validation attempts made no database changes.

## Execution

Resume the current generator without changing its code or packet while it runs:

```sh
/Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/run_bulk_completion_images.py \
  --packet var/wands/bulk-completion-v1 \
  --run-dir var/wands/bulk-completion-images-v1 --background
```

All output goes to `bulk.log`; do not launch again while the lock is held.
The image run is generation, not visual acceptance or live publication. Use batch
review and bounded repairs for obvious identity/count/option mistakes. Do not
regenerate the five accepted assortments.

## Applied to the demo on September 11, 2026

The bulk correction is live, not just a local MageBox rehearsal:

- 505 simple-product updates, 98 configurable-parent updates, 64 obsolete children
  disabled and detached. Five corrected roots are now simple products.
- All 667 affected SKUs passed 10,643 field checks and 3,335 stock checks against
  the intended updates or their unchanged before-state. The corrected scope has
  exactly 494 parent/child links and 160 configurable axes.
- The whole WANDS catalog contains 51,799 simple records, 1,995 configurables and
  50 bundles with 600 selections. Disabled records are included in those counts.
  No broken bundle selections, empty bundle options or orphan configurables.
- 424 final image files assigned to 507 products, including parent heroes.
  All 1,521 base/small/thumbnail roles matched the uploaded SHA-256 hashes.
  507 original gallery views and five superseded table views were hidden, not
  deleted. All original image files remain recoverable.
- All five affected stock/EAV/inventory/price/search indexes rebuilt successfully.
  Browser checks covered the converted Ocean Baby simple product, configurable
  selection/image/price changes, bundle price recalculation, mobile layout and
  searches for `picnic table` and `nursery decor`.
- Python suite: 427 passing tests. PHP structure tests cover dry-run, application,
  exact inverse, bundle-consumer guard and ID-preserving axis reconciliation.

Final local media packet: `var/wands/bulk-media-import-v4`. Images, review pages,
generated CSVs and logs remain ignored by Git. The image generator completed
419 initial images, one 83-image repair pass and four clean picnic-table images;
five previously accepted assortments were reused. Final images are synthetic lab
illustrations, not exact component-count or geometry certifications. Some complex
assortments and shapes remain approximate; structured product definitions are
authoritative. Do not describe this as exhaustive visual accuracy verification.

### Native importer findings

Use `bulk-native-import-v3`, not the original v1 CSVs. Preserve existing URL keys
even for media-only rows. Update parent content using `parent-content-only.csv`;
the native configurable import tried to replace primary IDs referenced by label
rows. `reconcile_bulk_axes.php` updates labels/positions while preserving IDs.

The native importer converted 570 explicit empty special prices into zero.
`clear_bulk_special_prices.php` preflighted and cleared only those scoped values.
Final verification confirms no such price differences remain. Do not treat zero
as equivalent to an absent special price in the verification code.

### Recovery and evidence

Remote receipts and scoped snapshots remain inside `farm-relevance-php-1` at
`/tmp/wands-bulk-completion-20260911`. Server-side verification results are in
`/tmp/wands-bulk-verify-20260911`; post-import catalog snapshots were verified in
place, not downloaded to the Mac. Native CSV logs are under the application's
`var/wands/bulk-completion-20260911` directory.

The complete pre-import database backup remains only on comtom at
`/opt/comtom/backups/wands-bulk-20260911-2156/database-v2.sql`, 307,286,926 bytes,
SHA-256 `757d5a98264b42a248f6208bd361f4816f4febff1c31c0334f8de315c7cb56bb`.
The earlier `database.sql` attempt is empty, not a usable backup. Scoped journals
retain deleted relationship/label rows, prior price values and gallery flags.
A full database restore is a fallback requiring separate approval, not a tested
automatic whole-batch inverse after later imports.

An unrelated existing ShoppingFeed template emits a RequireJS initializer on the
Hyvä simple-product page (`mageosShoppingFeedAutoSelectSimple`, `require` undefined).
It was identified but not changed in this catalog pass. No NetSuite changes,
package upgrades, public publication, push or merge were performed.

The generated CSV appends clearly synthetic dimensions to product descriptions,
without requiring a new specification-attribute deployment. It preserves the
approved Ocean Baby activation seed of 47 units at 74.99 base / 63.74 special.
Historical SKUs are retained; current option values determine presentation.

No scheduled continuation was created: the app rejected the heartbeat request.
The background generator is independent of that rejection. Do not claim automatic
future deployment or notification unless a continuation is actually available.
