# Mage-OS large demo catalog

For the portable Mage-OS Lab candidate, start with the
[distribution guide](dev/tools/wands_catalog/distribution/README.md).
It separates the catalog module, data and images from this development store.
Product images are distributed as separate archives, not through Git or Git LFS.
The [offline handoff record](dev/tools/wands_catalog/LAB_HANDOFF_READY.md) identifies
the current private recipient package and verification results.

The private candidate passed fresh-install testing on Mage-OS 3.5.0 with both
starter and full profiles. See the [acceptance result](dev/tools/wands_catalog/LAB35_ACCEPTANCE.md).
Mage-OS 3.4 was not tested, and publication remains separate. MIT for code/authored data and
CC0 for generated images where rights are held were approved September 11, 2026.
Do not clone this
entire project as a community sample-data installer: its root Composer files and
environment configuration describe the original private development store.

## Historical development environment

The following setup notes describe the original environment, not the current
portable release or current demo counts. See the
[bulk completion record](dev/tools/wands_catalog/BULK_COMPLETION.md) for the
September 11 demo update.

Local Mage-OS development environment with the Hyva default theme, the original Koti sample-data storefront, and an isolated WANDS relevance-lab storefront.

## Installed stack

- Mage-OS 3.4
- Hyva default theme 1.5.2
- Tailwind CSS 4
- Koti sample data 1.0
- MySQL 8.4 and OpenSearch 3.8 through Docker
- PHP 8.4 through Magebox
- OpenSearch Relevance Workbench pinned to upstream commit `c11e95375c2a3e4f4550dd9c807fd059138e754b`
- Deterministic WANDS catalog preparation, pricing, import, and image-queue tooling

## Local URLs

- Storefront: <http://mageos-latest.localhost:8080/>
- Admin: <http://mageos-latest.localhost:8080/admin>
- WANDS relevance lab: <http://relevance.comtom.lab:8080/>

## WANDS catalog

The WANDS storefront is a separate website, store group, store view, and root category with USD as its scoped base and display currency. Catalog pricing is website-scoped so the original Koti storefront retains its EUR base currency. WANDS products are not assigned to the Koti website. Synthetic prices retain their method and version as product attributes.

The current lab contains 42,994 WANDS products, 861 product classes, 480 seeded search queries, and a curated 10-department top navigation. Heuristic v2 prices range from $19.99 to $4,399.99 with a $309.99 median. Product images are generated locally and attached through resumable, incremental media-only imports.

`relevance.comtom.lab` intentionally uses Magebox's HTTP development port on this machine. Local TLS port `8443` is already owned by SquirrelOps Home, and the public hostname does not resolve to localhost. Do not stop or reconfigure SquirrelOps merely to make this lab use HTTPS.

See [`dev/tools/wands_catalog/README.md`](dev/tools/wands_catalog/README.md) for preparation, import, query seeding, and generated-media commands.

## Restore dependencies

```sh
docker compose -f docker-compose.mageos.yaml up -d
composer install
```

Composer authentication for the Hyva private repository must be configured in the local Composer credential store. Do not commit `auth.json` or `app/etc/env.php`.

## Catalog realism proposals

Use the [review-only realism workflow](dev/tools/wands_catalog/REALISM_REVIEW.md)
to prepare a deterministic 100-product sample and audit the bundle assortments.
This is a separate review lane, not an automatic live-catalog import.

The [full-catalog workflow](dev/tools/wands_catalog/FULL_REALISM.md) adds complete
catalog patches, revised bundles, fictional lab collections, inventory scenarios,
and a reference-audited local image pipeline. Image acceptance and remote import
remain separate gates.
