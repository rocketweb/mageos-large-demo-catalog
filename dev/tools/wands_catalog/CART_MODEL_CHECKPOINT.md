# Unsaved guest-cart checkpoint, 2026-09-11

All **21 native Magento cart-model cases** pass in the isolated fixture. Each uses
a new, unsaved guest quote. No quote, reservation or order is persisted, and every
fixture table has identical hashes before and after the tests.

## Coverage

- Three simple root products add successfully with the correct price.
- All eight configurable selections resolve to the exact expected child ID and
  SKU. Each produces one configurable parent line and one simple child line with
  the correct ID relationship. The parent carries the selected price; the child
  does not double-charge it.
- The two configurable parents reject both missing and invalid selections.
- All four retired nursery variants reject direct add-to-cart attempts.
- Nursery quantity 47 succeeds at $63.74 each and a native line total of $2,995.78.
  Quantity 48 fails specifically for insufficient inventory.

That is twelve accepted and nine rejected requests. The verifier checks the exact
business rejection messages and exception classes, so an infrastructure exception
cannot masquerade as a successful negative test. It also checks selected IDs,
quantities, line prices and line totals rather than just the acceptance flag.

## Evidence

- `var/wands/cart-cases-v2.json`: complete 21-case evidence with exact item IDs.
- `var/wands/cart-pricing-v2.json`: fresh, read-only native pricing evidence.
- `var/wands/cart-verification-v2/result.json`: hash-bound acceptance result.
- `var/wands/cart-pass-tests-v1.log`: **405 Python tests pass**.
- `var/wands/cart-apply-v1.json`: local migration receipt and rollback marker.
- `var/wands/cart-restored-v1.json`: native reindex after inverse.

The cart evidence must bind to a **fresh read-only price probe**, not the in-process
indexer's table listing. MariaDB exposes the indexer's two session-scoped working
tables while it runs; they disappear when that connection closes. The first strict
comparison correctly rejected the mismatched table sets. A new read-only pricing
probe gives exact parity without ignoring unexpected tables or weakening the
zero-write cart check.

The fixture uses the same 115-table, 2,873-row catalog/guest-metadata capture as the
pricing pass. No customer, cart or order rows, or even quote-table schemas, were
needed for these unsaved model checks. Runtime versions remain Mage-OS 3.5.0,
Hyva 1.5.2, PHP 8.4.24 and MariaDB 11.4.12.

The local migration was rolled back and native stock/price indexes rebuilt. The
restored model observations, price rows and indexed table hashes match the accepted
pricing baseline. Database `wands_rehearsal_cart_v1` is restored. Failed and partial
evidence remains ignored under `var/wands`; nothing was overwritten or published.

## Limits and next steps

These are native `Quote::addProduct` and line-price calculations, not a browser
shopping cart, address/tax/shipping totals, quote persistence, checkout or order
placement. The quotes use isolated USD defaults and guest group zero. Actual Hyva
rendered labels, selection-driven price updates and browser errors still need
verification, followed by the separate native media-import stage.

No push, merge, deployment, image upload, native catalog import or live catalog
mutation occurred. Existing local application configuration is untouched.

## Repeat verification

```sh
python3 dev/tools/wands_catalog/verify_cart_rehearsal.py \
  --evidence var/wands/cart-cases-v2.json \
  --pricing var/wands/cart-pricing-v2.json \
  --candidates var/wands/pilot-definition-scope-v3/candidates.json \
  --plan var/wands/definition-migration-v3/migration.json \
  --output-dir var/wands/cart-verification-new
```

Run from the merchandising worktree with a fresh output directory. Routine output
stays in the adjacent `.log` file. The result leaves browser storefront, checkout
and publication acceptance false.
