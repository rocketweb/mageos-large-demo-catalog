# Existing demo enrichment update

Internal operator procedure, not the public fresh-install path. Exact target:
`farm-relevance-php-1`, `/opt/comtom/stores/relevance/src`, database `magento`.
The operator scripts refuse a different target. This preserves the demo's 1,200
extra products and hybrid search instead of replacing it with a stock-search lab.

The September 13 dry run proposed 342,859 attribute changes across 53,776 products
and 65,375 related/cross-sell links. Only descriptions and `lab_spec_*` columns
appear in the attribute CSV. Prices, stock, product types, URLs and hero images
are outside its scope. There were no existing merchandising links or specification
attributes. Twenty-two specification attributes are added by two named patches.
The native importer file is updated to the tested append behavior. Three other
files are new. No other module's setup patches are run.

`demo_scope.php plan` captures exact canonical-table hashes and writes a pinned
attribute CSV. `demo_update.py` makes a private full database backup and copies
the existing module before applying anything. Its verification compares all
desired values/links and the protected table hashes. Native `updated_at` import
bookkeeping and rebuilt index tables are not treated as immutable catalog data.
All stages log to the private update directory and stop on a nonzero exit.

## Inverse operation

Only use this inverse for this exact update, after checking the saved backup
hash and confirming no later customer/order or catalog changes would be lost.
The preflight observed zero customers and zero orders. Keep the original backup
and logs. Do not run this against another installation or reuse the command for
a later deployment.

From the server:

```sh
cd /opt/comtom/stores/relevance/catalog-enriched-20260913-v2
sha256sum --check backup-sha256.txt && \
  docker exec -i --user www-data farm-relevance-php-1 \
  php var/catalog-enriched-20260913-v2/demo_database.php restore \
  < /opt/comtom/stores/relevance/catalog-enriched-20260913-v2/before.sql
```

Restore the saved `module-before/Model/Catalog/ProductImporter.php` to its exact
original path and owner. The three newly added files may remain unused; the
database restore removes their patch-history entries and attributes. Reindex and
clean this store's caches, then verify its original protected hashes, product
population, search engine and storefront. A database backup does not roll back
search indexes, uploaded image files or other later external changes.

Do not remove original media. The optional gallery update is a separate phase
with its own before-state and verification. A failed verification is not a
completed deployment.

## Recorded stock-side-effect recovery

The native imports changed 139 fields in 90 stock rows: 49 `is_in_stock` flags,
50 `stock_status_changed_auto` flags and 40 `low_stock_date` values. The original
quantities and all other protected tables matched. The updater stopped.

`extract_demo_stock.py` reads only the stock table from the exact hash-pinned
private SQL backup. It accepts numeric/date/null stock literals, including the
actual multiline dump format, and rejects arbitrary SQL expressions, duplicates,
wrong counts and truncated statements. Unrelated binary dump bytes are preserved
by byte-compatible decoding, not interpreted as stock data.

`restore_demo_stock.php` requires the inspected 90-row/139-field scope, locks and
checks each current value against the recorded after-state, restores only those
fields in a transaction, and requires the entire stock-table hash to match the
original plan before committing. This restoration passed. The explicit
`--finish-after-stock-restoration` continuation preserved the failed receipt,
repeated canonical verification, reindexed and verified again successfully.

The separate gallery phase passed 71 checks for 14 additions. The final whole-
catalog comparison excludes only those 14 independently verified new gallery IDs
from the original-row hashes; every original media row must still match. It also
requires exact descriptions/specifications and all 65,375 links, with prices,
stock, relationships, configuration and the extra products preserved.
