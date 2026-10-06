# Product coverage audit

The two existing lab stores now contain **107,815 WANDS records and all six core
product types**. The [127-product QA suite](QA-CATALOG.md) adds named fixtures for
virtual, downloadable, grouped, configuration, custom-option, pricing, inventory
and visibility behavior. Scale and product coverage are separate test surfaces.

Counts below exclude unrelated products already in each store. The original
107,688-record expansion and September downloads contain only simple, configurable
and bundle products. The October stable full release includes the QA extension
as phase 6 and covers all six types.

[Documentation index](docs/README.md) · [Expansion implementation](docs/EXPANSION.md)

## Core types

| Product type | Records | Coverage |
| --- | ---: | --- |
| Simple | 103,720 | Physical products, children, options, pricing and inventory fixtures |
| Configurable | 4,001 | Up to three axes, sparse combinations and virtual children |
| Bundle | 62 | Fixed/dynamic price, four control types and physical/virtual components |
| Virtual | 14 | Services and configurable children |
| Downloadable | 12 | PDF/ZIP links, previews, selection, sharing and limit settings |
| Grouped | 6 | Physical, virtual and downloadable associations |

Virtual products cover services and other products without shipping. Downloadable
products add files, samples, link selection and download permissions. Grouped
products let customers order associated products with independent quantities.
These behaviors need dedicated fixtures; catalog size does not establish coverage.
See Adobe's [virtual](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/types/product-create-virtual),
[downloadable](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/types/product-create-downloadable)
and [grouped](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/types/product-create-grouped)
product documentation.

## Original expansion limits

The original 50 bundles use dynamic pricing, dynamic SKU and weight, price-range display
and shipment together. Their 600 selection entries are required dropdown
selections with customer quantity changes disabled. Fixed pricing, separate
shipment, optional options, other selection controls and editable quantities
are not represented. Configurable products have at most two variation attributes.

The original accepted expansion CSVs contain no custom options, tier/group prices, upsell
links, scheduled special-price dates, or explicit quantity increments. Related
and cross-sell links, special prices and out-of-stock rows are present.
Backorders are disabled in the stock rows. All products use Taxable Goods.
Existing store stock was preserved during installation, so export stock values
are not a claim about every current live quantity or inherited setting.

## Installed QA collection

The reproducible `WANDS-QA-` package contains 77 simple, 14 virtual, 12 downloadable,
6 configurable, 12 bundle and 6 grouped records. Parent and child records are
counted separately. It reuses 16 approved images and supplies three local download
files. [The fixture guide](QA-CATALOG.md) lists exact SKU cases, expected outcomes,
native and runtime checks, package pins and remaining qualification limits. The matrix below
also includes store-configuration tests that product creation alone cannot supply.

| Area | Installed fixtures and further behavior to verify |
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

The expansion is complete for the approved scale and image scope. The QA suite
is installed on both existing stores. Checkout, payments and post-order download
access remain separate qualification work.
