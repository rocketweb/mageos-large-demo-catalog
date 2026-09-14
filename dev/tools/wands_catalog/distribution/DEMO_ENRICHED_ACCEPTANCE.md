# Existing demo enrichment acceptance

September 13, 2026, US Eastern. Target: `relevance.comtom.lab`, not the public
recipient fixture. Mage-OS 3.5.0 and Hyvä Default 1.5.2 were already installed.

## Catalog and media verified

- 55,044 products retained, including all 1,200 extra demo records.
- 342,859 description/specification field changes across 53,776 products.
- Twenty-two new specification attributes, including the synthetic-data notice.
- Exactly 65,375 related/cross-sell links, matching the full release profile.
- Four catalog module files added/updated. No other module's setup patches ran.
- Fourteen detail/room illustrations appended to seven existing galleries.
- All 71 gallery assertions passed, including hashes, labels, positions and
  unchanged hero roles and existing entries.

The final full-scope verifier reported zero remaining attribute discrepancies,
exact links and unchanged protected data. It compared every original media row,
excluding only the 14 separately verified new gallery IDs. Product identities,
types, prices, stock, URLs, configurable/bundle relationships and configuration
were preserved. All native indexes completed rebuilding successfully.

The first comparison caught native import stock side effects. Exactly 139 field
values in 90 rows were restored from the verified private backup with conflict
checks and a transaction. The entire stock table then matched its original hash.
Verification passed both after restoration and after reindexing. Failed and
successful receipts remain available; see the [operator recovery procedure](acceptance/DEMO_UPDATE.md).

The database/module backup and the later pre-gallery database backup remain
private on the server. Neither databases nor catalog images were added to Git.
The local suite passed 496 tests, including new backup-parser failure cases.

## Storefront observations

The live Traci rug page showed the new synthetic-specification disclosure and
dimensions. The original hero and both new detail/room images loaded. Its three
gallery slides were available, and the page fit a 390-pixel viewport without
horizontal overflow. The lab's private certificate required a session-local
browser exception in a separate daemon; system trust and other browser tasks
were not changed. No customer or order was created by these checks.

## Hybrid search remains unqualified after this update

Search configuration remains `mageos_opensearch_hybrid`; its active generation
was not replaced or forcibly activated. However, the bulk changes created a
large incremental queue. Store 2's readiness latch remained closed at the latest
check. An exact `kitchen pot` storefront request was observed in newly appended
route telemetry as `route=native`, `reason=readiness_closed`, with results shown.
Do not describe this as a verified hybrid search deployment or claim ranking gains.

The existing correctness, embedding and event workers were running without
container restarts. RabbitMQ had no dead-letter messages. Many unclaimed jobs
crossed the module's five-minute publication window and became `TIMED_OUT`.
The encoder also logged broken pipes; its document-client timeout was 30 seconds.
These observations do not by themselves prove one root cause for the backlog.

In a late five-minute snapshot, 16 embedding and 10 priority jobs completed for
store 2, while thousands remained unresolved. Native indexes and catalog data
were current, but hybrid freshness was not. Exact counts are volatile. No timeout,
batch-size, CPU, worker-count or generation changes were made in this catalog
update. A scoped hybrid recovery/performance pass and a final exact-route check
remain before calling the entire live workflow complete.
