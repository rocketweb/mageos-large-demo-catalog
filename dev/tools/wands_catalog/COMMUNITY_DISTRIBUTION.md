# Sharing the catalog with Mage-OS Lab

Original design, September 9, 2026. The September 11 implementation is in
[distribution/README.md](distribution/README.md): deterministic private candidate
archives and an offline verifier. Starter/full acceptance on Mage-OS 3.5.0 is
recorded in [the acceptance result](LAB35_ACCEPTANCE.md). A source-only
[resumable downloader](distribution/DOWNLOADS.md) followed on September 12.
Resumable import, hosting and publication remain open; 3.4 was not tested.
The sections below retain the
original design requirements and historical packet counts, not current acceptance.
Matt approved MIT for authored tooling/data and CC0 for generated images where
rights are held on September 11; see [current terms](distribution/TERMS.md).

## Recommended boundary

Share a reusable sample-data package, not a clone of Matt's store. Recipients
should install a pinned catalog and its already-generated images without a
Mac, a GPU, oMLX credentials or access to the existing demo server.

| Layer | Contents | Proposed home |
| --- | --- | --- |
| Source | Importer, schemas, recipes, tests, notices, release metadata, tool screenshots and diagrams | GitHub repository |
| Catalog release | Portable product/attribute/category records, prices, stock scenarios, configurable and bundle relationships | Versioned downloadable archive |
| Media release | Selected product JPEGs, including accepted repair references, with SKU/role mappings and hashes | Separate versioned downloadable archives |
| Local runtime | Download cache, staging, import checkpoints and logs | Ignored filesystem paths on the recipient's machine |

Product photos do not belong in Git or Git LFS. Tool illustrations do belong
in Git. The ignore policy distinguishes generated media directories and
SKU-named product files from screenshots, diagrams and theme assets. Prompts,
generation provenance and audit evidence are not product-image binaries.
The regression test checks ignored paths and the current Git index; it is not
a server-enforced push policy, and `git add -f` can bypass ignore rules.

An ordinary follow-up commit removes the four previously tracked product
reference JPEGs from the current tree without deleting their local files.
They remain recoverable from earlier Git history. No force push or history
rewrite is needed for these roughly 342 KB of historic assets.

## Distribution and installation

Use an owner-controlled HTTPS download location, backed by ordinary static
files or S3-compatible object storage. Keep a configurable mirror/base URL so
Mage-OS Lab can host the exact same bytes independently. Decide the account,
access level, bandwidth budget and hostname before any upload or purchase.
Do not serve release downloads through the Magento application or require its
private `.lab` hostname. No provider or hosting-cost claim is settled here.

Start with one catalog archive and a bounded set of media archives, not a
service requiring API accounts. Group images deterministically by SKU range
with a maximum archive size. Avoid recompressing JPEGs; preserve accepted
bytes and hash identity. Archive names are immutable within a release.

The root release manifest should contain:

- Release/schema versions, exact source commit and supported importer range.
- Upstream dataset revision/hash, recipe versions and license-notice paths.
- Artifact relative paths, compressed/unpacked byte counts and SHA-256 hashes.
- Exact counts by product type, configurable links, bundle options/selections,
  media associations, distinct image files and intentionally missing images.
- A per-image manifest with relative path, SKU, media role, dimensions, byte
  count, hash, generation lineage and actual acceptance status.
- Catalog profile, complete dependency closure and any known limitations.

Release checksums must be pinned in the source release metadata received
through a separate trusted channel. A checksum downloaded beside a changed
archive does not independently establish authenticity. Signed manifests can
be added when an owner and signing-key process are agreed.

Planned recipient experience, not commands that exist yet:

1. Install a small Composer catalog module into an existing supported Mage-OS
   installation. No dependency on Matt's project `composer.json` or lockfile.
2. Select an explicit catalog version and profile. Download with progress in a
   log, resumable partial files, bounded retries and final hash verification.
3. Validate disk space, schema compatibility, currency, website/store target,
   SKU collisions and exact affected records. Show a dry run before import.
4. After confirmation and backup, stage data and media, import attributes and
   simple children before dependent parents/bundles, then associate media.
5. Reindex and verify counts, selectable options, bundle pricing/salability,
   sample search results, images and synthetic disclosures in the storefront.

Default to an empty dedicated lab installation. Existing stores require a
separate explicit target and snapshot/rollback review. Never delete unrelated
SKUs or replace the whole product table. Re-running a release must be
idempotent, with checkpoints bound to release hashes and destination identity.
Rollback must preserve pre-existing values and shared media; uninstalling the
module must not silently delete catalog data.

The downloader/extractor must reject traversal, absolute paths, symlinks,
unexpected files, duplicate destinations and expansion beyond declared size
limits. Do not execute scripts supplied by a data archive. Finish validation
before moving staged media into the installation.

## Catalog profiles and dependencies

Prepare a small starter profile from accepted families in the current pilot,
plus representative accepted bundles. Derive its complete child/component
closure and exact counts rather than arbitrarily taking the first CSV rows.
Offer the full catalog separately once its complete release is accepted.
Optional generation recipes are for contributors, not prerequisites for users.

The existing full realism packet targets 53,844 distinct SKUs: 40,994
standalone simples, 10,800 simple children, 2,000 configurable parents and 50
bundles. Those are local packet counts, not an accepted community release.
Media-folder file counts do not establish coverage, uniqueness or approval.

The core catalog must not require Hyva, Koti sample data or OpenSearch Hybrid.
Keep theme presentation and search configuration as optional integrations.
Test the core on a clean stock Mage-OS 3.4 installation; test the Hyva adapter
separately with the recipient obtaining any dependencies through their own
authorized installation route. Never bundle a private Composer credential,
vendor tree, theme archive or unrelated source snapshot with the catalog.

## Provenance and redistribution review

The local upstream manifest pins WANDS revision
`3b74dcf4ba29ab8ff3e6a50b5b09fc627cb882b5`. Its
[license](https://github.com/wayfair/WANDS/blob/3b74dcf4ba29ab8ff3e6a50b5b09fc627cb882b5/LICENSE)
is MIT and requires retention of its copyright and permission notices. Its
[README](https://github.com/wayfair/WANDS/blob/3b74dcf4ba29ab8ff3e6a50b5b09fc627cb882b5/README.md)
also requests citation of the WANDS research paper. Include both in each
data distribution. Source verification performed September 9, 2026.

The current generator defaults to FLUX.2 Klein 4B. The upstream
[model card](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B)
identifies its weights as Apache-2.0. That is not an automatic license for
all generated images or a guarantee about third-party rights. Before sharing,
inventory actual generator/model revisions and reference origins for each
accepted image; review output terms and any mixed-model exceptions. Do not
include model weights in the catalog download. Preserve model references and
generation settings without claiming byte-identical regeneration on all hosts.

The current root Composer metadata describes a Mage-OS project, not a complete
license decision for Rocket Web's new importer, derived data and generated
media. Matt must choose those distribution terms explicitly. Prepare separate
code/data/media notices and review third-party dependencies before publication.
Do not represent the package as an official Mage-OS or Wayfair release without
agreement from the relevant maintainers.

Use a dataset card that distinguishes original WANDS facts from fictional
prices, stock, rewritten copy, variants, bundles and dimensions. Images are
synthetic illustrations, not manufacturer photographs. Synthetic dimensions
remain visibly disclosed, with no fit, safety, certification or warranty
guarantees. Historical source ratings must not become invented customer
reviews or generated-variant ratings.

Keep original WANDS judgments in a separately identified benchmark profile.
They do not validate rewritten content, generated children or bundles. A
community release must not inherit the old hybrid-search improvement claim
without a matching corpus and new evaluation evidence.

## Packaging acceptance gates

1. Finish option/assortment corrections and media acceptance for the chosen
   profile. The 300-root depth packet currently has 36 repair-queue roots and
   non-executable gallery briefs; it is not publishable as a completed gallery.
2. Extract a portable catalog-only package from this machine-specific project.
   Remove hard-coded paths, private repository routes, domains, IDs and local
   installation assumptions from its public interface.
3. Build from an explicit accepted SKU/media allowlist. Do not archive a whole
   worktree, `var`, `pub/media`, database dump or generation-run directory.
4. Retain raw private audit evidence locally. Produce a sanitized public
   manifest with relative paths, no credentials, no personal/home paths, no
   private URLs, and no unrelated customers, orders, sessions or logs.
5. Build a local release candidate with hashes, notices, complete dependency
   closure, precise media coverage and an offline installation path.
6. Test on a disposable clean installation: first install, interrupted/resumed
   download, interrupted/resumed import, corrupt/missing archive, repeated
   import, rollback and customer-visible acceptance. Record timings and disk
   usage from that run rather than promising estimates as measured facts.
7. Agree code/data/media licenses, hosting ownership and release scope with
   Matt. Present the exact artifact hashes and destination for publication
   approval. Only then push code, upload archives or announce availability.

First distribution deliverable: a private, portable starter release candidate
that a second person can install without Matt's filesystem, credentials or GPU.
Full media distribution, automated hosting, public publication and official
Mage-OS Lab integration remain later, separately approved steps.
