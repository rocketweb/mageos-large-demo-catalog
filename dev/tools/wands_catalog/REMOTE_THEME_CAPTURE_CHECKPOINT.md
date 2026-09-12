# Approved remote theme capture, 2026-09-11

The approved read-only collector was uploaded to
`/tmp/wands-schema-rehearsal.jdx7Hi/snapshot_rehearsal_schema.php` inside
`farm-relevance-php-1` on `37.27.126.105`. It is a fresh temporary file; the prior
nested helper and all historical evidence were retained. The remote SHA-256 matches
the local collector:

`1484bb704217727660a85cdf7e6f78e58a029ffb5182fb37956e192f0744eafa`

The capture at **2026-09-11 20:50:12 UTC** contains 119 tables, 2,881 scoped rows
and exactly 17 products. All previously captured catalog rows and migration guards
still match. Store `wands` resolves to **Hyva/default, theme ID 5**, through its
explicit store assignment. These are captured theme registrations, not synthetic
IDs inferred from the local installation.

Only numeric `design/theme/theme_id` assignments for default scope, website 2 and
store 2 are exported. Theme-file contents, customer entities, orders, carts,
credentials and unrelated configuration remain excluded. The query transaction is
read-only and rolled back. Only helper/evidence files were written remotely; no
catalog records, galleries, modules or application settings changed.

The current snapshot passes `verify_storefront_capture.py`, which checks collector
and plan hashes, freshness, the unchanged catalog fixture and effective theme
assignment. The full Python suite passes **412 tests**. The refreshed capture also
passes all **10 MariaDB migration/failure/inverse scenarios**, including exact row
parity across all 119 tables after rollback. Its disposable local database is
`wands_rehearsal_theme_capture_v1`, restored to captured state.

## Evidence

- `var/wands/rehearsal-schema-storefront-v1/schema-storefront-v1.json`
- `var/wands/storefront-capture-verification-v1/result.json`
- `var/wands/mariadb-theme-capture-v1/result.json`
- `var/wands/storefront-capture-tests-v1.log`

The files remain ignored. The collector upload approval has been used only for the
stated temporary tooling and read-only capture. Push, merge, module deployment,
live definition migration, media upload/import and old-gallery retirement remain
separate actions. The next local pass can use the captured theme metadata for native
rendering and browser component checks without changing the demo.
