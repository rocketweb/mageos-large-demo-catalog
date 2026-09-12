# README screenshot sources

Captured September 12, 2026 from the full-profile acceptance storefront running
Mage-OS 3.5.0, Hyvä Default 1.5.2 and OpenSearch 3.1.0. Catalog release:
`catalog-2026.09.12-rc2` (profile data `2026.09.11-rc2`).

These are direct browser screenshots at 1920 × 1080, saved as JPEG at quality 85.
There is no compositing, image generation, text replacement or storefront styling
change in the captures. Hyvä was installed on the actual remote instance before
capture. Only normal navigation, filter expansion and product
selection were used. No order or cart submission was needed.

| File | Storefront path | Captured state |
| --- | --- | --- |
| `bundle-room.jpg` | `/wands-bundle-001-modern-contrast-living-room-essentials.html` | Initial bundle page with room illustration and price range. |
| `catalog-search.jpg` | `/catalogsearch/result/?q=lamp&product_list_order=relevance&product_list_dir=desc` | Category filter expanded; Relevance selected after the scoped layout correction. |
| `configurable-furniture.jpg` | `/wands-30335-merlyn-6-piece-outdoor-garden-patio-furniture.html` | Furniture pieces set to `6 Pieces (+$150.00)`, price $1,299.99. |
| `bundle-options.jpg` | `/wands-bundle-001-modern-contrast-living-room-essentials.html` | Scrolled to the customization panel, default available selections, total $1,496.46. |

The illustrations are synthetic, not manufacturer photography or a guarantee of
exact component appearance. Room styling can include items outside the bundle.
The structured assortment and current selections define the product.

To refresh a capture, use the same release, theme, viewport, URL and selected
state. Wait for images to load and transitions to settle, keep the target in
view and inspect the saved file before replacing it. Do not capture admin pages,
customer information, credentials or browser chrome.

These four documentation screenshots are intentionally eligible for Git. Actual
SKU-named catalog images remain excluded by the repository's existing rules and
are distributed through release assets instead. The captures show Hyvä UI and
branding; the catalog-image CC0 terms do not relicense third-party UI or marks.

The previous Luma captures are retained in ignored local working artifacts, not
the README gallery. See [Hyvä acceptance](../../distribution/HYVA_ACCEPTANCE.md)
for installation scope, the search layout correction and verification limits.
