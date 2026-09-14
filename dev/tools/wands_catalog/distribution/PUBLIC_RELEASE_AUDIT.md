# Enriched v2 public release audit

Audit date: September 13, 2026. Target: `rocketweb/mageos-large-demo-catalog`.
The repository was already public. The inspected default branch was `1d57fe4`;
the catalog acceptance baseline was `c427ba4` on `wands-merchandising`.

## Source and history

Gitleaks 8.30.1 scanned all reachable history, reporting 73 commits with changes
and approximately 4.78 MB scanned. Its official Darwin ARM64 archive was checked
against SHA-256 `b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5`.

One finding was inspected: `curl-auth-user` at line 25 of the workbench snapshot's
`docker-compose.security.yml`, introduced by `5fb0c11`. It uses
`admin:$${OPENSEARCH_INITIAL_ADMIN_PASSWORD}`, an environment reference, not an
embedded password. No credential rotation or history rewrite follows from that
finding. No credential files or database dumps were found in historical tracked
paths. This is a scoped audit, not a guarantee that automated scanning finds
every possible secret.

The four tracked JPEGs are documentation screenshots. Catalog image binaries
and release archives remain outside Git and Git LFS. The root Composer project
still describes the original development store, including a Hyvä repository
endpoint. It is not the portable installer; recipient instructions use the
separately packaged catalog module.

The root MIT scope, original WANDS license and citation, generated-media CC0
qualification, and the workbench snapshot's OSL/AFL notices remain separate.
Theme packages, vendor directories, model weights, credentials and database
exports are not release assets. Historical generated-media provenance limitations
remain disclosed rather than being treated as blanket rights clearance.

## Release and runtime gates

Medium and full v2 profile pins remain the ones in
[enriched acceptance](ENRICHED_ACCEPTANCE.md). The gallery pin is in
[gallery installation](GALLERIES.md). New helper code supports an explicit
anonymous mode and a separate gallery asset namespace. Each new helper behavior
has a regression test observed failing before its fix.

The new release uses a new tag, `catalog-2026.09.13-enriched-v2`; the existing rc2
tag and asset bytes must not be replaced. Verify the integrated source commit,
uploaded asset names/sizes/digests, an anonymous download and a clean recipient
installation before reporting the release workflow complete.

Publication and the clean medium recipient installation are now verified in
[public recipient acceptance](PUBLIC_RECIPIENT_ACCEPTANCE.md). All 27 uploaded
asset digests matched; anonymous helper, toolkit and catalog downloads succeeded.
The recipient completed all five import phases and 194,287 assertions without a
corrective import. The archive-aware asset scan found no secrets.

## Repository settings observed

Issues are enabled. Main-branch protection is disabled, and no active CI check
runs were returned for the inspected default commit. GitHub secret scanning and
push protection are disabled. These settings were inspected, not changed.
The security document provides a direct email reporting route and does not
promise that GitHub private vulnerability reporting is enabled.

## Demo update boundary

The demo already runs Mage-OS 3.5.0 with Hyvä Default 1.5.2 and hybrid search.
It has 55,044 products, zero customers and zero orders at inspection. Its 1,200
additional test products are not part of the 53,844-record distribution profile.
Do not replace this store with the stock-search acceptance fixture. Prepare an
attribute/link-only update, preserve extra products and existing search modules,
and retain a scoped before-state and database backup before applying changes.
