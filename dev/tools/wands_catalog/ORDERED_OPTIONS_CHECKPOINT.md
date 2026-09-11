# Ordered configurable options checkpoint, 2026-09-11

Both remaining display defects from the [native Hyva pass](HYVA_OPTIONS_CHECKPOINT.md)
are resolved locally. Outdoor family `WANDS-030335` now displays **Furniture pieces**
in both the rendered label and embedded JSON, with options **4, 5, 6, 7 Pieces** in
ascending order. Lamp labels and Walnut/Oak/Espresso/Bronze ordering are unchanged.

The frontend plugin sorts cloned display options and the matching JSON options.
It does not renumber global EAV options, rename SKUs, change mappings or mutate
shared attribute objects. JSON output preserves script-safe escaping. The scope
remains exactly this outdoor SKU on website `wands`.

## Verified

- Regression tests failed on the original `4, 5, 7, 6` order and old JSON label,
  then passed after the fix. They also check unchanged source objects, non-target
  products/websites, prices, caption content and script-safe JSON encoding.
- The unchanged installed Hyva template rendered through native frontend discovery
  and newly generated isolated interceptors. The verifier accepts only the intended
  JSON label/order differences, not changes to prices, child IDs, SKUs, media URLs
  or other configuration fields.
- All eight selected-child prices and exact option bindings match native indexed
  prices. The complete 21-case unsaved guest-cart suite passes again.
- **411 Python tests pass**, and the modified PHP plugin passes syntax checking.
- All 105 local migration operations were reversed again. Seventeen product
  observations, price rows and all 117 original in-process table hashes match the
  indexed baseline. Four synthetic theme/currency tables remain unchanged. The
  fixture is restored; parity does not claim to restore auto-increment counters.

Runtime remains the observed Mage-OS **3.5.0**, Hyva **1.5.2**, PHP **8.4.24** and
MariaDB **11.4.12**. This is not a newly verified Mage-OS 3.4 installation.

## Current evidence

- `var/wands/hyva-options-control-v3.json`
- `var/wands/hyva-options-ordered-v1.json`
- `var/wands/hyva-options-verification-v3/result.json`
- `var/wands/storefront-cart-verification-v3/result.json`
- `var/wands/storefront-restored-v2.json`
- `var/wands/storefront-ordered-apply-v1.json` and its verified inverse marker
- `var/wands/option-order-tests-v1.log`

The previous caption-only acceptance remains historical. Its command requires the
previous code revision because evidence pins source hashes. Use this current command
from the merchandising worktree with a fresh output directory:

```sh
python3 dev/tools/wands_catalog/verify_hyva_options.py \
  --baseline var/wands/hyva-options-control-v3.json \
  --candidate var/wands/hyva-options-ordered-v1.json \
  --pricing var/wands/storefront-pricing-v3.json \
  --plan var/wands/definition-migration-v3/migration.json \
  --rollback-baseline var/wands/pricing-baseline-v2.json \
  --restored var/wands/storefront-restored-v2.json \
  --receipt var/wands/storefront-ordered-apply-v1.json \
  --output-dir var/wands/hyva-options-verification-new
```

Routine output stays in adjacent log files. All catalog images, generated classes,
native template output, fixtures and evidence remain outside Git.

## What still prevents a live-ready claim

1. Browser interactions: real option changes, live price updates, console errors,
   full page behavior and persisted-cart acceptance. Native HTML and unsaved models
   do not establish those results.
2. Deployment lifecycle: a production-capable migration adapter, timestamp/cache
   behavior and candidate module installation with freshly compiled interceptors.
   The guarded local runner intentionally cannot connect to the demo database.
3. Remote preflight: refresh the exact catalog/dependency scope and prepare verified
   database and old-media backups. An attempted collector update was denied by
   auto-review because that remote code upload lacked specific authorization; it
   was not retried. No new live theme capture is claimed.
4. Media stage: rehearse the native import for five reviewed product assignments,
   then verify actual gallery files and roles. The proposed five JPEGs total
   1,140,411 bytes. Existing media retirement needs its own explicit decision.
5. Approval and execution: present the exact code revision, dry-run counts and
   inverse evidence. Push, merge, deployment, live definition migration and media
   import remain separate states and are not performed by this pass.
