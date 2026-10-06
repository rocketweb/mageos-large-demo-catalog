# Sharing the catalog

Share the [root README](README.md) and stable
[catalog-2026.10.06 assets](https://github.com/rocketweb/mageos-large-demo-catalog/releases/tag/catalog-2026.10.06).
The release provides 107,815 records, all six core types, approved expansion media
and 127 named QA fixtures. Public downloads need no account, model, GPU or API key.

| Shareable item | Scope |
| --- | --- |
| October stable full and toolkit | Current complete catalog, fresh-lab installer, QA definitions and manifests |
| September medium/full prereleases | Historical 5,000/53,844-record alternatives with their own pins |
| Source and guides | Portable module, recipes, acceptance limits and contribution tools |

Recipients need an empty Mage-OS lab, their own routing and an empty-baseline
backup. Do not send a live database, vendor tree, credentials or working directory.
Keep notices, the dataset card and manifests with redistributed files. Share the
[current acceptance limits](dev/tools/wands_catalog/distribution/PRODUCTION_RELEASE.md#acceptance-and-practical-limits)
with the catalog: existing-store checks, archive verification and fresh recipient
installation are separate qualification surfaces.

## Maintainer checklist before a public launch

- [ ] Review the exact branch, full reachable Git history and release contents
  for credentials, private configuration and third-party material. In particular,
  the historical root Composer project contains environment-specific repository
  configuration; it is not the portable installer. A clean working tree is not
  a public-history audit. If cleanup is needed, choose a reviewed export or
  history-cleanup plan before changing visibility.
- [ ] Integrate the intended source into the default branch after approval, so
  the landing README, license and contribution links describe the released work.
  Pushing a feature branch does not update that landing page.
- [ ] Build a new versioned toolkit/module release for source changes. The rc2
  archives do not include the later Hyvä search-layout correction. Do not replace
  their bytes under existing hashes or move their tag to newer code.
- [ ] Verify new assets by size, SHA-256 and archive member inventory. Test the
  documented download from a clean directory, qualify recipient installation separately from existing-store acceptance.
  A new third store was explicitly excluded for this release; disclose that limit
  and retain source, package-parity, native-import and browser evidence.
- [ ] Keep the [license scope](NOTICE.md), WANDS citation and generated-media
  provenance limits in the shared package. Do not imply blanket rights clearance
  for third-party UI, marks or historical image references.
- [ ] Obtain approval for repository visibility and any release publication.
  Update current access instructions after visibility changes; preserve dated
  acceptance records as historical evidence.
- [ ] Check GitHub issue availability, private security reporting and branch
  protection settings. These documents do not configure those settings.
- [ ] From an unauthenticated browser after publication, verify the default
  README, screenshots, license and release downloads. A successful owner download
  does not prove public access.

This checklist is a reusable release gate, not a record that every setting is
enabled. See [the release audit](dev/tools/wands_catalog/distribution/PUBLIC_RELEASE_AUDIT.md)
for the dated September 13 findings. Repository visibility was already public before that pass;
no visibility change was needed.
