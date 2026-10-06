# Human image review

Review images by source, with the product name, brief and specifications beside
both attempts. **Keep** saves visual approval. **Redo** requires a note describing
what to change. Choices save automatically and the interface advances to the
next image. Automated rejection reasons stay in the evidence, outside the UI.

The usual local address is <http://127.0.0.1:8877/> when the review server is
running. The completed expansion's generation workers are stopped; opening or
starting review does not restart generation or change either installed catalog.

## Review quickly

| Action | Control |
| --- | --- |
| Keep the current image | **K** or Keep |
| Request a correction | **R** or Redo, then add a specific note |
| Save the correction and advance | **Enter**; **Shift+Enter** adds a newline |
| Skip without deciding | **N** or Skip |
| Move between images | Arrow keys or navigation buttons |
| Undo the last choice in this page | **U** or Undo |
| Inspect image detail | Click either image to open its full-size version |
| Revisit choices | Filter by department, source, product text or decision |

For corrections, identify the product part and the desired result: “Make the
riser base terracotta; keep the computer monitor black.” Include missing parts,
wrong material, geometry or piece count when relevant. Every image must still
have no visible text, numbers or measurements. Specifications beside the image
are product data, not instructions to draw measurements.

Source images for standalone repairs are labelled **Previous attempt**. Keep is
a decision about those exact image bytes. If the image or worker state changes
before saving, refresh and inspect the new image instead of forcing the old choice.

See [the correction record](FEEDBACK-REPROCESSING.md) for patterns from October 2
and 3, [the expansion guide](docs/EXPANSION.md) for acceptance contracts, or the
[documentation index](docs/README.md) for other workflows. Details below are for
operators and developers.

## Start the local server

Check the saved `server.pid`, actual process command and URL before starting
another process. A PID receipt can be stale after a restart. Use the durable
output directory, retaining the existing feedback database:

```sh
/Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/review_rejected_images.py \
  --run var/catalog-expansion-20260918/run-v3 \
  --output var/catalog-expansion-20260918/human-image-review --port 8877
```

Run from this repository root. The page persists choices and note drafts on
reload. Stopping the foreground review server does not stop image workers.
A completed run may have no remaining unreviewed items.

## Feedback storage

Paths below are relative to
`var/catalog-expansion-20260918/human-image-review/`, excluded from Git:

| File | Contents |
| --- | --- |
| `feedback.sqlite` | Exact-image choices and append-only revision history |
| `feedback.jsonl` | Current choices, product briefs, source/image hashes, prompts, seeds, settings and original automated review |
| `feedback-summary.json` | On-demand outcome snapshot by product profile, material, color and generation lane, including exact Redo notes |
| `server.json`, `server.pid` | Server URL, run, database and process receipt |
| `server.log` | Launcher output when redirected to this file; the foreground command itself logs to the terminal |

The first UI was opened during testing and immediately used for real reviews.
Its live storage was backed up and moved into this durable workspace. The earlier
`/tmp/wands-human-review-browser-test` path was a symlink used by that process;
it is historical setup, not the restart target. Do not discard the real feedback
as a disposable test dataset. Unit-test fixtures use separate temporary choices.

## Save semantics and local HTTP boundary

The interface reads the generation ledger without rewriting job acceptance.
Keep saves a human visual approval; Redo saves a correction request. Neither
silently reopens exhausted attempts, changes in-flight prompts, accepts a
candidate or deploys products. A subsequent correction/acceptance tool consumes
those decisions under its own exact-input checks.

The save handler checks image/source hashes, job state and decision revision.
Stale images and conflicting browser tabs cannot silently replace another choice.
Image reads are restricted to allowed paths and recheck byte hashes. The server
binds to loopback and requires the local Host, Origin and per-process review token
for writes. It is a local review tool, not a remote multi-user service.

## Summarize and use corrections

This command reads feedback and writes a summary without starting the server or
changing the generation ledger:

```sh
/Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/review_rejected_images.py \
  --run var/catalog-expansion-20260918/run-v3 \
  --output var/catalog-expansion-20260918/human-image-review --summarize
```

Identify recurring concrete defects in Redo notes, and compare human-kept images
with model holds when evaluating reviewer calibration. Counts alone do not prove
that automated QA was wrong. Compare changes on representative Keep/Redo examples
under equal conditions; retain exact hashes, prompts, prior attempts and Keeps.
The dataset supplies evidence for corrections, not automatic training or a model
change.

The October 2 pass applied 44 Redo decisions to 99 matching unapproved jobs. All
99 were accepted by October 3. The [historical correction record](FEEDBACK-REPROCESSING.md)
contains immutable admission scope, product patches, evidence and scoped rollback.
A new feedback pass needs its own reconciled preview; it must not mutate sealed
packets or restore an older ledger over subsequent progress.

## Verification

```sh
/Users/matt/code/mageos-latest/.venv-imagegen/bin/python -m unittest discover \
  -s dev/tools/wands_catalog/tests -p 'test_human_image_review.py' -v
```

The recorded interface verification covered persistence, exact source grouping,
required notes, undo history, stale images/sources, worker-state changes, path
restrictions and local HTTP writes. Browser checks also exercised actual images,
Keep/Redo, automatic advance, undo and saved choices after reload. These are
recorded results; rerun relevant checks after interface changes.
