# Mage-OS 3.5 acceptance result

The private catalog candidate passed fresh-install testing on Mage-OS 3.5.0.
Matt selected 3.5 instead of the originally proposed 3.4 target. No Mage-OS 3.4
compatibility result is implied.

The instance runs on `37.27.126.105` at
`/opt/comtom/wands-lab35-acceptance`, in the dedicated
`wands-lab35-acceptance` Compose project. Its storefront is private, bound only to
`127.0.0.1:18035`. The existing relevance demo was not modified or restarted.

## Result

| Check | Starter | Full |
| --- | ---: | ---: |
| Products | 27 | 53,844 |
| Simple records | 23 | 51,799 |
| Configurable parents | 3 | 1,995 |
| Bundles | 1 | 50 |
| Configurable links | 10 | 10,736 |
| Bundle options / selections | 4 / 12 | 200 / 600 |
| Verified image roles | 81 | 161,472 |
| Data/media assertions | 303 | 616,053 |
| Discrepancies | 0 | 0 |

The expanded full-profile verifier also checks 3,384 configurable axes, exact
child option labels, bundle component identities, quantities, defaults and price
settings. All four native full-import phases reported zero invalid rows and zero
errors. All 11 indexes are Ready with no scheduled backlog.

Browser checks passed on the actual remote storefront:

- Configurable size/color selection and an $870.99 selected variant added to a
  guest cart. No order was placed.
- Color-specific image switching on the corrected nursery-decor family.
- Bundle selection recalculated $1,496.46 to $1,716.46.
- An intentionally out-of-stock vanity displayed `OUT OF STOCK` with no purchase
  button.
- Search for `lamp` returned products. This is a functional check, not a ranking
  study or an inherited WANDS relevance-improvement claim.
- A 390 px mobile viewport had no horizontal overflow in the checked bundle view.
- Homepage HTTP 200 and a curated ten-department menu. All 57 top-level categories
  remain; 47 are hidden from the main menu, not deleted.

The full test database contains one guest quote, zero customers and zero orders.
The dataset still includes the disclosed 64 disabled legacy variants, 20 disabled
records without media and 2,010 inherited family illustrations. Passing import
checks does not turn synthetic images into exact product-geometry evidence.

## Runtime and isolation

Fresh Composer installation: `mage-os/project-community-edition` 3.5.0.
PHP 8.4.25, MariaDB 11.4, stock OpenSearch 3.1.0 and the stock Luma theme.
No Hyvä, NetSuite, hybrid-search or relevance-workbench package is installed.
The private PHP runtime image was reused; no demo application files, vendor tree,
credentials or database were copied.

Composer lock SHA-256:
`8c5bd32869f215c1864a9ebf21428b45dbfd5ff66882cbcd64d1683ebfc62b5b`.
The environment receipt records all four exact image IDs, the single dedicated
network and loopback-only port binding. No public proxy, DNS or TLS routes changed.

The starter database is retained as `lab_starter`. The full profile runs in
`lab_full`, created separately from the original empty baseline. The private
baseline backup is `receipts/empty-before-module.sql`, SHA-256
`29105d60d71a3f9ce4dc292b02b6d271f305594c6e1085bcc1c0506329bdc8cc`.
Backup/configuration/credential files remain on the server. Generated credentials
are mode 0600; a scan found none in the installation logs.

## Installation findings incorporated into the harness

Native bundle stock flags are not effective availability when stock management
is explicitly disabled. Verification checks the unmanaged configuration instead;
the storefront separately proved bundle availability and dynamic pricing.

Root-run CLI steps generated directories that PHP-FPM could not extend during
the import. The final ownership cleanup and PHP restart restored HTTP 200, and
the working-tree harness source now runs subsequent Magento commands as `www-data`
with ownership prepared before setup/import. The public procedure documents the
same requirement. No catalog-module behavior change was needed for this issue.

The existing menu-curation command is now included in the procedure and harness.
It changes only menu visibility, retaining categories and product assignments.

The real destination preflight passed against each empty database and refused a
repeat install against the populated 53,844-product catalog without database writes.
Automatic import resume and an idempotent existing-store updater remain unsupported.

## Access

From the Mac, establish a tunnel:

```sh
ssh -N -L 18035:127.0.0.1:18035 root@37.27.126.105
```

Then open [the test storefront](http://127.0.0.1:18035/). Magento and the catalog
remain on the server. The instance is an acceptance fixture, not a public service;
no periodic cron worker was added. Reindex manually after subsequent catalog edits.

Remote receipts: `starter-state.json`, `full-state.json`, `receipts/`,
`src/var/starter-verification.json` and `src/var/full-verification.json`.
Local aggregate copies: `var/wands/lab35-starter-verification.json`,
`var/wands/lab35-full-verification.json` and `var/wands/lab35-environment.json`.
No database or credential export was downloaded.

The tested archives remain immutable `2026.09.11-rc2` candidates with the pins in
[the release record](LAB_RELEASE_CANDIDATE.md). Their original documentation
mentions the proposed 3.4 gate; this receipt records the subsequently selected
and actually tested 3.5 environment. Source documentation includes the observed
ownership and navigation steps. Source changes are not committed or pushed, and
no public release or hosting publication has occurred.
