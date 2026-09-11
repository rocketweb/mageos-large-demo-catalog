# Native Hyva options checkpoint, 2026-09-11

The unchanged installed Hyva 1.5.2 configurable template now renders **Furniture
pieces** for outdoor family `WANDS-030335`. The lamp family still renders **Finish**.
The shared EAV label remains **Piece Count**. All eight option IDs, child SKUs and
guest prices are verified against native indexed prices, with no database changes
during rendering. The 21 unsaved guest-cart cases pass again in this runtime.

## Fix and runtime correction

Hyva reads the shared EAV store label instead of the family super-attribute label.
The frontend-only `ConfigurableFamilyLabel` after-plugin clones the display
collection, its items and the affected attribute. It changes only the outdoor
family on website `wands`, without altering the database or shared cached objects.
The focused regression was observed failing with the original collection, then
passing with the clone-based fix. No vendor template was copied or modified.

This pass also found that earlier isolated roots could read precompiled classes
through the installed Composer loader's source `generated/code` fallback. The
application configuration and database were isolated, but generated code was not
fully isolated. The new loader removes source-generated paths from PSR mappings
and class maps, preserves installed library mappings, and loads generated classes
only from the fresh rehearsal root. Its regression exposed a macOS `/var` versus
`/private/var` path-alias case, which is now normalized.

This installation uses optimized interceptor generation. Late injection into the
plugin list does not recreate missing method hooks. The candidate is therefore
registered before Magento startup through a local fixture module, using the exact
candidate frontend XML and plugin class. Native frontend discovery, XML validation,
and isolated generated method paths are captured. This tests the candidate code,
not deployment or full module installation on the demo.

Sanitized Composer product metadata and four explicitly synthetic theme/currency
tables allow native template rendering without copying environment credentials.
They are not evidence of live theme assignments. The source checkout remains
untouched. No vendor runtime or generated class is added to Git.

## Evidence

- `var/wands/hyva-options-control-v2.json`: same isolated runtime, unpatched caption.
- `var/wands/hyva-options-discovery-v2.json`: native candidate render and class paths.
- `var/wands/hyva-options-verification-v2/result.json`: exact HTML/JSON bindings,
  prices, zero-write rendering, source-code hashes and rollback acceptance.
- `var/wands/storefront-cart-verification-v2/result.json`: 21 cart cases pass again.
- `var/wands/storefront-restored-v1.json`: native stock/price reindex after inverse.
- `var/wands/hyva-pass-tests-v2.log`: **410 Python tests pass**.

All 105 local migration operations were reversed using the pinned receipt. All 17
product observations, native price rows and 117 original in-process table hashes
match the indexed baseline. This includes the two session-scoped index working
tables; there are 115 original persistent tables. The four synthetic theme/currency
tables are retained unchanged as local fixture setup. Database
`wands_rehearsal_storefront_v1` is restored.

## Remaining gates

- Outdoor options currently retain native order `4, 5, 7, 6 Pieces`; improve the
  display order without renumbering global options or changing existing SKUs.
- The JSON attribute label still says `Piece Count`; only the visible HTML caption
  is corrected in this pass. Keep JSON and visible terminology consistent next.
- Real browser selection, selection-driven price updates, console errors and
  persisted-cart behavior remain unverified. These were PHP template and model
  checks, not full storefront/browser acceptance.
- Media upload, native media import and exact rendered image verification remain
  separate. Captured image URLs do not establish that any file was loaded.
- Push, merge, module deployment, live catalog migration and publication are not
  included. A further remote collector upload was denied by the approval reviewer;
  it was not retried. Continuing remote capture requires explicit authorization for
  that helper and destination. Local work used synthetic theme metadata instead.

## Repeat acceptance

Run from the merchandising worktree. Evidence is historical and hash-bound; fresh
runtime execution requires a new fixture root and receipt. Logs remain in files.

```sh
python3 dev/tools/wands_catalog/verify_hyva_options.py \
  --baseline var/wands/hyva-options-control-v2.json \
  --candidate var/wands/hyva-options-discovery-v2.json \
  --pricing var/wands/storefront-pricing-v2.json \
  --plan var/wands/definition-migration-v3/migration.json \
  --rollback-baseline var/wands/pricing-baseline-v2.json \
  --restored var/wands/storefront-restored-v1.json \
  --receipt var/wands/storefront-apply-v1.json \
  --output-dir var/wands/hyva-options-verification-new
```
