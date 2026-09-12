# Native media rehearsal stage, 2026-09-11

The five reviewed import JPEGs are now staged in a private, hash-locked packet for
the next disposable Mage-OS importer rehearsal. No importer has been executed and
no files were uploaded to the demo.

## Exact staged scope

| Target | Reviewed image |
| --- | --- |
| WANDS-000056 | Three-piece nursery assortment |
| WANDS-003897 | Ten-piece bakeware assortment |
| WANDS-017842 | Forty-five-piece flatware assortment |
| WANDS-030335-3-PIECES-5B0E | Corrected 5 Pieces outdoor variant |
| WANDS-035295-BRONZE-D916 | Bronze three-lamp assortment |

Five JPEGs total **1,140,411 bytes**, with fifteen image roles and fifteen labels.
The existing historical child SKU is retained; it is not interpreted as the sale
unit count. No configurable parent or unreviewed sibling receives a selected-option
image. The packet contains only the eight approved media CSV columns and default
store scope. Tests reject price columns, path escapes, parent targets and divergent
image roles.

The current snapshot contains five old gallery associations and five old gallery
files for these targets. Their metadata is inventoried, but binary backups are not
claimed. Existing gallery images must be preserved unless retirement is separately
approved.

## Artifacts and verification

- `var/wands/native-media-stage-v1/staging-root/pub/media/import/wands/pilot-media-v1/`
- `var/wands/native-media-stage-v1/staging-root/var/wands/media.review.csv`
- `var/wands/native-media-stage-v1/old-media-backup-required.json`
- `var/wands/native-media-stage-v1/scope.json`
- `var/wands/native-media-stage-v1/manifest.json`

Each staged image is checked against its reviewed source hash and byte count. The
CSV must match the pinned assignment rows exactly. The package also binds to the
accepted native definition/rollback evidence and refreshed read-only remote snapshot.
It does not assert that the corrected definitions are live. The full Python suite
passes **416 tests**.

Two fresh builds, `native-media-stage-v1` and `native-media-stage-v2`, produce
identical manifests and output hashes. All staged JPEGs, CSVs and snapshots remain
ignored under `var/wands`; catalog images are not added to Git.

## Important importer boundary

The installed `ProductImporter` calls `Import::validateSource()` before returning
from its validate-only branch. Native `AbstractEntity::_saveValidatedBunches()` calls
`Import\Data::saveBunch()`, which writes `importexport_importdata`. Therefore
**validate-only is not a read-only database operation**. It must not be used as an
unapproved live preflight.

The next pass should create a fresh disposable application/database fixture with
the required import staging schemas, apply the verified definition migration, and
validate/import these five rows there. Record exact catalog, staging-table and file
changes, preserve old gallery associations, verify all fifteen roles and labels,
then rehearse the full data/media inverse. The current definition-only rollback
proof is not a media-import rollback proof.

No push, merge, deployment, native media validation/import, remote image upload,
gallery deletion or live catalog mutation occurred in this pass.

```sh
python3 dev/tools/wands_catalog/prepare_native_media_rehearsal.py \
  --assignment var/wands/pilot-media-assignment-v2 \
  --exports var/wands/storefront-exports-v1 \
  --snapshot var/wands/rehearsal-schema-storefront-v1/schema-storefront-v1.json \
  --definition-acceptance var/wands/theme-browser-native-verification-v1/result.json \
  --output-dir var/wands/native-media-stage-new
```

Run from the merchandising worktree. This prepares files only and logs to the
adjacent `.log` file. The resulting staging directory is not a Magento installation.
