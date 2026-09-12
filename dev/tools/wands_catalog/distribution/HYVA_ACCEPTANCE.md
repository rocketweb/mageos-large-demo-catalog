# Mage-OS 3.5 with Hyvä: storefront verification

On September 12, 2026, Hyvä Default **1.5.2** was installed on the full-profile
Mage-OS **3.5.0** catalog instance. The README screenshots were captured from this
running storefront, not generated or restyled browser mockups.

## Environment and scope

- PHP 8.4.25, MariaDB 11.4 and OpenSearch 3.1.0.
- Default `Hyva/default`, with Mage-OS branding and the existing WANDS navigation.
- Theme assignment limited to WANDS website 2 and store view 2.
- Fifteen dependency additions; zero existing package updates or removals.
- Hyvä's dependency tree includes Mollie packages. Its master enabled/active
  flags are explicitly off on WANDS. No payment credentials were configured.
- Existing CAPTCHA and security settings were not changed.

The instance was originally installed fresh and tested with Luma. Hyvä was added
after the full catalog import, so this is not a separate fresh-import test under
Hyvä. The other relevance demo, public routing and repository visibility were
not changed. No catalog archives or generated image bytes were replaced.

Installed Composer lock SHA-256:
`8674885f1a076ed4f875d729cd7cf45ad54c474240a73bc15f208d6b9f8e4e7d`.

## Checks performed

The full read-only catalog/media verifier passed **616,053 assertions with zero
discrepancies** after installation:

| Record | Verified count |
| --- | ---: |
| Products | 53,844 |
| Simple / configurable / bundle | 51,799 / 1,995 / 50 |
| Configurable links / axes | 10,736 / 3,384 |
| Bundle options / selections | 200 / 600 |
| Base, small and thumbnail image roles | 161,472 |
| Customers / orders | 0 / 0 |

All 11 indexes were Ready with zero scheduled backlog at final verification.
The local catalog suite passed 461 tests, including the new search-layout
regression and opt-in HTTPS fixtures. The deployed layout hash matched the local
file: `3a64e072e08d2d499b9ee7cf1cfa054a884e0f9fe19f378c05c2a7929a849268`.

Browser checks on the actual storefront confirmed:

- Hyvä CSS under `frontend/Hyva/default/en_US/css/styles.css`, the Hyvä browser
  object and Alpine 3.14.3 loaded.
- The living-room bundle displays its illustration and price range. Changing
  seating from Abida to Gatun recalculated the total from $1,496.46 to $1,716.46.
- The Merlyn furniture family accepts the six-piece option and displays $1,299.99
  with its variant illustration.
- Selecting Brown and White on the nursery-decor family loads the corresponding
  distinct color-specific media paths successfully.
- Lamp search renders product images and expandable category filters. The
  normal search URL renders Hyvä, not the earlier cached Luma response.
- Search selects Relevance by default; selecting Price updates both the URL and
  selected option. Returning to explicit Relevance also selects it correctly.
- The checked bundle page has no horizontal overflow at a 390 px viewport.
  No visible error messages or browser JavaScript errors were observed in the
  final checked states.

No cart submission, login, registration, checkout, payment or order-placement
acceptance is claimed for this Hyvä pass. Search checks are functional, not a
ranking-improvement measurement. Synthetic media limitations still apply.

## Search layout correction

The initial Hyvä search toolbar retained a cached `position` sort value while its
available orders were Name, Price and Relevance. No option was marked selected,
so the browser displayed the first label, Product Name. Runtime diagnostics
confirmed that the list had Relevance configured while the toolbar still held
Position.

The [Hyvä-only layout](../../../../app/code/RocketWeb/LabCatalog/view/frontend/layout/hyva_catalogsearch_result_index.xml)
initializes the lab's three search sort choices and defaults, then clears the
toolbar's stale cached order/direction. Native request-driven choices remain
available. It affects `hyva_catalogsearch_result_index`, not Luma or category
pages. The regression check was observed failing before the file existed;
live browser checks confirmed the failing state and then verified Relevance,
Price and explicit Relevance after the correction.

This file is an addition to the current source and the screenshot instance. It
is **not in the unchanged rc2 module archive**. To reproduce this Hyvä setup,
copy it to `app/code/RocketWeb/LabCatalog/view/frontend/layout/` after installing
the catalog module and Hyvä, then clean layout and full-page caches. The shipped
theme's vendor templates were restored unchanged after temporary diagnostics.

## Recovery and retained evidence

A full pre-change database backup, Composer files and application configuration
were retained privately on the server before installation. A targeted recovery
procedure accompanies them. Stale full-page cache files survived normal CLI
clean/flush in this instance; the affected cache directories were moved into the
private recovery receipt and recreated with web-user ownership. The original
browser session then served Hyvä on the unchanged search URL.

Backup files, credentials and private Composer access are not part of this
repository or its release assets. Screenshot sources and captured states are in
[the capture notes](../docs/screenshots/README.md). The catalog's original
[Luma import acceptance](ACCEPTANCE.md) remains historical evidence.
