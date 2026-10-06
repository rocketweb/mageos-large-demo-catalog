# Human image review

Matt requested a fast review interface with brief product details, Keep / Redo,
a required correction note for Redo, and source grouping. Automated rejection
reasons are retained as evidence but are not shown in the interface.

The local page is at <http://127.0.0.1:8877/>. Its feedback is stored in
`var/catalog-expansion-20260918/human-image-review/`:

- `feedback.sqlite`: exact-image choices and an append-only revision history.
- `feedback.jsonl`: current choices with product briefs, source/image hashes,
  generation prompts, seeds, settings, and the original automated review.
- `feedback-summary.json`: an on-demand snapshot by product type, material,
  target color and generation lane, plus the exact Redo notes.
- `server.json` / `server.pid` / `server.log`: current interface receipt and log.

The first interface was opened during testing and Matt immediately began using
it. Its live storage was backed up and moved into this workspace, retaining the
same URL and all existing decisions. The running process still uses
`/tmp/wands-human-review-browser-test`, which is a symlink to the durable folder.
After a reboot, use the durable output path below. Do not discard this dataset
as test data. The separate unit-test fixtures contain disposable test choices.

```sh
/Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/review_rejected_images.py \
  --run var/catalog-expansion-20260918/run-v3 \
  --output var/catalog-expansion-20260918/human-image-review --port 8877
```

Check `server.pid`, the actual process command and the URL before starting
another process. The existing page persists choices and note drafts on reload.

Keyboard: **K** keeps the current image, **R** opens the correction-note field,
**Enter** saves that note and advances, **Shift+Enter** adds a newline,
**N** skips, arrow keys navigate, and **U** undoes the last choice in that page.
Filters allow revisiting kept images and Redo notes. Clicking either photograph
opens its full-size version. Source images for standalone repairs are explicitly
labelled "Previous attempt".

The interface reads the generation ledger without writing it. Keep is a saved
human visual approval; Redo is a saved correction request. Neither action
silently rewrites automated acceptance, reopens exhausted attempts, changes
in-flight prompts or deploys a catalog. A subsequent correction pass can use
the exact choices, with the existing image-text/measurement ban still enforced.
Image bytes, current job state, and decision revisions are checked at save time;
stale images and conflicting browser tabs cannot silently overwrite a choice.

To prepare a summary for the next pass:

```sh
/Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/review_rejected_images.py \
  --run var/catalog-expansion-20260918/run-v3 --summarize
```

Use the raw feedback to identify concrete recurring correction needs, and compare
human-kept images with model holds to find candidates for QA calibration.
Do not assume every human Keep proves a QA false positive. Evaluate proposed
prompt or reviewer changes on representative Keep / Redo examples under equal
conditions. Retain exact prior hashes, prompts and attempt histories. This
dataset supplies feedback; it does not automatically train or change a model.

The October 2 correction pass applied the next 44 Redo decisions to 99 matching
unapproved jobs. See [the correction record](FEEDBACK-REPROCESSING.md) for its
patterns, queue scope, verification and rollback procedure.

Validation:

```sh
/Users/matt/code/mageos-latest/.venv-imagegen/bin/python -m unittest discover \
  -s dev/tools/wands_catalog/tests -p 'test_human_image_review.py' -v
```

Eleven tests cover persistence, exact source grouping, required correction notes,
undo history, stale images/sources, worker-state changes, path restrictions,
and local HTTP write protections. The live page was also verified with actual
image loading, Keep/Redo, automatic advance, undo and saved choices on reload.
