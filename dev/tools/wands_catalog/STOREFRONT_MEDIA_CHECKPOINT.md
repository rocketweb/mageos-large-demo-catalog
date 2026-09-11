# Storefront media checkpoint, 2026-09-11

The five-family pilot now has compact, locally reviewed storefront compositions,
20 raster exports and a five-product media assignment proposal. The remote preflight
is blocked by product-definition drift. Nothing has been imported or assigned live.
This checkpoint does not approve a push, deployment, product conversion or gallery
retirement. Catalog images and generated packets remain ignored, outside Git.

## Completed local passes

1. `build_storefront_compositions.py` repacks the 68 accepted physical pieces with
   uniform scaling, checked counts and no extra objects. All five SVG candidates
   received direct visual review, recorded in `storefront_composition_observations.json`.
2. `export_storefront_media.py` produces a 2000px PNG master, 2000px JPEG import
   original, 1200px WebP and 400px WebP for each family. All five JPEGs and thumbnails
   received direct visual review, recorded in `storefront_export_observations.json`.
   The export packet rebuilt byte for byte. A 2000px canvas is not a claim that every
   source component has native 2000px detail.
3. `plan_pilot_media_assignment.py` maps images to exact reviewed sale units and
   options. SKU text is not used as the source of option truth. Parents and other
   variants are held, not assigned the selected-option image automatically.
4. `preflight_pilot_media.py` compares a read-only remote snapshot with the proposal
   and prepares an exact upload plan, old-media backup inventory and review-only
   inverse SQL. It checks product types, definitions, relationships, configurable
   axes, option ownership, store overrides and existing galleries. It never imports.

The Python suite passes 381 tests. New guards were observed failing before their
implementation. The raster review loads all ten images at desktop and 390px mobile
width, has no horizontal overflow and reports no browser page errors. These are
local artifact checks, not live storefront acceptance.

## Exact proposed media scope

| Target SKU | Reviewed image | Proposed product type |
| --- | --- | --- |
| WANDS-000056 | Quilt, fitted sheet and unfolded valance | Simple |
| WANDS-003897 | Ten-piece bakeware assortment | Simple |
| WANDS-017842 | Forty-five-piece flatware assortment | Simple |
| WANDS-030335-3-PIECES-5B0E | Five furniture pieces and two included pillows | Simple child, 5 Pieces |
| WANDS-035295-BRONZE-D916 | Three coordinated Bronze lamps | Simple child, Bronze |

This is five products, fifteen image roles, fifteen labels and five import JPEGs
totaling 1,140,411 bytes. All three Magento image roles use the 2000px original;
the theme should generate its own image sizes. The proposal does not change names,
descriptions, types, prices, stock, categories, websites, relationships or bundles.

The snapshot includes thirteen context products: three standalone targets, two
configurable parents and eight children. Six sibling variants and both configurable
parents are read-only context. The nursery is proposed as standalone locally but
remains configurable remotely, so its full current dependency scope must be gathered
separately before planning any type conversion.

## Current remote findings

The snapshot captured at `2026-09-11T12:33:39+00:00` reads the relevance application
in `farm-relevance-php-1` on `37.27.126.105` through `comtom-public`. Its application
bind mount is `/opt/comtom/stores/relevance/src` to `/var/www/html`. All five target
products are assigned to website 2, `WANDS Relevance Lab`, with store view `wands`.
No target media store overrides were found. This is a dated snapshot, not a continuing
claim about server state.

Preflight findings:

- Fifteen definition differences: name, description and `lab_sale_unit` on each of
  the five targets. The reviewed images describe the corrected local definitions.
- `WANDS-000056` is still configurable; the reviewed local definition is simple.
- `WANDS-030335-3-PIECES-5B0E` still has the live option label `3 Pieces`; the reviewed
  local option is `5 Pieces`. The historical SKU will not be renamed implicitly.
- Five existing target gallery associations require inspection and a separate
  retirement decision. Their existence does not prove that each old image is wrong.
  An add/update import alone does not retire old gallery images.

The tool therefore exits 1 with `status=blocked`, while preserving the proposal,
field-level diff, old-media inventory and inverse SQL. It must not be bypassed to
assign a corrected image to an incompatible live definition.

## Current local artifacts

Paths below are relative to this repository root:

- `var/wands/storefront-compositions-v1/review.html`: compact square compositions.
- `var/wands/storefront-exports-v1/review.html`: current JPEG and thumbnail review.
- `var/wands/storefront-exports-v1/`: all twenty exported rasters and hashes.
- `var/wands/pilot-media-assignment-v2/media.review.csv`: exact five-row proposal.
- `var/wands/pilot-media-assignment-v2/snapshot-request.json`: current request.
- `var/wands/pilot-media-remote-snapshot-v1/`: private read-only catalog evidence.
- `var/wands/pilot-media-preflight-v2/preflight.json`: blocked result and field diff.
- `var/wands/pilot-media-preflight-v2/upload-plan.review.json`: five source files,
  hashes, sizes and exact staging destinations; not an executed upload.
- `var/wands/pilot-media-preflight-v2/binary-backup-required.json`: old gallery files
  requiring backup, not proof that those files were backed up.
- `var/wands/pilot-media-preflight-v2/rollback-media.review.sql`: five-product media
  inverse, ending in `ROLLBACK`, never executed.

Assignment v1 is superseded by v2 because the original snapshot request lacked the
required attribute list. Preflight v1 is superseded by v2, which adds option-owner
and axis checks and the exact upload plan. Historical packets remain unchanged.
The snapshot helper and its output are retained in the isolated container directory
`/tmp/wands-media-preflight.jOO2ip`, outside the application. No catalog data was
written. This evidence is not a complete database or binary-media backup.

## Ordered deployment gates

### 1. Resolve and approve product definitions separately

Prepare a fresh, narrowly scoped definition diff including existing nursery children,
parent links and any shared option-label consumers. Calculate the full affected-record
counts from that dependency-complete snapshot. Do not apply the older 667-record
definition packet merely to unblock this five-product media pilot. Keep the approved
synthetic definitions as the intended state; isolate the exact prerequisite changes,
backup, inverse and blast radius for approval. A type conversion or shared option
edit is not a media-only change.

### 2. Code deployment

Inspect the exact deployed importer revision and dependencies. The local planners do
not need to run on the storefront. If importer changes are necessary, review, test
and approve that code deployment separately. Do not replace the whole application
checkout, push a branch, merge or restart services from this packet.

### 3. Backup and clone rehearsal

After scope approval, back up the affected database state and the exact old binary
media, verify recoverability and freeze competing writes during application. Rehearse
the native importer and inverse on an isolated clone. Native `--validate-only` may
write import staging tables and is not a read-only live diagnostic. Record actual
Magento EAV paths, gallery rows and store inheritance after import, since Magento
can transform source paths. The proposed paths are not invented post-import evidence.

The media inverse restores only the five target products' six image/label attributes
and per-product gallery associations, including prior store scopes. It deliberately
does not delete shared gallery master rows or binary files. It is not a rollback for
product-definition changes, import staging tables, caches or indexers. Those require
their own scoped restoration and verification. Leave new unreferenced files in place
until cleanup is separately approved.

### 4. Media upload

Only after exact upload approval, check all five destination paths from
`upload-plan.review.json` before transferring to
`/opt/comtom/stores/relevance/src/pub/media/import/wands/pilot-media-v1/`.
Abort on different existing bytes, retain identical files and never overwrite or
delete unrelated files. Verify every destination SHA-256 against the local proposal.
Uploading originals is separate from assigning them to Magento products.

### 5. Data import

Refresh the snapshot and rebuild the preflight after the approved prerequisite
definition changes. Inspect any new difference and obtain approval for the exact
five-row media CSV, website/store scope and any separately enumerated gallery
retirements. Import only that reviewed CSV with the native add/update importer;
do not reconcile bundles or import the broader catalog. Capture the resulting
database diff and require zero unexpected product, option, price, inventory,
relationship or sibling-media changes.

### 6. Live storefront verification

After an approved import, verify the actual WANDS storefront, not just the files:

- All three standalone product pages show the intended sale unit and complete image.
- The outdoor parent selects the `5 Pieces` child with the five furniture pieces
  and two pillows; the lamp parent selects Bronze with the three-lamp image.
- Switch through the other six sibling variants and confirm their original images,
  selected SKU, option labels and prices remain unchanged. Parent media assignments
  must also remain unchanged unless separately approved.
- Check search/category thumbnails and full-size gallery images at desktop and
  mobile sizes, including image switching, alt labels, response status, rendered
  crops, missing images, old gallery conflicts and browser errors.
- Confirm stock and prices against the pre-import baseline. Any add-to-cart or
  checkout smoke test needs the approved test-session scope; do not place an order.
- Reindex or clear only the required caches through the approved deployment process.
  Preserve before/after evidence and prove recovery on the clone before declaring
  the rollback usable. Keep prepared, uploaded, imported and live-verified separate.

## Rebuild the read-only comparison

From the repository root, with a newly captured snapshot and a fresh output name:

```sh
python3 dev/tools/wands_catalog/preflight_pilot_media.py \
  --assignment var/wands/pilot-media-assignment-v2 \
  --snapshot var/wands/pilot-media-remote-snapshot-v1 \
  --exports var/wands/storefront-exports-v1 \
  --output-dir var/wands/pilot-media-preflight-new

tail -f var/wands/pilot-media-preflight-new.log
```

The default maximum snapshot age is 24 hours. The old snapshot above will eventually
be rejected and must be replaced, not accepted by disabling freshness checks.
Routine output is logged, not printed. Original WANDS judgments do not validate
these synthetic images, dimensions, variants or rewritten descriptions.
