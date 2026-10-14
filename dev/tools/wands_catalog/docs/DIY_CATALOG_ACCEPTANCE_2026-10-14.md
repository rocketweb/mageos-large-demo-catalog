# DIY catalog acceptance, October 14, 2026

Both dedicated test stores contain only the 107,815-product WANDS catalog, with
canonical DIY category paths, generated product identifiers and URLs.

Navigation order: **DIY, Furniture, Decor, Bed & Bath, Kitchen, Outdoor, Storage,
Kids, Pets**. All nine items occupy one row in both themes at 1024, 1100, 1279,
1280, 1440, 1614 and 1920 pixels, without horizontal overflow.

| Store | Products before | Other products removed | WANDS products after | Empty sample categories removed |
| --- | ---: | ---: | ---: | ---: |
| [Luma](https://latest.rocketcode.com/) | 109,855 | 2040 | 107,815 | 38 |
| [Hyvä](https://latest-hyva.rocketcode.com/) | 158,007 | 50,192 | 107,815 | 47 |

## Clean catalog migration

The old department name also appeared in 2000 generated product SKUs and URL keys.
A bounded native import rebuilt those products with DIY identifiers and updated
their variant references. The other 105,815 product identities, data, stock and
media matched their preservation fingerprints. No order referenced a rebuilt
generated product.

Full database and file backups were verified before the changes, and their
inverse restore plans were validated. Obsolete stock records were quarantined
before native deletion. Customers and test orders were retained.

Both stores have zero products or inventory records outside WANDS, zero legacy
department URLs, and zero legacy department category or product attributes. The
old category URL and a generated product URL returned HTTP 404 without redirects.
Active import data and JSON inventories use the canonical names and references.

## Verification

Both stores run Mage-OS 3.6.0 and PHP 8.4.24 in production mode. Hyvä Default is
1.5.3. Per store:

- 834,131 native catalog and media checks passed across all 107,815 products.
- 963,240 stock checks passed, including 103,746 default-source quantities.
- The exact final candidate passed a same-release no-op update.
- DIY category grids and a rebuilt configurable product rendered correctly.
- Black and Small variant options were selectable in both themes.
- Native indexes were valid after the rebuild.
- Maintenance was disabled, cron restarted, and original memory limits restored.

An isolated checkout of the exact staged changes passed 912 tooling tests with
one optional disposable-store gallery check skipped, plus 32 module tests with
148 assertions. All 35 module files matched the qualified artifact. The descendant
URL regression failed with its fix disabled and passed after restoring it.

The [machine-readable receipt](DIY_CATALOG_ACCEPTANCE_2026-10-14.json) records
artifact pins and the verification counts. The final candidate manifest is
`96a5c20f84bc2b5d29a235ca9aac5210f70b05534662dce70125748d72a11838`.
This candidate is private; the existing public release archives retain their
published identities. Browser acceptance covers desktop navigation and catalog
pages, with no cart submissions or orders created.
