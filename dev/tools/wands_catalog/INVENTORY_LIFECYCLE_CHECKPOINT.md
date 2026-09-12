# Inventory lifecycle checkpoint, 2026-09-11

The approved pilot migration now passes native Magento stock-index and inventory
service checks in the disposable fixture, including rollback. This follows the
[product-model rehearsal](MAGEOS_MODEL_REHEARSAL_CHECKPOINT.md). It is not a cart,
rendered Hyva storefront or live-deployment result.

## Important finding

Applying the 105 definition/activation operations alone leaves stale derived stock
data. In the observed fixture, the nursery's default-stock index still had quantity
zero. Magento's salable-quantity API returned **0**, even though general salability
and requested quantities **1** and **47** passed using other stock checks.

Calling the installed native partial stock indexer for exactly the seventeen scoped
product IDs resolved that inconsistency:

- Nursery salable quantity: **47**.
- Product-model and inventory-service salability: both **true**.
- Requested quantities **1** and **47**: accepted.
- Requested quantity **48**: rejected with the insufficient-quantity error.
- Four retired nursery children: still present and disabled; both salability checks
  return **false**, and their salable quantities return **0**.
- All seventeen products were observed without inventory-service exceptions.

Only `cataloginventory_stock_status` changed during the native partial reindex:
one nursery row changed from quantity 0 to 47, and four obsolete child index rows
were removed. Product entities, retained child stock quantities, source-item records
and unrelated fixture tables were unchanged. Those four derived index rows are
recreated by the native reindex after rollback; no product or source stock was deleted.

After the guarded inverse and another native partial stock reindex, all **112 fixture
tables** match their original row hashes. The stock index and all seventeen product
inventory-service observations also match their before-state. Auto-increment counters
are not rewound. This is stronger than checking only the migration's direct writes.

## Fixture correction and evidence

The first native-index attempt stopped because source-carrier metadata was absent
from the minimal fixture. A diagnostic rerun captured the nested exception and proved
zero changed database rows. The collector now includes the schema and scoped source
rows of `inventory_source_carrier_link`; no orders, shipments or customer data were
added. The scope regression test was observed failing before the allowlist fix.
The incomplete fixture was rolled back and preserved. Acceptance used a fresh one.

Accepted fixture: **112 actual-schema tables, 2,870 rows**, MariaDB **11.4.12**.
The ten database forward/failure/inverse tests pass again. Installed application
code remains Mage-OS **3.5.0**, Hyva **1.5.2** and PHP **8.4.24**. No upgrade occurred.
The Python suite passes **399 tests**.

Ignored evidence:

- `var/wands/rehearsal-schema-application-v8/schema-application-v8.json`
- `var/wands/mariadb-inventory-rehearsal-v2/result.json`
- `var/wands/inventory-before-v2.json`
- `var/wands/inventory-after-v2.json` (stale index, deliberately not acceptance)
- `var/wands/inventory-indexed-v3.json`
- `var/wands/inventory-restored-v2.json`
- `var/wands/inventory-apply-v2.json`, with committed and rolled-back markers
- `var/wands/inventory-lifecycle-verification-v1/result.json`
- `var/wands/complete-suite-20260911-v3.log`

`probe_mageos_inventory.php` refuses a non-loopback destination, any database outside
the rehearsal prefix, a changed approved plan hash or a fixture containing anything
other than the exact seventeen approved products. Its default mode does not reindex.
The explicit `--reindex` mode calls native `Stock::executeList`, never a full index.
Whole-table hashes detect unexpected writes, and failures retain diagnostic hashes.
This is a local test helper, not a production migration adapter.

## Required deployment sequencing

Any future live adapter must include the native stock-index lifecycle after both
forward migration and rollback. Merely updating source quantities, legacy stock
rows or indexer state is insufficient. The tested result does not justify manually
patching derived stock-index rows in production.

Still pending: full production-adapter lifecycle/timestamp/cache behavior, price
indexing and rendered configurable pricing, actual Hyva option selection and cart
checks, and native five-product media import. The local fixture uses isolated
configuration defaults plus captured per-product stock settings, not the complete
live configuration. No reservations, quotes, carts or orders were created.

Before a live update, refresh the read-only snapshot, verify the exact affected
scope and recoverable database/media backups, and obtain deployment approval for
the tested revision and destination. Keep media upload/import as a separate stage.
No push, merge, deployment, image upload, native import or live catalog write occurred.
Both accepted fixture databases are restored. The dedicated local MariaDB container
remains running for follow-on checks; unrelated containers remain untouched.

## Repeat verification

From the merchandising worktree, choose a fresh output directory:

```sh
python3 dev/tools/wands_catalog/verify_inventory_lifecycle.py \
  --before var/wands/inventory-before-v2.json \
  --stale var/wands/inventory-after-v2.json \
  --indexed var/wands/inventory-indexed-v3.json \
  --restored var/wands/inventory-restored-v2.json \
  --receipt var/wands/inventory-apply-v2.json \
  --plan var/wands/definition-migration-v3/migration.json \
  --output-dir var/wands/inventory-lifecycle-verification-new
```

Routine output stays in the adjacent `.log` file. The result hash-binds evidence,
plan, receipt and helper code while explicitly leaving cart, storefront and
publication acceptance false.
