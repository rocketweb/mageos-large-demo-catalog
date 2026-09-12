# Catalog publication preparation

This tooling prepares and validates release artifacts. It does not authorize a
commit, push, deployment, data import, media upload or rollback execution.
The existing bulk image process must retain its current scripts, inputs and
run directory. These readiness tools run separately and do not request GPU work.

## Current local findings

The replacement `var/wands/realism-stock-explicit-v5` packet passed the independent full-file
check: 53,794 product updates, including 2,000 configurable parents, 10,800
children and 40,994 standalone simple products. The 50 bundles contain 200
options and 600 selections. Total unique target SKUs: **53,844**.

The replacement report has zero errors and zero warnings. All 50 bundle rows set
`manage_stock=0` and `use_config_manage_stock=0`, so their derived salability no
longer changes with the remote global stock-management setting. The earlier
`realism-full-v4` packet remains frozen and must not be imported.

The local installed `module-bundle-import-export/Model/Import/Product/Type/Bundle.php`
add/update path uses `populateExistingOptions()` and matches options by title;
it does not remove old options/selections absent from the incoming file. The
revised bundle CSV therefore uses the module's atomic `--reconcile-bundles` import
path. It locks only the listed WANDS bundle parents, reports exact old option,
selection, price and relation counts, removes their existing assortment, and runs
the validated import in the same transaction. A failed import rolls back cleanup.
Switching to whole-product replace/delete is not an acceptable shortcut.

## 1. Reproduce full artifact validation

From `/Users/matt/code/rocket-search/.worktrees/wands-merchandising`:

```sh
python3 dev/tools/wands_catalog/release_readiness.py \
  --packet var/wands/realism-stock-explicit-v5 \
  --output-dir var/wands/release-readiness-v5-resolved
```

Use a fresh output directory on each run. Normal output/errors go to the sibling
`.log`. The tool verifies every frozen packet/input hash before loading data.
It checks required copy/metadata, finite positive prices, clearance prices,
stock/backorder flags, complete family combinations, child option values,
type/URL identity, simple-only bundle links, required groups, defaults and stock.

Outputs:

- `validation.json`: exact entity/option/selection counts and findings.
- `snapshot-request.json`: exact SKU, expected type, configurable-link/axis and
  variant-option scope for remote preflight. No credentials are present.
- `storefront-cases.json`: expected results for 2,000 configurable families, all
  50 bundles, and three simple-product stock scenarios. These are **not run**.

## 2. Read-only remote snapshot and local diff

Resolve the actual application root and container on `37.27.126.105` before
running anything. The intended storefront is `relevance.comtom.lab`, not the
pilot store and not a local Magento installation. No remote snapshot has been
taken by this preparation work.

After authorization for the exact snapshot/transport operation, copy the snapshot
script and request to an approved private path on that environment. Execute the
script in its PHP runtime, replacing the uppercase path placeholders:

```sh
php dev/tools/wands_catalog/snapshot_catalog.php \
  --root=ABSOLUTE_MAGENTO_ROOT \
  --request=ABSOLUTE_PRIVATE_PATH/snapshot-request.json \
  --output-dir=ABSOLUTE_PRIVATE_PATH/catalog-before
```

The output parent directory must already exist. `snapshot_catalog.php` reads only
the configured Mage-OS database, checks `SELECT DATABASE()` and the expected base
URL, schema-qualifies queries, and starts a repeatable-read, read-only transaction.
It reads credentials from that installation's `app/etc/env.php` without outputting
them. It does not bootstrap Magento or write products, configuration or import
staging tables. It writes a new private snapshot directory and sibling log only.
Exceptions fail closed; a directory without a completed `manifest.json` is unusable.

Snapshot scope includes exact selected products, EAV values at every store scope,
attribute metadata/assignments/options, legacy stock, MSI source items if installed,
configurable links/axes, bundle rows, product relations, website/category membership,
media association rows and relevant store configuration. It does not query orders,
customers, reservations, payment information or unrelated configuration secrets.

The snapshot is **not** a full database or binary-media backup. It is evidence for
the narrowly scoped diff and inverse. Capture a separate complete recoverable backup
before any approved write, including catalog media files and the deployed code SHA.

Transfer the snapshot back through the approved private channel, then prepare:

```sh
python3 dev/tools/wands_catalog/snapshot_preflight.py \
  --packet var/wands/realism-stock-explicit-v5 \
  --request var/wands/release-readiness-v5-resolved/snapshot-request.json \
  --snapshot var/wands/catalog-before \
  --output-dir var/wands/remote-preflight-v1
```

This validates request/packet/destination identity, freshness (24 hours maximum
by default), table completeness, row counts and every snapshot file hash. Use a
fresh snapshot immediately before writes; a 24-hour limit does not protect against
intervening changes. Freeze catalog writes or compare a new snapshot before apply.

Outputs:

- `preflight.json`: exact found/missing target SKUs, changed product/field counts,
  old/new bundle counts, snapshot row counts, inverse row counts, and blockers.
- `field-diff.jsonl`: exact prior/proposed scalar and stock values.
- `bundle-diff.jsonl`: old option/selection IDs and proposed assortments.
- `rollback.review.sql`: inverse EAV values, changed legacy-stock fields, default
  MSI source items, bundle options/selections and bundle-owned product relations.
- `rollback-media.review.sql`: media EAV fields and per-product gallery links/values.
  It leaves shared gallery master rows and new files intact.

Both SQL files are **review-only and deliberately end with `ROLLBACK`**. Neither
tool executes them. They preserve missing/null attribute values as well as values
that existed, and qualify every table with the snapshot database/prefix. They do
not disable foreign keys. Rehearse against a clone using a snapshot of that clone;
do not run production-qualified SQL through a connection to a different database.

The inverses are not yet runtime-validated. Verify default-source import behavior,
existing promotions/special-date bounds, inherited settings, store overrides,
category/website/tax-class invariance and media-table behavior in the clone.
Non-default inventory sources need an explicitly reviewed extension if the import
would change them. Code/schema rollback and binary-media recovery use the full
backup and the separately recorded prior code artifact, not these SQL files.

## 3. Storefront acceptance

Use the generated cases to drive a later authorized browser session. Resolve the
base URL, store code, URL suffix, currency, tax display, guest/customer group and
active price rules first. Product `url_key` is not a complete route until the real
suffix and store configuration are known. The baseline case prices are synthetic
USD, before tax, without additional promotions. Do not report a price defect until
those runtime assumptions are reconciled.

Start with representatives from every configurable axis/product group and every
bundle theme, then cover the full case inventory. Capture screenshot, URL and
console evidence on failures. Never place an order, use payment details, change
admin configuration or import data as part of these checks.

| Surface | Required observation |
| --- | --- |
| Configurable PDP | Correct axes/options and child identity; selection updates price and image; stock disables the right combinations; starting price reconciles to selectable children |
| Bundle PDP | Exactly four intended groups with no obsolete options; only intended selections; salable defaults; changing selections produces the component subtotal; set counts in the hero image are correct |
| Stock | In-stock, low-stock and unavailable simple products; unavailable combinations cannot be added; derived parent/bundle state is correct |
| Search/category | Exact parent/bundle/simple SKU finds the intended product; hidden variants stay individually hidden; correct price, stock, image and product link on result/category cards |
| Media | No missing/404 images, successful gallery loading, correct variant color/material/size, every bundle component present, no duplicated or omitted set pieces |
| Content/runtime | New copy/specifications and collection label; no raw HTML leakage, exception page, console error or broken option interaction |

Record observations in a copy of `observations.example.json`, outside Git. Leave
unrun cases absent. Each case uses `sku`, `http_status`, `name`, `in_stock`,
`console_errors`, `exception_visible`, `broken_images`, `product_images_loaded`,
`visual_acceptance`, `exact_sku_search_results`, and `evidence_paths`.

For configurables, add `axis_codes`, `starting_price`, and a `variants` array with
`sku`, `options`, `can_add_to_cart`, `displayed_price`, `image_matches_options`.
For bundles, add `default_subtotal`, `alternative_total_verified`, and `options`
with `label`, `required`, and `selections` containing `sku`, `enabled`,
`displayed_price`. For simple products add `displayed_price`, `can_add_to_cart`.
Use JSON booleans, not strings. Evidence files must come from real browser checks;
the comparator checks recorded facts, not the browser independently.

```sh
python3 dev/tools/wands_catalog/check_storefront_observations.py \
  --cases var/wands/release-readiness-v5-resolved/storefront-cases.json \
  --observations var/wands/storefront-observations.json \
  --output var/wands/storefront-acceptance.json
```

Missing cases remain `not_run`; missing runtime context remains blocked. A partially
observed suite cannot return a complete pass. Search/category visual layout, actual
selected-image fidelity and screenshots still require browser judgment, not just
numeric assertions. Avoid cart mutation unless that separate check is authorized.

## 4. CPU-only image repair preparation

```sh
python3 dev/tools/wands_catalog/prepare_audit_repairs.py \
  --run-dir var/wands/bulk-realism-v3 \
  --source-products /Users/matt/code/rocket-search/data/raw/wands/product.csv \
  --output-dir var/wands/repair-drafts-readiness-v1
```

The tool takes a frozen byte-prefix copy of the active audit log, tolerating only
an incomplete trailing record. It matches the current model/policy/reference hash
and rechecks source-evidence hashes. It sorts drafts by affected-job count and tags
likely count, geometry, finish or material issues. Prompts retain source facts and
flag multiple values for review. Model observations are not authority to change the
catalog. No oMLX request, MFLUX load, image generation or mutation of the active job
occurs. Refresh into a new directory as more audit results arrive.

At the first capture, 61 failed/uncertain references affected 292 image jobs;
21 drafts had multiple source values to review. These are capture-time counts,
not a live counter. Drafts require review before becoming a generation plan.

## 5. Deployment checklist and rollback boundaries

### Code deployment

- [ ] Record exact approved commit SHAs, target host/store and rollout window.
- [ ] Commit/push/merge are separate actions requiring their own authorization.
- [ ] Confirm all active image workers use unchanged input/code hashes.
- [ ] Rehearse the new attribute patch, compilation and configuration in a clone.
- [ ] Record the previous code artifact and compatibility-preserving rollback.
- [ ] Approve and deploy code only; do not implicitly import data or upload media.

### Data import

- [ ] Obtain fresh remote evidence, complete DB backup, and exact dry-run counts.
- [ ] Resolve missing/incorrect types, attribute assignments, variant options,
  and special-date/promotion findings. Confirm the explicit bundle stock values.
- [ ] Prove old bundle options and selections will be removed only for the 50
  approved bundle parents, with old rows/relations recoverable from the snapshot.
- [ ] Run `lab:wands:import --validate-only` in the clone. This does not change
  products but native validation can write import staging/history data; it is not
  the read-only snapshot step and must not race another importer.
- [ ] For each bundle batch, run `lab:wands:import --validate-only
  --reconcile-bundles` and compare its exact would-remove counts with the snapshot.
- [ ] Approve the exact scalar/stock diff and bundle reconciliation scope.
- [ ] Import each validated bundle batch with `lab:wands:import --reconcile-bundles`.
  Retain its exact removed-record counts, checkpoints and post-import invariants.
  Never use whole-product delete/replace to clean up bundle options.
- [ ] Reindex and compare resulting attributes, stock, links and bundle rows to
  the expected packet. Stop on any mismatch; do not proceed to media automatically.

### Media upload and association

- [ ] Finish required repairs and explicit output-image acceptance.
- [ ] Freeze the accepted SKU/file/image-hash manifest; generated does not mean accepted.
- [ ] Use a new release-specific import subdirectory and preserve original files.
- [ ] Capture fresh pre-media associations and ensure old binary files are backed up.
- [ ] Approve upload and association separately from the data import.
- [ ] Upload accepted files only, verify checksums, then import exact media mappings.
- [ ] Verify gallery links, image responses and expected hero/variant/set content.

### Verification and rollback

- [ ] Run the case-driven storefront session and retain actual browser evidence.
- [ ] Confirm correct remote SHA, product counts, search/index behavior, stock,
  option selection, bundle totals, media and absence of frontend/runtime errors.
- [ ] If rollback is needed, obtain approval for the exact inverse and compare
  current state to the checkpoint. Freeze competing writes before applying it.
- [ ] Rehearse and verify inverse row counts in a clone. Both generated inverse
  SQL files end with `ROLLBACK`; changing that boundary requires explicit approval.
- [ ] Restore only affected data/media associations, then reindex and re-test.
  Leave new unreferenced files for separately approved cleanup.
- [ ] Record code deployed, data imported, media associated, live verified and
  user accepted as separate states. Publication is not complete merely because
  image generation or the importer exited successfully.
