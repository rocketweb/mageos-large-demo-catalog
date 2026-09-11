# Guest price-index lifecycle checkpoint, 2026-09-11

Native stock and price indexing now pass in the isolated five-family fixture.
All thirteen active product price rows agree with Magento pricing models, and the
inverse plus the same indexers restores the indexed baseline exactly.

## Verified results

| Product family | Base / regular price | Final price or option range |
| --- | --- | --- |
| Nursery | $74.99 | $63.74 |
| Bakeware | $79.99 | $79.99 |
| Flatware | $109.99 | $109.99 |
| Outdoor | Existing parent base $174.99 | $134.99 to $209.99 across four children |
| Lamps | $109.99 | $109.99 for each finish |

The outdoor parent base-price column is not its minimum selectable price. The
verifier checks native final-price resolution against the child minimum, and the
indexed min/max range against all four child final prices. It does not mistakenly
equate the parent base-price column with the displayed configurable minimum.

Only the nursery's approved price/promotion changes. Prices and special prices for
all other sixteen products are compared with the captured runtime baseline, not
silently replaced by different prices in older local catalog drafts.

The partial indexers run for exactly seventeen product IDs. The fixture produces
seventeen guest/WANDS price rows before migration, thirteen afterward, and seventeen
after rollback. The four retired child entities and original source quantities
remain intact; disabled children are not present in the active price index.

## Evidence and isolation

- Runtime: Mage-OS 3.5.0, Hyva 1.5.2, PHP 8.4.24, MariaDB 11.4.12. No upgrade.
- Source fixture: 115 table schemas and 2,873 rows. The collector adds only the
  guest group zero, group exclusion metadata, tax-class metadata, and scoped fixed
  product tax rows. No customer, quote, order or credential data is exported.
- The initial fixture lacked `weee_tax`. Native index creation succeeded, but
  configurable pricing API calls raised missing-table errors. The failed evidence
  was retained. Acceptance uses a fresh dependency-complete fixture; no module was
  disabled or pricing behavior mocked to make the checks pass.
- Native indexing creates two additional working tables. Whole-table row hashes
  after rollback match the **indexed baseline**, including those working tables.
  This differs deliberately from the raw, not-yet-indexed capture. Auto-increment
  counters and complete production configuration are not part of that claim.
- The ten database forward/failure/inverse scenarios pass again. **403 Python
  tests pass**, including guest-scope exclusion, index-only mutation boundaries,
  parent-range and stale-promotion regressions. PHP helpers pass syntax validation.

Current ignored evidence:

- `var/wands/rehearsal-schema-pricing-v2/schema-pricing-v2.json`
- `var/wands/mariadb-pricing-rehearsal-v2/result.json`
- `var/wands/pricing-baseline-v2.json`
- `var/wands/pricing-updated-v1.json`
- `var/wands/pricing-restored-v1.json`
- `var/wands/pricing-apply-v1.json`, with committed and rolled-back markers
- `var/wands/pricing-lifecycle-verification-v1/result.json`
- `var/wands/pricing-pass-tests-v2.log`

The pricing verifier pins the exact probe, shared runtime helper, plan, receipt,
candidate scope and all three observed states. Database `wands_rehearsal_pricing_v2`
is restored to its indexed baseline. Existing normal local configuration and the
live application remain unchanged. Routine output goes to ignored log files.

## Remaining gates

This verifies guest USD pricing under isolated defaults and captured product/rule
price rows. It is not acceptance for customer-specific groups, taxes at a shipping
address, rendered Hyva price updates, a browser cart or checkout. Native cart-model
and storefront option checks are next, followed by the separate five-product media
stage and the full live lifecycle/backup/deployment approval gate.

No push, merge, deployment, image upload, native Magento import, quote, reservation,
order or live catalog mutation occurred in this pass.

## Repeat verifier

```sh
python3 dev/tools/wands_catalog/verify_pricing_lifecycle.py \
  --before var/wands/pricing-baseline-v2.json \
  --after var/wands/pricing-updated-v1.json \
  --restored var/wands/pricing-restored-v1.json \
  --candidates var/wands/pilot-definition-scope-v3/candidates.json \
  --receipt var/wands/pricing-apply-v1.json \
  --plan var/wands/definition-migration-v3/migration.json \
  --output-dir var/wands/pricing-lifecycle-verification-new
```

Run from the merchandising worktree with a fresh output directory. The result
explicitly leaves storefront, cart and publication acceptance false.
