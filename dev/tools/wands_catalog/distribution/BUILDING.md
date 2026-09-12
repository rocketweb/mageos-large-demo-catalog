# Building the private candidate

Run from the catalog repository, not the OpenSearch module checkout. The builder
requires Python 3.11+ and Pillow for JPEG header/format verification. Recipients
only need the standard-library verifier. No image generation occurs during builds.

Supply existing pinned inputs explicitly. Paths belong in local commands, not
the public manifest. This recipe intentionally requires the pinned prepared base;
changing datasets requires an explicit recipe revision and validation.

```sh
python3 dev/tools/wands_catalog/distribution/build_release.py \
  --repository "$PWD" \
  --base /path/to/prepared/products.csv \
  --families var/wands/merchandising-stock-explicit-v1 \
  --realism var/wands/realism-stock-explicit-v5 \
  --corrections var/wands/bulk-native-import-v3 \
  --base-prompts /path/to/prepared/image-prompts.jsonl \
  --media /path/to/generated/wands \
  --corrected-media var/wands/bulk-media-import-v4 \
  --output var/wands/lab-release-starter \
  --profile starter --release 2026.09.11-rc1
```

For the full catalog, choose `--profile full` and a different new output directory.
The adjacent `.log` file records progress, failures, final counts and the manifest
pin. Output directories cannot be overwritten. Retain completed artifacts as
immutable candidates, and give revised builds new identifiers and directories.

The builder merges original prepared records, configurable families, full realism
updates, bundle definitions and the final bulk corrections. It preserves disabled
retirements while removing obsolete configurable relationships. For this
fresh-install recipe, explicit-empty decimal sentinels become empty CSV fields;
these CSVs are not a safe update recipe for existing stores.

Profiles include the complete dependency closure. Missing relationships, option
value disagreements, duplicate SKUs/URLs, invalid prices, nonfinite quantities,
private environment references and missing enabled-product media stop the build.
Media bytes are not rewritten. Per-image dimensions, hashes, lineage and actual
acceptance limitations accompany the archive inventory. JPEG verification checks
file structure/header consistency, not a new exhaustive visual audit.

Deterministic tar headers use zero timestamps and neutral ownership. Content
changes, including documentation changes, produce new hashes. Source-file hashes
identify uncommitted candidate changes independently of the baseline Git commit.
Do not claim the baseline commit alone reproduces a dirty candidate.

## Checks before handing over files

```sh
python3 -m unittest discover -s dev/tools/wands_catalog/tests -p 'test_*.py' \
  > var/wands/distribution-tests.log 2>&1
php dev/tools/wands_catalog/distribution/test_provisioner.php \
  > var/wands/distribution-php-tests.log 2>&1
php dev/tools/wands_catalog/distribution/test_attribute_options.php \
  /path/to/verified/staging/data/attribute-options.json \
  >> var/wands/distribution-php-tests.log 2>&1
```

Use the real PHP binary for the intended runtime, not a wrapper for another store.
Verify a second identical starter build has identical archive and manifest hashes.
Run the standalone verifier and extract only into a new directory. Check that
release archives and product images remain ignored by Git. Keep the full store's
Composer project, credentials, database backups and unrelated modules out of the
archives. Publish only after destination testing, rights and hosting approval.

## Offline recipient handoff

The handoff builder wraps the accepted rc2 profiles without rebuilding their
catalog, module or media archives. It adds the current standalone verifier,
downloader, preflight and recipient documentation from an explicit allowlist.
Private acceptance infrastructure, environment files and generation directories
are not included.

```sh
python3 dev/tools/wands_catalog/distribution/build_handoff.py \
  --starter var/wands/lab-release-20260911-starter-rc2 \
  --full var/wands/lab-release-20260911-full-rc2 \
  --output var/wands/lab-handoff-20260912-v3
```

The builder requires the exact accepted manifest pins compiled into its recipe,
verifies both profiles first, then creates `handoff.tar`, a new handoff manifest,
a standalone verifier and `START_HERE.md`. Output must be a new directory.
Progress is recorded in the adjacent `.log`; nothing is printed by default.

The outer manifest verifies the wrapper and exact nested archive bytes. Recipients
also run the enclosed verifier on their chosen profile before its extraction.
Trust the handoff pin through a separate channel and authenticate `release.py`
against that pinned manifest before executing it. The documented bootstrap check
does not rely on Python assertions, which optimization can disable.

The full offline handoff is about 2.34 GB. Keep space for the wrapper, extracted
profile archives, selected profile contents, and the recipient's installation.
No hosting service is required for offline handover. Resumable HTTPS downloads
remain an alternative for recipients who only need one profile after hosting is
approved. Product archives stay outside Git and Git LFS.
