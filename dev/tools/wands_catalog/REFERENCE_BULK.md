# Repaired references and gated bulk generation

Run from `/Users/matt/code/rocket-search/.worktrees/wands-merchandising`.
This workflow generates local staging media only. It does not import products,
overwrite original media, push Git commits or deploy to the remote store.

## Repair scope

The reviewed prompt set is `reference-repairs.json`. Each prompt is pinned to
the original product's source-evidence hash. It corrects these four references:

- `WANDS-042963`: blue tufted velvet task chair with silver caster base.
- `WANDS-014081`: two-seat light-brown reclining loveseat, not an armchair.
- `WANDS-023338`: light-gray octagonal wood block coffee table.
- `WANDS-017261`: a matched pair of gray table lamps with oatmeal empire shades.

Generate with the previously selected local MFLUX runtime:

```sh
HF_HUB_OFFLINE=1 /Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/repair_reference_images.py \
  --plan dev/tools/wands_catalog/reference-repairs.json \
  --source-products /Users/matt/code/rocket-search/data/raw/wands/product.csv \
  --output-dir var/wands/reference-repairs-v2
```

Output goes to `generation.log`. Successful files have request/image hashes in
`generation-events.jsonl`. Existing files are never overwritten. Changed prompts,
source facts or image hashes require a fresh versioned directory. Regeneration
is not acceptance: inspect the images and run the vision audit before use.
The selected repaired JPEGs and generation provenance are also retained in
`assets/reference-repairs-v2/` beside this document, so they travel with the
second Git commit. A fresh run can use that directory as `--repair-dir`.

Validation completed on September 4, 2026: all four repaired references and the
unchanged rug passed the structured oMLX audit. A black chair variant preserved
the repaired geometry and tufting. The first repaired bundle pilot still omitted
one lamp; the revised explicit-count prompt produced an accepted pilot containing
one loveseat, one octagonal table, one rug and both lamps. That accepted pilot is
`var/wands/repaired-pilot-v3/WANDS-BUNDLE-001-REALISM.jpg`. This is one bundle's
acceptance, not acceptance of all future bundle outputs. The code suite passes
80 tests, and PHP syntax lint and whitespace checks pass.

## Prepare an immutable queue

```sh
python3 dev/tools/wands_catalog/bulk_reference_images.py \
  --jobs var/wands/realism-full-v4/image-jobs.jsonl \
  --source-products /Users/matt/code/rocket-search/data/raw/wands/product.csv \
  --repair-plan dev/tools/wands_catalog/reference-repairs.json \
  --repair-dir var/wands/reference-repairs-v2 \
  --run-dir var/wands/bulk-realism-v3 \
  --image-python /Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  --model Qwen3.8-27B-8bit \
  --env-file /Users/matt/code/.env \
  --prepare-only
```

The queue contains 10,850 output jobs using 2,196 distinct references. Repair
files override only matching source SKUs in the new manifest. Original manifests
and media remain unchanged. Multi-image bundle prompts preserve the entire count
of any component sold as a set.

Before the first bulk run, audit the repaired references using the new queue:

```sh
python3 dev/tools/wands_catalog/audit_reference_images.py \
  --jobs var/wands/bulk-realism-v3/jobs.jsonl \
  --source-products /Users/matt/code/rocket-search/data/raw/wands/product.csv \
  --output var/wands/bulk-realism-v3/reference-audit.jsonl \
  --model Qwen3.8-27B-8bit --env-file /Users/matt/code/.env \
  --reference-id 42963 --reference-id 14081 --reference-id 23338 \
  --reference-id 17261 --reference-id 17873
```

## Run and resume

Repeat the prepare command **without `--prepare-only`** to start or resume.
The default sequence is:

1. Generate jobs whose current references already have matching approvals.
2. Audit up to 20 additional references through local oMLX.
3. Generate newly eligible jobs through local MFLUX.
4. Repeat until every reference has been screened.

Each bundle requires every component to pass. Approvals must match the model,
audit policy, prompt, source facts and image hash, have a normal completion,
have confidence at least 0.90, and contain no issues. A later failed decision
revokes an earlier approval. Rejected/uncertain references are never silently
approved to keep the batch moving. They are listed in `withheld-jobs.jsonl` at
the end. The full 10,850 jobs will not all generate if further bad references
are found. Those require another reviewed repair set and versioned run.
The audit requests a bounded JSON schema and disables thinking per request,
without changing global oMLX settings. This prevents the observed failure where
free-form deliberation consumed the token budget instead of returning a verdict.
The parser still independently validates the result even if the server does not
enforce the schema. Request/model policy changes invalidate earlier approvals.

The run holds directory/audit locks, refuses changed run inputs and checks
existing generated-image hashes on resume. A service or generation error stops
the run. Resolve the error and repeat the same command; completed work is retained.
The command resumes after a reboot but does not automatically restart itself.

```sh
tail -f var/wands/bulk-realism-v3/bulk.log
tail -f var/wands/bulk-realism-v3/media/generation.log
```

`status.json` exposes the process ID and current stage. Output remains quiet by
default, including native model output. oMLX credentials are loaded only from
the explicitly supplied source; credential values are not written to artifacts.

Generated images remain **pending visual acceptance**. Inspect representative
variants and every bundle before a later, separately authorized remote import.
Do not treat a completed generator process as storefront acceptance.
