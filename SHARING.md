# Sharing the catalog

For an authorized recipient, share the [README](README.md) and its pinned
[release assets](https://github.com/rocketweb/mageos-large-demo-catalog/releases/tag/catalog-2026.09.12-rc2).
They need repository access while it remains private. No local image generator,
GPU or API key is needed to use the prepared catalog.

Share the starter first when someone wants to check installation. Share the full
profile for catalog-scale work. Both require their own empty Mage-OS installation.
Do not send the original demo database, vendor tree, credentials or local working
directory. Keep the notices, dataset card and manifests with redistributed files.

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
  documented download from a clean directory, then install the chosen profile
  into a fresh lab. Retain separate source, import and browser evidence.
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

This checklist is preparation, not a record that these steps have passed. There
is no need to change visibility to share privately with existing collaborators.
