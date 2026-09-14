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
