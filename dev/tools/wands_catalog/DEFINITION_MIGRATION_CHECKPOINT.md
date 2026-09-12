# Definition migration checkpoint, 2026-09-11

The user approved the five-family definition scope and the separate nursery
activation values after commit `65fb8e8`. The approved activation is a 47-unit
synthetic seed, $74.99 base price, $63.74 special price and weight 1.75 in the
store's existing unit. No stock is pooled or moved from the retained children.
This settles that decision; it does not approve deployment of an untested revision.

## Prepared

`prepare_definition_migration.py` produces **105 explicit row operations** from the
100-operation scoped proposal plus the five nursery activation rows. It verifies
the scoped snapshot and its hashes, rejects altered dependency counts, unexpected
stock sources, a changed 47-unit seed, price/weight store overrides and nonempty
special-price date values. The captured nursery has no special-date overrides;
its existing `has_options` and `required_options` flags are already zero.

The generated packet is `var/wands/definition-migration-v3/`. Its migration JSON
SHA-256 is `91cff3d0c405006285921e6f7e90d3499fb60a8e23e91def55ef840ebc121828`.
The packet manifest also pins the runner, builder and original scope evidence.
Earlier migration packets are historical; their runner hash pins no longer match
the current code. None is a deployable Magento CSV or a blanket write authorization.

`rehearse_definition_migration.php` defaults to dry-run. It accepts only a local
SQLite file named `rehearsal.sqlite`, or a loopback MySQL connection with a database
name beginning `wands_rehearsal_`. It does not read Magento production credentials
and cannot target the relevance database. The MySQL path requires InnoDB tables
and serializable transactions, but has not yet been exercised against MariaDB.

Before writes, the runner compares captured catalog, option, inventory, relation,
media, URL and attribute rows. It allocates the new option ID instead of guessing
one. The transaction checks each affected row and rejects unexpected changes within
the captured scopes. Existing entity timestamps are preserved in this database-only
rehearsal. A future production adapter must account explicitly for Magento lifecycle,
cache invalidation, timestamp and indexing behavior; this runner is not that adapter.

## Verified locally

The PHP runner passes syntax validation with the local PHP 8.4.24 binary. The full
Python suite passes 387 tests. A separate SQLite snapshot-fixture integration run
passes these ten scenarios:

1. Dry-run changes no database rows.
2. An injected interruption after operation 40 rolls back the transaction.
3. All 105 planned operations apply.
4. Reapplying against changed data is blocked without writes.
5. A changed receipt is rejected before rollback.
6. A new outside consumer of the created option blocks rollback.
7. The inverse restores all loaded fixture table rows exactly.
8. Repeating the inverse is blocked without writes.
9. Rollback remains possible after the original snapshot expires, provided the
   exact receipt and post-state still match.
10. A stale snapshot cannot authorize a new application.

The receipt-integrity and rollback-expiration regression cases were observed
failing before their fixes. The unit tests also cover preserving unrelated row
fields and rejecting changed nursery stock seeds or promotion-date overrides.

Current result: `var/wands/definition-rehearsal-v4/result.json`. It records plan,
runner and harness hashes. Fixtures, receipts and logs remain ignored, outside Git.
Parity refers to loaded table contents, not auto-increment counter restoration.
The SQLite fixtures do not reproduce the full MariaDB schema, foreign keys, triggers,
Magento services, plugins, indexers or storefront. No MariaDB or live acceptance
claim follows from these tests.

## Receipt and recovery behavior

The runner writes and fsyncs an exclusive receipt before committing, then creates
a commit marker binding the exact receipt hash. The inverse verifies the plan,
destination, receipt hash and post-state before reverting rows in reverse order.
It refuses to remove the new option if another product or extra label began using
it. The inverse includes restoring the absence of new sale-unit and special-price
rows, the prior nursery type, disabled-child statuses, relations, options and stock.

If interruption occurs between database commit and marker creation, the outcome
must be inspected manually. Missing markers are not proof that the transaction
did not commit. The runner deliberately refuses automatic replay or rollback from
an ambiguous receipt. Rollback does not expire with snapshot age; its protection
is exact current post-state and receipt validation.

## Remaining boundary

Docker Desktop was stopped when checked. Starting it could restart unrelated
containers, so the user was asked for startup approval. It was not started by this
pass. No remote containers, databases, media or catalog records were changed.

After Docker startup is approved:

1. Prepare a disposable, loopback-only MariaDB rehearsal using the actual schema
   and a catalog-only, dependency-complete fixture. Verify no connection points to
   the demo database. Re-run forward, failure and inverse tests with real constraints.
2. Prepare an isolated Mage-OS runtime using the tested adapter. Check the nursery's
   salability, price/promotion, weight, removed options and retained child records;
   verify all outdoor options and lamp finishes. Record actual storefront behavior.
3. Refresh the live read-only snapshot, verify unchanged scope, prepare the full
   database/media backup and inverse rehearsal evidence, and present the exact
   tested revision and counts for deployment approval.
4. Apply only after that deployment gate. Media upload/import remains its own
   five-product stage after the definitions are verified live.

No push, merge, deployment, image upload, Magento import, order or live catalog
mutation occurred in this pass.

## Re-run the local database-fixture test

From the worktree root, choose a fresh output directory:

```sh
python3 dev/tools/wands_catalog/test_definition_rehearsal.py \
  --plan var/wands/definition-migration-v3/migration.json \
  --output-dir var/wands/definition-rehearsal-new \
  --php /opt/homebrew/Cellar/php@8.4/8.4.24/bin/php
```

Routine runner output goes to receipt-specific `.log` files, not the terminal.
The result JSON states explicitly that MariaDB and storefront checks are pending.
Use a newly prepared packet once the 24-hour snapshot freshness window expires.
