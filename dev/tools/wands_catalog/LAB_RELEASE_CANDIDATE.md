# Mage-OS Lab private release candidate

Subsequent acceptance: Matt selected Mage-OS 3.5, and both profiles passed in the
[new isolated instance](LAB35_ACCEPTANCE.md). The preparation record below retains
the original candidate state; 3.4 was not tested and no publication is implied.

September 12 follow-up: the [companion downloader](distribution/DOWNLOADS.md)
is implemented and locally tested, including interruption over loopback HTTPS.
It supports the pinned rc2 manifests below. No rc2 bytes were changed, no new
release was built, and no public download destination has been selected.

The later [offline handoff](LAB_HANDOFF_READY.md) wraps these exact rc2 profiles
with current tools and instructions. The profile pins below remain unchanged.

Prepared September 11, 2026. Candidate `2026.09.11-rc2` is built and verified
locally. It is not published, installed into a new store, committed or pushed by
this pass. The approved MIT/CC0 choices are included in its archives.

## Files to hand over after integration acceptance

| Profile | Local directory under `var/wands/` | Products | Images | Total archive bytes |
| --- | --- | ---: | ---: | ---: |
| Starter | `lab-release-20260911-starter-rc2` | 27 | 24 | 2,222,080 |
| Full | `lab-release-20260911-full-rc2` | 53,844 | 46,602 | 2,326,958,080 |

Each directory has a root manifest, catalog archive, catalog-only module archive,
separate image archives, verifier and build summary. The full profile has nine
media archives. Earlier `v1` files are superseded private experiments and do not
contain the final approved terms. Do not distribute those as the current release.

Manifest SHA-256 pins:

```text
starter 42bd8400415204b8bc6b8f5ed5cf8adb8156185eca92ff156cd54285bb68b40f
full    9bf76000f3de8816459638ba2f396af805eaaa83c504886000e1b3c32adcf19d
```

The source baseline is `99c46f0`. Uncommitted candidate source files are recorded
by their own SHA-256 values in each manifest; the baseline commit alone is not
the candidate's full source. These pins belong in a separately trusted channel
when the artifacts are eventually shared. No release signature exists yet.

## Exact catalog scope

Full profile: 51,799 simple records, 1,995 configurable parents, 50 bundles,
10,736 configurable links, 200 bundle options and 600 selections. There are 64
disabled legacy variants. All enabled products have image assignments.

53,824 products receive 161,472 base/small/thumbnail roles. The 20 missing-media
records are disabled legacy variants and are individually identified in the
media-lineage file. 2,010 children inherit a family illustration; this is disclosed,
not represented as a distinct image accurately showing every selected option.

Starter profile: 23 simples, three configurables, one bundle, ten configurable
links, four bundle options and 12 selections. All 27 products have media.

## Verification performed

- Full Python suite: **434 tests passed** with native PHP enabled for the
  destination-preflight contract test.
- Seven distribution tests cover complete dependency closure, deterministic
  archives, pinned verification, corrupt/missing files, member hashes, unsafe
  paths, symlinks, duplicates, extraction refusal and empty-store collision checks.
- Separate PHP provisioning tests verify URL rejection before database access,
  inherited/explicit theme behavior and removal of the global price-scope write.
- Attribute setup includes every configurable option in both actual release
  profiles. The 29 missing correction labels are now included for fresh installs.
- Module Composer metadata validates with `--strict --no-check-publish`.
- PHP syntax checks pass for all 24 module/distribution PHP files.
- Independent standalone verification passes for both profiles; starter extraction
  into a fresh directory succeeds. A second starter build produces identical
  archive hashes and an identical release manifest.
- Git contains zero SKU-named catalog images, and candidate archives are ignored.

These are offline and contract checks. The PHP preflight test uses a read-only
database double, not a newly installed Magento runtime. Historical demo acceptance
is not proof of a fresh Mage-OS 3.4 install.

## Original remaining boundary (superseded by the 3.5 acceptance above)

Run the [integration procedure](distribution/README.md) in an approved disposable
Mage-OS 3.4 destination, using the pinned starter first and then the full profile
on a restored empty baseline. This pass did not create that environment or install
catalog products locally. The current demo was not modified.

The empty-store preflight is implemented; native import recovery/checkpoints and
automatic downloads are not. Until those are implemented and tested, use the
documented offline, fresh-install-only procedure and restore the empty baseline
after an interrupted import. Do not promote the candidate as an idempotent updater.

Commit/push, destination installation, public hosting and publication are separate
actions. No accounts, paid services, public releases or new automation were created.
