# Public-download recipient acceptance

Verified September 13, 2026 (US Eastern), using the published
[`catalog-2026.09.13-enriched-v2` prerelease](https://github.com/rocketweb/mageos-large-demo-catalog/releases/tag/catalog-2026.09.13-enriched-v2).
PR #2 merged as `256cdf8ad496410c3252445c69700cd1f5650ba6`. All 27 uploaded asset
names, sizes and GitHub-reported SHA-256 digests matched the frozen local files.
The previous rc2 release was not modified. A signed-out browser could view the
new release. An archive-aware Gitleaks scan found no secrets in the new assets.

## Fresh installation

The separate, loopback-only `wands-lab35-recipient-v2` fixture used a new database
and new search index. Its Mage-OS 3.5.0 / Hyvä Default 1.5.2 application dependencies
were copied privately from the pinned acceptance installation on the same server.
This is a fresh catalog install, not a fresh Composer-download test. No database,
runtime media, environment file, Composer credentials or catalog module was copied
from the source installation.

The test downloaded all three helpers from the public release without credentials
and verified their pinned hashes before execution. It then downloaded the medium
profile and toolkit using `--anonymous`, verified/extracted them, ran the empty
destination preflight before module installation, enabled the downloaded module,
ran setup, provisioned Hyvä and imported all five documented CSV phases in order.
The original empty baseline and post-import database backups remain private.
No corrective import or mutation of the downloaded files was needed.

| Result | Verified count |
| --- | ---: |
| Products | 5,000 |
| Simple / configurable / bundle | 4,857 / 93 / 50 |
| Configurable links / axes | 500 / 158 |
| Bundle options / selections | 200 / 600 |
| Media role assignments | 15,000 |
| Total catalog assertions | 194,287 |
| Included enrichment assertions | 133,637 |
| Discrepancies | 0 |

The six URL normalizations are Magento's native formatting, recorded by the
verifier. The public downloader verified all 4,734 medium archive members,
including 4,688 images, and the separately pinned toolkit.

## Storefront observations

The Hyvä homepage and department navigation loaded. A native search for `chair`
returned products with specification filters. The Yarnell Upholstered Dining
Chair page showed its synthetic-specification disclosure and related chair.
Selecting Blue/Wool changed the gallery to the matching, successfully loaded
variant image and displayed the $355.99 variant price. The product page fit a
390-pixel viewport without horizontal overflow. No cart or order was created by
these checks.

These are sampled storefront checks, not exhaustive visual acceptance. The
earlier 400 commerce scenarios and full-profile verification remain documented in
[enriched acceptance](ENRICHED_ACCEPTANCE.md); they were not rerun on this medium
recipient fixture. The clean public-download test does not qualify checkout,
payments, every Mage-OS version or every theme. The module and generated data are
for dedicated labs, not existing customer stores.

The local suite passed all 492 tests with PHP and the loopback HTTPS test enabled.
A prior restricted-sandbox run failed to bind its local HTTPS server; rerunning
with loopback networking enabled passed. The operator harness is in
`acceptance/recipient_instance.py`, with quiet stage logs and one-use guards.
