# MariaDB rehearsal checkpoint, 2026-09-11

The 105-operation pilot definition migration now passes a database-only rehearsal
on **MariaDB 11.4.12**, matching the observed demo database version. All loaded rows
across 33 actual-schema tables are restored by the inverse. This is not Magento
application, indexing, storefront or live-deployment acceptance.

## Evidence

- `var/wands/rehearsal-schema-v2/schema.json`: read-only source capture at
  `2026-09-11T18:49:21+00:00`, 33 table definitions, 973 rows and 48 foreign-key
  column references. Exactly seventeen product records; no customer, order, cart,
  credential or non-catalog configuration export. Triggers and routines are excluded.
- `var/wands/mariadb-rehearsal-v3/result.json`: ten passed database scenarios,
  exact plan/schema/runner/harness hashes and before/after/restored whole-table hashes.
- `var/wands/mariadb-rehearsal-v3/applied.json`: actual generated option ID and the
  105 before/after row records, with commit and rollback markers.
- Python suite: **388 tests pass**. The schema collector and MariaDB harness pass
  PHP syntax validation. Routine output remains in ignored log files.

The test creates a new database and never overwrites an existing one. Foreign-key
checks are disabled only while constructing the cyclic fixture, then re-enabled.
Every captured foreign key is checked for orphaned rows before the migration and
after rollback. Foreign keys remain enabled during forward and inverse operations.

The ten scenarios cover actual-schema loading, initial foreign-key integrity,
zero-write dry-run, interruption after operation 40, all 105 writes with constraints
enabled, duplicate-apply refusal, receipt tampering, an outside option consumer
blocking rollback, complete table-row restoration and duplicate-inverse refusal.
Auto-increment counters are not rewound. The earlier SQLite suite separately covers
expired-snapshot rollback and refusal to apply a stale plan.

## Issues found and corrected

The catalog table allowlist initially omitted Magento's `cataloginventory_` prefix.
The read-only capture stopped without exporting data. A regression test observed
that failure, then passed with the prefix allowed while customer/order/configuration
tables remained excluded.

The first real-engine fixture did not preserve admin store ID zero: ordinary
MariaDB auto-increment behavior assigned it a new ID. The foreign-key audit caught
the resulting orphan. The loader now enables `NO_AUTO_VALUE_ON_ZERO` and explicitly
asserts that store zero is `admin` before proceeding. A fresh database passed; the
failed database was not rewritten or silently reused.

The cached MariaDB 10.6 image was not used for acceptance. Its internal Docker
network also did not publish the requested localhost port. That unused test
container was stopped. The accepted rehearsal uses a dedicated bridge, with the
database published only at `127.0.0.1:13380`, and no live credentials.

## Local resources

- Container: `wands-definition-mariadb114-20260911`.
- Image: `mariadb:11.4.12`, digest
  `sha256:4f1d8d202fcf7bcb3902f63af09f9c1a050c2922a89652f22abaec0d4f015e83`.
- Network: `wands-definition-loopback-20260911`.
- Database: `wands_rehearsal_pilot_v3`, restored to its before-state.
- Database storage: disposable tmpfs, bounded to 1.5 GiB; container limited to
  2 GiB RAM and two CPUs. Evidence persists separately under ignored `var/wands`.

Docker Desktop was started after the user's continuation approval. Its configured
OpenCTI containers restarted automatically and were left alone. No pruning, removal
of user volumes or alteration of unrelated containers was performed.

The read-only collector ran in the relevance PHP container's isolated directory
`/tmp/wands-schema-rehearsal.jdx7Hi`. Only helper code and catalog evidence were written
there. No Magento application files, database rows or media assignments were changed.

## Application version and remaining gates

Read-only Composer lock inspection shows both the local `mageos-latest` checkout
and the current demo are **Mage-OS 3.5.0 with Hyva 1.5.2**, despite the original
3.4 request earlier in this task. This pass did not upgrade either installation.
Application verification must use the observed current runtime, not be reported as
a Mage-OS 3.4 test.

Next is an isolated application-level check using a separate root, configuration,
cache and database. The 33-table relational fixture alone is not a complete Magento
database; supporting application metadata and read-only acceptance checks are still
needed. Do not point the ordinary local checkout at this fixture or load its normal
environment credentials. A complete storefront/reindex check and a fresh live
preflight still precede the exact deployment approval gate.

No push, merge, deployment, image upload, Magento import or live catalog mutation
occurred. Catalog images, database snapshots, fixtures and receipts remain outside Git.
