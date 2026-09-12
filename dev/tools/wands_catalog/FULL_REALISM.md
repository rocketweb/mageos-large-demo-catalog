# Full-catalog realism workflow

This extends the 100-product review to the entire WANDS catalog. It prepares
changes locally; it does not import into either local Magento or the remote store.
Existing WANDS SKUs, product types, relationships, URL keys and frozen relevance
judgments are preserved. Non-WANDS products are outside the patch.

## Implemented priorities

| Priority | Implementation |
| --- | --- |
| Names | Preserve useful short names; compact long marketing titles; remove fixed source colors/materials/sizes when a configurable axis varies them |
| Copy | Source-backed parent and selected-child descriptions, escaped HTML, readable specifications; contradictory features are withheld |
| Prices | Exact class, taxonomy, class-family and department fallbacks; explicit synthetic anchors; subtype, pack and material handling; color-neutral family pricing |
| Images | Hash-pinned reference-edit jobs for every child and default bundle assortment; quiet resumable local runner; reference-audit gate |
| Bundles | 50 revised room-essentials assortments, exact class eligibility, simple-only selections, bounded price bands, available defaults where possible |
| Specifications | Allowlisted source facts and original evidence; no inferred units, certifications or warranties |
| Brands | Seven coherent fictional lab collections; separate `lab_brand` attribute, never a replacement for real source manufacturers |
| Availability | In-stock, low-stock and unavailable scenarios, clearance prices, derived configurable/bundle stock, no invented delivery dates or backorders |

Some bundle roles intentionally change. Bedroom essentials use nightstand,
lighting, storage and pillow instead of unverified bed/bedding pairs. Bathroom
essentials use storage, mirror, mat and accessories instead of unverified faucet
installation combinations. Kids bundles are study collections, not infant-sleep
assortments. Dining bundles are tabletop collections. Existing bundle SKUs and
URLs remain stable. Prices are fictional USD lab values, not researched retail.

## Build

From `/Users/matt/code/rocket-search/.worktrees/wands-merchandising`:

```sh
python3 dev/tools/wands_catalog/build_realism_catalog.py \
  --source-products /Users/matt/code/rocket-search/data/raw/wands/product.csv \
  --prepared-products /Users/matt/code/mageos-latest/var/wands/products.csv \
  --merchandising-dir /Users/matt/code/mageos-latest/var/wands/merchandising \
  --media-dir /Users/matt/code/mageos-latest/pub/media/import/wands \
  --output-dir var/wands/realism-full
```

Choose a fresh directory. Default output goes to the sibling `.log`; `--json`
explicitly opts into terminal output. Identical inputs/code produce identical
data files. All four inputs are hashed before and after the build.

The completed development packet is currently `var/wands/realism-full-v4`:

- 42,994 source products and 10,800 children, totaling 53,794 product patches.
- 50 bundles with 600 selections.
- 10,850 reference-based image jobs.
- Source evidence, validation checks, and local-artifact inverse CSVs.
- No unresolved per-unit quantity pricing exceptions in this packet.

These are artifact counts, not a claim of live deployment. Broad category price
fallbacks and all inferred commercial values are identified as synthetic in the
evidence. Withheld facts remain in the evidence file, not the storefront copy.

## Images: audit first

For the repaired reference set and the current resumable bulk runner, use
[Repaired references and gated bulk generation](REFERENCE_BULK.md). The original
calibration findings below are retained as evidence, not the current repair state.

The existing local `mflux==0.19.1` runtime supports `Flux2KleinEdit`. It uses the
Mac GPU directly. It does not use oMLX, ChatGPT quota or a cloud API for image
generation. oMLX is used only for the optional vision-reference audit.

Two color edits have been generated and inspected: the black and blue variants
of `WANDS-042963` preserve the reference chair. This is edit-consistency evidence,
not acceptance against the catalog: the subsequent source audit flagged the
chair's color and missing tufting. The bundle trial did **not** pass:
it duplicated a chair and omitted a lamp. Inspection also found an existing
loveseat reference depicting a chair, and a lamp-set reference depicting one
lamp. Do not bulk-generate from those references or treat the trial as accepted.

Supply the oMLX credential through `OMLX_API_KEY`, or pass an explicit
`--env-file` containing exactly one `OMLX-KEY` entry. On this workstation the
approved source is `/Users/matt/code/.env`. Only that named entry is parsed;
the file is never sourced, modified or copied. Duplicate entries and shell
interpolation are rejected. An explicit file takes precedence over the process
environment. The tools never search credential stores or embed the key in
arguments, output files or prompts.

The following command uses the locally tested vision request path. It performs
a bounded five-reference calibration, not a full-catalog audit:

```sh
python3 dev/tools/wands_catalog/audit_reference_images.py \
  --jobs var/wands/realism-full-v4/image-jobs.jsonl \
  --source-products /Users/matt/code/rocket-search/data/raw/wands/product.csv \
  --output var/wands/realism-verification/reference-calibration-v2.jsonl \
  --model Qwen3.8-27B-8bit \
  --env-file /Users/matt/code/.env \
  --reference-id 42963 --reference-id 14081 --reference-id 17261 \
  --reference-id 23338 --reference-id 17873
```

Normal output and errors go to the sibling `.log`, never the terminal:

```sh
tail -f var/wands/realism-verification/reference-calibration-v2.log
```

The runner requires `finish_reason=stop` and a valid verdict. Truncated or
malformed output gets one retry with a larger token budget (1,024 then 2,048).
Blocked or unsupported completions fail immediately. Exhausted retries stop the
run without approving that image. Every saved audit records the model, policy
version, prompt hash, source-evidence hash, image hash and completion metadata.
An output lock prevents concurrent writers. Restarting the same command skips
matching completed audits, including failed/uncertain verdicts. An interrupted
final JSONL record is preserved and separated from new records on resume.
Changed source evidence, image hash, model or audit policy triggers re-auditing.

Calibration on September 4, 2026 completed all five requests with normal
completion status. A repeat of the same command made zero model requests:

| Reference | Model verdict | Finding / next action |
| --- | --- | --- |
| `WANDS-042963` | Uncertain | Brown smooth chair versus listed blue/gray/off-white options and tufting; review source facts and replace the reference before accepting derived variants |
| `WANDS-014081` | Fail | Single chair instead of a two-seat loveseat; regenerate as a loveseat |
| `WANDS-023338` | Fail | Brown square table instead of a light-gray octagonal table; correct shape and finish |
| `WANDS-017261` | Fail | One lamp instead of the listed set; show both lamps |
| `WANDS-017873` | Pass | Teal abstract rug; model screening passed, not a general guarantee of exact visual accuracy |

Direct visual inspection confirmed the chair/loveseat, table-shape/finish and
missing-lamp mismatches. Do not reinterpret these failures as permission to
change the source catalog to fit incorrect pictures. Original media is retained.
No bulk image generation or remote import was started by this calibration.

The authenticated image request path is now runtime-tested. That does not certify
the model's accuracy across the catalog. A model's self-reported confidence is only
a screening signal, not proof of visual correctness. Inspect representative results
and every failed/uncertain reference. Repair rejected references in a separate
versioned media directory, then rebuild the job manifest and audit their new hashes.

After reference approval, generate in a **new** output directory:

```sh
HF_HUB_OFFLINE=1 /Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/generate_reference_images.py \
  --jobs var/wands/realism-full-v4/image-jobs.jsonl \
  --reference-audit var/wands/reference-audit.jsonl \
  --output-dir var/wands/realism-media-final
```

Use `--limit 10` for a bounded batch or repeated `--sku` to select particular
jobs. `--dry-run --json` validates reference hashes and reports the queue without
loading the model; it does not grant reference approval. The first two single-
reference edits took about 9 and 10 seconds; the four-reference bundle took
about 25 seconds. Full generation is therefore a many-hour job, not complete yet.

```sh
tail -f var/wands/realism-media-final/generation.log
```

The same command resumes completed images only when request and image hashes
match. A directory lock prevents concurrent writers. Original media is never
overwritten. Stale or untracked output images fail closed; preserve the directory
and resolve the mismatch rather than deleting evidence. Generation stops on the
first runtime failure. Generated status is separate from visual acceptance.

## Remote import gate

Before importing at `relevance.comtom.lab`:

1. Complete reference repairs, image generation and output visual acceptance.
2. Obtain a fresh remote snapshot of precisely the affected WANDS records,
   attributes, bundle options, prices, inventory and media associations.
3. Validate the CSVs against the installed Magento importer and dry-run counts.
   The new `AddRealismAttributes` data patch must be installed first. Its syntax
   is checked locally, but its runtime behavior is not yet live-verified.
4. Create a remote backup and inverse operation based on that snapshot. The
   `rollback.*.local-artifacts.csv` files are **not** a complete production rollback:
   they cannot capture intervening remote changes or defaults absent from inputs.
5. Obtain explicit approval for the exact deploy/import scope and destination.
6. Import with update semantics, never delete/replace the catalog. Ensure old
   bundle options are replaced narrowly rather than appended to the new roles.
7. Reindex and verify search, category/PDP rendering, swatches, prices, bundle
   choices and stock behavior. Update media only after visual acceptance.

The initial realism change set was committed as `d85f8c7`. Subsequent repair and
bulk tooling is a separate commit. Neither commit implies a push or deployment.

## Verification

```sh
python3 -m unittest discover -s dev/tools/wands_catalog/tests -p 'test_*.py'
php -l app/code/RocketWeb/LabCatalog/Setup/Patch/Data/AddRealismAttributes.php
git diff --check
```

The suite covers source preservation, HTML escaping, family/pack pricing,
stock derivation, class matching, source conflicts, quiet reproducibility,
reference hash approvals, path containment and image resume integrity. Audit
regressions cover truncated/filtered completions, malformed JSON, bounded retry,
interrupted-log resume, explicit credential loading and quiet secret-safe errors.
Model-returned fields cannot overwrite the pinned reference path, image hash or
source evidence. The initial suite had 72 passing tests; PHP syntax lint and
`git diff --check` also pass. These are local checks, not Magento runtime acceptance.
