# Catalog expansion completion

## Completed installation, 2026-10-06T18:17:45Z

The doubled catalog is installed and verified on the two existing destinations:
Studio and Comtom. Each now has **107,688 WANDS product records**: 103,643
simple products, 3,995 configurable parents and 50 bundles, with 27,736
configurable parent-child links. No third store was created and no products
were deleted. Required image generation, retained-image repairs and category
checks have finished.

Each store passed database acceptance, 15 unsaved cart-model checks and 28
rendered storefront checks. Original product IDs, existing stock, unrelated
products and protected store data were preserved. Search results were verified
nonempty; search ranking, checkout and payments are not qualified by these checks.

The accepted export contains 95,401 distinct JPEGs. Each store has 107,455
accepted media assignments and 322,365 verified image roles. There are 233
explicit disabled media exclusions: 213 reviewed quarantined products and 20
original disabled, imageless records. All 20 affected configurable families and
two affected bundles passed dependency checks. Measurements remain product
data only; the shared image policy prohibits visible measurements and text.

Private, ignored completion evidence is recorded in
`var/catalog-expansion-20260918/completion-authorized-20261004/completion-acceptance.json`.
It pins database, cart, browser and media acceptance evidence for both stores,
plus private backup and ordered inverse receipts. These artifacts contain
installation-specific data and are not shipped in Git. Image workers are stopped.

Source tooling and documentation can be committed independently of distribution.
The expanded media archive has not been published as a release asset. Existing
release downloads retain their original profile and counts. For remaining
testing coverage, see [the product coverage audit](PRODUCT-COVERAGE.md).

## Developer evidence and recovery

The certificate binds both installations to their exact accepted export and
database, cart, browser and media evidence. A saved certificate is a dated result;
refresh destination checks before making a claim about subsequent store changes.

See [the implementation guide](docs/EXPANSION.md) for the ledger, accepted-export
contract, importer boundaries and ordered rollback. See
[the preserved expansion history](docs/EXPANSION-HISTORY.md) for the full chronology.

[Documentation index](docs/README.md).
