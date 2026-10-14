# Category imports and navigation

The current source module preserves commas in WANDS category names and curates
nine departments after each successful `lab:wands:import`. Validation-only and
failed imports do not curate navigation. The published October 6 archives contain
the older module and retain their documented manual curation step.

The menu contains Furniture, Kitchen, Bed & Bath, Decor, Outdoor, Storage, Home
Improvement, Kids and Pets. Lighting and Rugs are the first two children of Decor.
Other root children, including Room Bundles and QA Fixtures, remain active and are
hidden from the menu.

## Existing trees and repeated imports

Curation renames Kitchen & Tabletop, Décor & Pillows, Storage & Organization,
Baby & Kids and Pet. It moves the existing Lighting and Rugs categories, including
their descendants, under Decor. Category IDs, existing URL keys and direct product
assignments are retained. Magento generates the URL rewrites for the two moves.

The category processor normalizes exported legacy paths to the curated hierarchy.
While an older tree awaits curation, aliases resolve those normalized paths to the
existing IDs. Repeated imports therefore reuse the same branches. Conflicting old
and canonical branches are rejected before category creation.
Each importer adapter receives a fresh category processor. This keeps cached parent
paths current when several imports run in the same process.

Successful import output includes a `navigation` object with visible, hidden,
renamed and moved department counts. Unchanged values are not saved again.
Changes clear the block and full-page caches. Curation uses default-scope names and
visibility; pre-existing store-view overrides need their own review.

The standalone command supports a dry run:

```sh
php bin/magento lab:wands:curate-navigation --dry-run
php bin/magento lab:wands:curate-navigation
```

Back up the affected category records and store URL rewrites before migrating an
existing catalog. Refresh the affected category and search indexes afterward.

## Category path format

Each assignment starts with `WANDS Catalog/`. Commas inside a path are name data,
such as `WANDS Catalog/Kitchen & Tabletop/Vases, Urns, Jars & Bottles`. Multiple
assignments repeat the root:

```text
WANDS Catalog/Slicers, Peelers And Graters,WANDS Catalog/Kitchen & Tabletop/Tools
```

The plugin uses a separate internal path delimiter for comma-separated WANDS
assignments. Explicit alternative delimiters also receive path normalization.
Other catalogs retain native parsing. The global comma separator remains in place
for product links, configurable data and other fields.

Previously created comma fragments are retained. This update prevents new splits
and migrates the nine departments; it does not repair unrelated fragment
assignments. That repair requires its own reviewed migration.

QA Fixtures remains reachable through its direct category URL, normally
`qa-fixtures.html`. The browser verifier accepts `--qa-category-path`.

## Local verification, October 14, 2026

The full local catalog contains 107,815 WANDS products. Native curation renamed five
departments, moved two branches with 123 descendants, and hid QA Fixtures. Before
and after checks retained every category ID and matched the product and direct
category-assignment fingerprints.

Both review views use the same full catalog and store view, with temporary theme
settings and separate caches. The WANDS module provides the navigation stylesheet.
At widths from 1024 through 1279 pixels, it uses closer spacing and 14 px labels in
Hyvä Default. Other websites do not receive that layout handle.

| Theme | Tested desktop widths in pixels | Menu rows | Visible departments | Horizontal overflow |
| --- | --- | ---: | ---: | --- |
| Luma | 768 | 2 | 9 | None |
| Luma | 1024, 1280, 1440, 1920 | 1 | 9 | None |
| Hyvä Default | 1024, 1100, 1279, 1280, 1440, 1920 | 1 | 9 | None |

Measurements waited for Luma's menu widget to initialize. Both Decor submenus
opened with Lighting and Rugs first. The moved category links opened populated
product grids. The temporary review router serves versioned static assets.
The category and search indexes were refreshed for the 125 moved categories and
their 7,494 products.

![Luma navigation at 1280 pixels](screenshots/navigation-luma-1280.png)

![Hyvä navigation at 1024 pixels](screenshots/navigation-hyva-1024.png)

A separate native fixture with 60 products migrated the five legacy names and two
branches during import. Reimporting the base and QA phases kept nine departments
and reported zero further renames or moves. Comma-bearing names and multiple
assignments remained intact.

Module PHPUnit passed 29 tests with 104 assertions and executed the curator,
taxonomy normalizer, category aliases, comma plugin and importer. Removing the
aliases produced three regression failures. The tooling suite passed 886 tests.
The native lifecycle check also failed with the shared processor and passed with a
fresh processor per adapter. It checks parent paths after a move and rolls back the
fixture transaction. Run it only against a disposable navigation fixture:

```sh
php dev/tools/wands_catalog/tests/acceptance/navigation_import_lifecycle.php [FIXTURE ROOT]
```

The earlier fixture's Hyvä mobile drawer did not open, including with the navigation
stylesheet disabled. Desktop acceptance above does not establish mobile interaction
acceptance. Published release archives still require their own update.
