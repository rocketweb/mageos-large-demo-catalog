# GitHub catalog release assets

Published September 12, 2026, with Matt's approval to use release assets.

[WANDS catalog for Mage-OS Lab: 2026.09.12 rc2](https://github.com/rocketweb/mageos-large-demo-catalog/releases/tag/catalog-2026.09.12-rc2)

The repository remains private. This is a published prerelease, not a draft and
not a public launch. Recipients must already have repository access. No visibility
change, collaborator invitation, source-branch push, merge or store deployment
was performed.

## Published scope

- Release ID: `387475409`.
- Tag: `catalog-2026.09.12-rc2`.
- Assets: 24 files, totaling 2,337,285,688 bytes.
- Largest asset: 268,431,360 bytes, below GitHub's 2 GiB per-file limit.
- Includes unchanged starter/full manifests, catalog/module/media archives,
  current toolkit, three standalone download/verification scripts, instructions
  and complete asset checksum inventory.

The `starter-` and `full-` upload-name prefixes are mapped back to original local
filenames by `github_download.py`. The original rc2 catalog hashes remain intact.
Images are release attachments; no image or archive was added to Git or Git LFS.

This asset-only tag anchors the existing remote main commit
`d1cd3749074761f00b62d8584f443046eba3e619`. The source branches were verified
unchanged after publication. The tag's automatically generated source ZIP is not
the current catalog installer; the release notes direct recipients to the attached
toolkit and profile module archives, which contain the actual source and notices.

## Acceptance

The release was created as a draft. All 24 uploaded asset sizes and GitHub SHA-256
digests matched the locally prepared files, with no missing or unexpected assets.
The actual draft starter and toolkit downloads passed byte/member verification
and extraction before publication.

After publication, the released scripts were used from a separate directory:

- Starter: 3 archives and 66 contained files verified.
- Toolkit: 1 archive and 14 contained files verified.
- Full: 11 archives and 46,644 contained files verified.
- Full download deliberately interrupted at 3,145,728 bytes, exited 130, then
  resumed `catalog.tar` from that exact byte offset and completed successfully.
- The child download commands produced zero terminal output; progress and results
  were recorded in their logs.

The Python suite passed 460 tests, including GitHub redirect credential stripping,
profile mapping, archive limits, toolkit extraction and the existing loopback
HTTPS recovery tests. No fresh Magento install was repeated during publication;
the [earlier Mage-OS 3.5 acceptance](LAB35_ACCEPTANCE.md) still applies to the
unchanged rc2 profile pins.

## Trusted manifest pins

```text
starter 42bd8400415204b8bc6b8f5ed5cf8adb8156185eca92ff156cd54285bb68b40f
full    9bf76000f3de8816459638ba2f396af805eaaa83c504886000e1b3c32adcf19d
toolkit 248adfcb07286bcdcae2459fea38d902e8cb29f53d0e9cb273fdaac2d7709908
```

Local assets and their inventory are in `var/wands/github-assets-20260912-v1/`.
The upload and live-download verification logs are adjacent under `var/wands/`.
The public-facing asset text retains WANDS/MIT notices, the paper citation,
approved CC0 scope, synthetic-data disclosures and fresh-install-only limits.

New GitHub-support source and this publication receipt remain local and
uncommitted. The previously committed source baseline is `ac2f9a3`. Published
toolkit files are independently identified by their release-asset hashes.
