# Enriched catalog acceptance: proposed remote scope

Prepared September 13, 2026. No new instance, import or fixture mutation has run.
The new remote work below requires approval as a single acceptance batch.

## Current evidence

Read-only checks on `37.27.126.105` confirmed that the existing
`/opt/comtom/wands-lab35-acceptance` project is running. Its `lab_full` database
has 53,844 products, zero customers and zero orders. Composer records Mage-OS
3.5.0 and Hyvä Default 1.5.2. The web binding remains loopback-only on port 18035.
The retained empty database backup matches SHA-256
`29105d60d71a3f9ce4dc292b02b6d271f305594c6e1085bcc1c0506329bdc8cc`.

The server had about 776 GiB disk space and 63 GiB available memory at inspection.
Port 18036 had no listener. Recheck resources and all target collisions immediately
before provisioning. These observations are not a reservation or a load test.

## Proposed changes

- Create `/opt/comtom/wands-lab35-enriched` with Compose project
  `wands-lab35-enriched`, a dedicated network and separate PHP, database, search
  and nginx containers. Refuse an existing target or occupied port.
- Bind only `127.0.0.1:18036`. Do not change DNS, TLS, public proxy routes,
  `relevance.comtom.lab`, or the existing port-18035 acceptance project.
- Use Mage-OS 3.5.0, Hyvä Default 1.5.2 and stock OpenSearch 3.1.0 for comparison
  with the recorded baseline, not an unrequested dependency upgrade. Keep theme
  packages and credentials private on the same server, outside release assets.
- Cap aggregate container memory at about 11.2 GiB and run imports/tests serially.
  Do not add cron, a search benchmark load generator or GPU jobs.
- Import medium into a new `lab_enriched_medium` database. After its checks,
  test full in a separate `lab_enriched_full` database. Both are inside the new
  database container. Retain the existing lab's databases unchanged.

## Exact catalog scope

| Record | Medium | Full |
| --- | ---: | ---: |
| Products | 5,000 | 53,844 |
| Simple | 4,857 | 51,799 |
| Configurable parents | 93 | 1,995 |
| Bundles | 50 | 50 |
| Configurable links | 500 | 10,736 |
| Bundle options / selections | 200 / 600 | 200 / 600 |
| Distinct baseline images | 4,688 | 46,602 |
| New specification values | 14,848 | 205,527 |
| Related / complementary links | 884 / 117 | 54,482 / 10,893 |

These are logical records and relationships, not a promised SQL affected-row
count. Magento creates additional EAV, index, URL and inventory rows. Capture
actual before/after database counts in receipts.

Pinned manifests:

```text
medium 6e83c128538a3c0bf336c06c4135aa2b19ad01abcd8754d707e9bedc62f6ef68
full   9ad4b9ed1a65d6253db2119f61a11e20eb6e3e1cec55da5a8519fd43d157fe8c
gallery 8f0cb669b9bea8aea7aa616cdfc9509c0584755d09969fba404847fc13c20c2f
```

The gallery package adds 14 images to seven products. Test this separately after
the baseline full import, preserving existing hero roles and prior gallery entries.
Neither baseline catalog archive already includes those additional galleries.

## Execution and verification

1. Authenticate assets and tools, retain a remote environment receipt, create the
   isolated application/database/search volumes and a fresh empty baseline backup.
   Do not export any credentials or copy an existing populated database.
2. Run collision preflight before provisioning. Install the candidate's module,
   including its disclosure patch and Hyvä search layout. Import simple products,
   configurable parents, bundles and media in order. Run as the web filesystem
   owner, capture each exit code and keep terminal output in logs.
3. Run the full read-only `verify_profile.php` with `enrichment_checks.php` beside
   it. Require `enrichment_checked=true`, a positive enrichment-check count and
   no failures. Check attribute option provisioning, indexes and media hashes.
4. Verify actual Hyvä product/detail/filter/compare pages, synthetic notices,
   related products, variant price/image switching, bundle options, stock and
   search on desktop and mobile. These are functional checks, not ranking gains.
5. Exercise the independent commerce fixtures with a baseline restore between
   cases. The medium profile contains complete targets for 88 of 400 cases:
   seven each of active sale, expired sale, out-of-stock, backorder notification
   and tier pricing; three unavailable variants; all 50 unavailable bundle-option
   cases. Defer the other 312 to the full profile, not a partial scenario import.
6. The fixtures' reference clock is October 15, 2026. Use an application-local
   test clock or explicitly record equivalent date translations relative to the
   test store timezone. Never change the host clock. Tier prices require native
   Magento handling, and MSI reservations/stock must be checked at runtime.
7. Test the gallery append with a captured before-state, then verify image hashes,
   order, labels and unchanged hero roles in both storage and the browser.

Commerce JSON files are specifications, not an implemented universal scenario
runner. Runtime adapters and evidence must be built and checked within the new
fixture. Guest carts are allowed for acceptance; no customer account creation,
checkout, payment or order placement is included.

## Recovery and boundaries

Retain empty and post-import baselines with configuration and package hashes
inside the new private fixture. An interrupted import returns only its new test
database to the retained baseline before retrying. Preserve failure receipts.
Scenario recovery must restore data, stock/reservations and any application-local
clock configuration; verify the inverse rather than relying only on file receipts.

The whole-batch inverse is to stop only the new `wands-lab35-enriched` Compose
project while retaining its files and volumes. No old project needs rollback
because none is changed. Deleting any instance, pushing source, publishing assets
or deploying the enriched data to the demo is outside this batch.
