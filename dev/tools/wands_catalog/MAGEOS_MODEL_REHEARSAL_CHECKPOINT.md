# Mage-OS model rehearsal checkpoint, 2026-09-11

The approved five-family migration passes actual Mage-OS product-model checks in
an isolated application root, including a complete forward/inverse cycle. This
advances the database-only checkpoint, not storefront or deployment acceptance.

## Verified

- Actual installed runtime: Mage-OS **3.5.0**, Hyva **1.5.2**, PHP **8.4.24** and
  MariaDB **11.4.12**. Read-only inspection found these versions on the demo/local
  installed code. Nothing was upgraded; this is not a Mage-OS 3.4 result.
- Expanded catalog-only fixture: **111 tables and 2,870 rows**. Ten MariaDB forward,
  failure and inverse scenarios pass with foreign keys enabled during migration.
- All **105 row operations** apply. All six copy fields on **13 active products**
  match the approved candidate records through complete store-2 product loads:
  name, description, short description, meta title, meta description and sale unit.
- Nursery loads as a simple product with no configurable children/options. Base
  price is **$74.99**, special price and native computed final price **$63.74**,
  weight **1.75**, legacy/default-source quantity **47**. Stock management is
  explicitly enabled, not inherited. These are model/row checks, not salability.
- The four old nursery child entities retain their original IDs and are disabled.
- Native configurable relationships expose the outdoor **4/5/6/7 Pieces** choices
  under **Furniture pieces** and all four lamp finishes under **Finish**.
- After rollback, a fresh application root reproduces the complete before-model
  projection, including copy, options, child identity/status and nursery stock.
- **396 Python tests pass**, including negative copy, option, stock, retained-ID
  and rollback-drift cases. The PHP helpers pass syntax validation.

The original configurable collection omits some EAV attributes. The probe now
fully loads each returned child before checking copy, while retaining the native
collection as evidence of the parent-child relationship. Earlier partial probes
are preserved but superseded by the complete evidence below.

## Isolation and evidence

`prepare_mageos_rehearsal.py` creates a fresh application root, reads only module
enablement from the installed configuration, and reuses installed vendor code.
It does not read the source environment credentials or copy system configuration.
The new root has its own generated code, file cache and file sessions. Its database
is restricted to localhost port 13380 and the `wands_rehearsal_` prefix.

The application schema capture includes EAV/store metadata, supporting catalog
structure and scoped stock/price-index rows. Customer/order/cart data and live
configuration values are excluded. Inventory shipment, order and pickup-quote
tables are explicitly excluded. Empty supporting schemas are not full live data.
The collector runs a read-only transaction without bootstrapping live Magento.

Current ignored evidence:

- `var/wands/rehearsal-schema-application-v7/schema-application-v7.json`
- `var/wands/mariadb-application-rehearsal-v5/result.json`
- `var/wands/mageos-complete-before-v1.json`
- `var/wands/mageos-complete-after-v1.json`
- `var/wands/mageos-complete-restored-v1.json`
- `var/wands/mageos-complete-apply-v1.json`, with committed and rolled-back markers
- `var/wands/mageos-model-verification-v1/result.json`, binding evidence hashes
- `var/wands/complete-suite-20260911-v2.log`

The database `wands_rehearsal_app_v5` is restored. The dedicated MariaDB container
remains running for subsequent isolated checks. No normal local application config
or unrelated Docker container was changed. Logs, snapshots and catalog media stay
outside Git.

## Remaining acceptance

Inventory-service salability, indexing lifecycle, actual Hyva rendering, selected
option pricing, add-to-cart and media import have not passed yet. Native parent
`getPrice()` returning zero is not a rendered configurable-price result. The fixture
does not copy all live configuration, rules, triggers or third-party integrations.
The database-only runner is still not a production Magento lifecycle adapter.

Before deployment, refresh the live snapshot, confirm the exact scope, prepare and
verify full database/media recovery, test lifecycle/cache/index effects, and obtain
approval for the exact tested revision and destination. Media upload/import remains
a separate five-product stage. No push, merge, deployment, image upload, native
Magento import, order or live catalog mutation occurred.

## Repeat the evidence verifier

From the merchandising worktree, choose a fresh output directory:

```sh
python3 dev/tools/wands_catalog/verify_mageos_rehearsal.py \
  --before var/wands/mageos-complete-before-v1.json \
  --after var/wands/mageos-complete-after-v1.json \
  --restored var/wands/mageos-complete-restored-v1.json \
  --candidates var/wands/pilot-definition-scope-v3/candidates.json \
  --receipt var/wands/mageos-complete-apply-v1.json \
  --plan var/wands/definition-migration-v3/migration.json \
  --database-result var/wands/mariadb-application-rehearsal-v5/result.json \
  --output-dir var/wands/mageos-model-verification-new
```

Routine output goes to the adjacent `.log` file. The JSON result explicitly keeps
storefront, salability and publication acceptance false.
