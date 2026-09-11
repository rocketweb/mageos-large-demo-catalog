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

Next: inspect the bulk structure against the demo, apply its reversible option,
relation and type changes, then run the native CSV importer. Preserve the old
gallery files. Associate the completed per-variant media, reindex, and verify full
product pages and representative configurable/bundle/search behavior. Commit each
completed code pass. Do not claim the demo is updated until live checks pass.

The generated CSV appends clearly synthetic dimensions to product descriptions,
without requiring a new specification-attribute deployment. It preserves the
approved Ocean Baby activation seed of 47 units at 74.99 base / 63.74 special.
Historical SKUs are retained; current option values determine presentation.

No scheduled continuation was created: the app rejected the heartbeat request.
The background generator is independent of that rejection. Do not claim automatic
future deployment or notification unless a continuation is actually available.
