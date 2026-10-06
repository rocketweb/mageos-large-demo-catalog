# Product coverage audit

The expansion is complete for scale and images, but product-behavior coverage
is incomplete. Three core types are missing: virtual, downloadable and grouped.
The proposed next step is a small, named QA collection rather than another large
generation run. No proposed fixtures below have been implemented.

Audited October 6, 2026 against the accepted expansion CSVs and completed
installation acceptance for the two existing lab stores. Counts below describe
WANDS catalog records, excluding unrelated products already in those stores.

[Documentation index](docs/README.md) · [Expansion implementation](docs/EXPANSION.md)

## Core types

| Product type | Records | Coverage |
| --- | ---: | --- |
| Simple | 103,643 | Standalone physical products and configurable children |
| Configurable | 3,995 | One or two variation attributes |
| Bundle | 50 | Dynamic price, SKU and weight; shipment together |
| Virtual | 0 | Missing |
| Downloadable | 0 | Missing |
| Grouped | 0 | Missing |

Virtual products cover services and other products without shipping. Downloadable
products add files, samples, link selection and download permissions. Grouped
products let customers order associated products with independent quantities.
These behaviors need dedicated fixtures; catalog size does not establish coverage.
See Adobe's [virtual](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/types/product-create-virtual),
[downloadable](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/types/product-create-downloadable)
and [grouped](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/types/product-create-grouped)
product documentation.

## Configuration gaps

All 50 bundles use dynamic pricing, dynamic SKU and weight, price-range display
and shipment together. Their 600 selection entries are required dropdown
selections with customer quantity changes disabled. Fixed pricing, separate
shipment, optional options, other selection controls and editable quantities
are not represented. Configurable products have at most two variation attributes.

The accepted product CSVs contain no custom options, tier/group prices, upsell
links, scheduled special-price dates, or explicit quantity increments. Related
and cross-sell links, special prices and out-of-stock rows are present.
Backorders are disabled in the stock rows. All products use Taxable Goods.
Existing store stock was preserved during installation, so export stock values
are not a claim about every current live quantity or inherited setting.

## Proposed QA collection, not implemented

Add approximately 100 to 150 clearly named `WANDS-QA-` records, with exact
fixtures and expected outcomes selected from the matrix below. Count parent and
child records separately. Reuse suitable approved physical images and create
small local test files for downloadable products. Keep the fixtures identifiable
by SKU and category so test suites can address them reliably.

| Area | Fixtures to add or explicitly verify |
| --- | --- |
| Virtual | Assembly service, design consultation; taxable and non-taxable; standalone and associated service; physical, virtual and mixed carts |
| Downloadable | Local PDF/ZIP, sample, single and multiple links, selectable links, finite/unlimited downloads and sharing settings; verify access before and after the qualifying order status |
| Grouped | Independently priced entryway or desk items; zero/default quantities, unavailable associated items and association order |
| Configurable | Three attributes, sparse combinations, unavailable and disabled children, variant prices/images and supported virtual children |
| Bundle | Fixed and dynamic price/SKU/weight, shipment together/separately, required/optional options, dropdown/radio/checkbox/multiselect, editable quantities; physical, virtual and mixed components |
| Custom options | Field, area, file, dropdown, radio, checkbox, multiselect, date, date/time and time; required/optional and fixed/percentage charges |
| Pricing | Tier/customer-group pricing, dated special prices, zero price, upsells, tax classes and applicable price-rule outcomes |
| Inventory | In stock/out of stock, backorders, minimum/maximum quantities, increments, decimal quantities and multi-source availability |
| Visibility and scope | Each visibility mode, enabled/disabled products, store-view text, website assignment and scoped price/stock behavior |

The bundle and custom-option variations follow Adobe's
[bundle documentation](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/types/product-create-bundle)
and [customizable options documentation](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/settings/settings-advanced-custom-options).
Individual combinations must be valid for the installed platform; the matrix
does not imply every setting can be combined with every product type.

Inventory sources, tax rules, customer groups, currencies, websites, price rules,
download access, checkout and payments also require store configuration and
behavioral tests. Product records alone cannot qualify them. Test order and
download flows with disposable accounts and explicit state cleanup.

Gift cards, subscriptions and Commerce/B2B features depend on the installed
edition or extensions. Include them only in a separately identified extension
suite. They are not additional default Mage-OS product types.

The expansion is complete for the approved scale and image scope. This audit
identifies a separate coverage extension; none of the proposed fixtures have
been imported or deployed.
