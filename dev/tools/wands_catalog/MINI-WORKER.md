# Mac mini image worker

The mini was an additional Apple Silicon renderer, working alongside the Studio. The completed run is stopped. The setup and benchmarks below preserve its admitted environment; timings and PIDs are historical.

| Operator detail | Rule |
| --- | --- |
| Ownership | One outstanding sealed batch per worker; Studio owns the ledger |
| Acceptance | Returned images enter central review, never automatic acceptance |
| Safe stop | Set `REMOTE_STOP` in `run-v3/`; wait for renderer, transfer and import completion |
| Restart | Verify actual processes, locks and reservations; resume the same packet |
| Current project | Do not restart completed generation just to inspect status |

See [the expansion guide](docs/EXPANSION.md) for current scope and shared contracts.
The detailed setup, operation and recovery notes below preserve the original
worker evidence. Do not use a historical PID as a live process identifier.

## Recorded setup and benchmark context

September 29 update: both workers resumed after adding reference-based variants
and within-budget product corrections to the mini. The mini no longer exits
permanently when it must wait for source approvals. Continuous mini batches now
use `--batch 32` to shorten edit batches and transfer intervals; the Studio keeps
`--batch 64`. PID files and advancing outputs are the current runtime evidence.

The four-image edit comparison produced byte-identical JPEGs on both machines.
Mean generation time was 45.968 seconds/image on the mini and 9.138 on the Studio,
excluding startup, transfers and review. Mini peak MLX-tracked memory was
15,351,227,714 bytes. OCR/vision review passed two and rejected two; direct holds
preserve the chandelier geometry and coffee-table added-chain findings. Passing
comparison images still enter normal central review, without acceptance overrides.
Evidence: `var/catalog-expansion-20260918/mini-setup/edit-benchmark.json` and batch
`119f5a753eab40fb99c32a7610edd611/direct-review.json`. The complete local suite ran
596 tests: 590 passed and six skipped (`tests-mini-edits.log`). Exhausted retries
still require diagnosed correction; this change does not reset their budgets.
The mini's previous renderer is preserved as
`code/remote_image_batch.before-edits-20260929.py`.

## Original setup and standalone benchmark (September 22)

As of September 22, both the Studio and mini image workers are active. The mini
passed a four-image benchmark and central quality review, and continuous
64-image batches have started. This is image generation, not a store deployment.

Verified destination: `matt@192.168.1.115`, hostname `Matts-Mini-2.localdomain`,
Apple M4 Pro, **24 GiB RAM**, macOS 27.0. The machine reported 18 GiB free on its
internal disk and no external data drive. The user freed space, and 78 GiB was
verified before provisioning. The runtime and pinned model are now installed.
Do not delete unrelated existing files.

The user explicitly approved adding the Studio's existing public SSH key to the
mini's `matt` account. It was added through their existing iTerm SSH session,
and independent SSH authentication succeeded afterward. Existing authorized keys
were preserved, with `~/.ssh/authorized_keys.before-wands-20260922` created if the
file existed. To revoke the added access, remove only the matching public key
from `authorized_keys`, retaining any other keys. Public-key fingerprint:
`SHA256:9pPZ8xBc6eO4mINgQ0xm+r5/FywKbc3okto3j+PIXDs`.

## Installed runtime and verified benchmark

Use one reusable SSH connection with `ControlPath=/tmp/codex-wands-mini-%C`.
The isolated worker root is `/Users/matt/wands-image-worker`. It can reside on an
approved external drive through a home-directory link if that becomes necessary.
Keep one Python 3.12.12 virtual environment in `.venv`; use the already installed
`/Users/matt/.local/bin/uv` to provision it. The pinned requirements and exact
model-file transfer list are under `var/catalog-expansion-20260918/mini-setup/`.
Copy the original pinned FLUX.2 Klein snapshot files into `model/`, following the
source cache symlinks. Do not change or re-quantize the source model to save disk.
The renderer verifies every model-file hash and the pinned generation packages.

Only `remote_image_batch.py` and `image_policy.py` are needed in the mini's `code/`
directory. The mini receives assigned prompts and generates RGB JPEGs. It does
not receive the catalog database, review API key or store credentials. The
measurement prohibition, first-attempt painted-material instruction, seed and
generation settings are identical to the central pipeline. One model instance
generates standalone images or reference-based edits. Product retries share the
Studio's bounded retry and direct-observation rules. Retained-source repairs
and all acceptance review remain on the Studio.

The Studio supervisor was restarted at a safe phase boundary to load lock
contention handling, bounded review-backlog draining and waiting for remote jobs.
Never interrupt a live generation/import transaction during future restarts.
Preserve STOP-file intent, ensure the old supervisor and child have exited, then
resume the existing run; no third catalog or new candidate is needed.

The completed benchmark used four diverse jobs and one batch:

```sh
/Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/run_remote_image_batches.py \
  --run var/catalog-expansion-20260918/run-v3 \
  --target matt@192.168.1.115 \
  --remote-root /Users/matt/wands-image-worker --batch 4 --max-batches 1
```

All 16 transferred model files matched their frozen hashes. The mini and Studio
used the same four prompts, seeds and settings, producing byte-identical JPEGs
for every image. Mean generation time was 20.806 seconds/image on the mini and
4.18975 seconds/image on the Studio, excluding model load and transfer time.
The mini's MLX-tracked peak GPU memory was 14.233 GiB. These are four-image sample
measurements, not a full-catalog throughput or completion-time guarantee.

Direct inspection and central OCR/vision review agreed: three passed; one
canister-rack image was rejected for including an unrequested cabinet door.
No displayed text or measurements were observed in this sample. The rejected
image received a hash-bound direct hold and remains subject to normal correction.
Benchmark evidence: `var/catalog-expansion-20260918/mini-setup/benchmark.json`,
the Studio comparison images, and remote batch
`64b027657f494fae886a98b7ca9f42f7/{returned/results.json,direct-review.json}`.

Continuous generation uses the same coordinator command with `--batch 64` and
without `--max-batches`. Studio supervisor PID 43769 and mini coordinator PID
43771 were verified at startup. Always refresh the PID files and actual process
state before relying on these historical numbers. Each has a process-scoped
Studio caffeinate helper; the remote renderer also runs under caffeinate.

## Reservation and recovery

September 26 recovery update: the coordinator now retries SSH connection failures
(exit 255), selected rsync connection/timeouts, and the renderer's explicit busy
exit (73) once per minute, for at most 30 retries per operation. The state file
shows connection/renderer waiting and the retry count. `REMOTE_STOP` interrupts
the backoff within five seconds. Other model, packet and validation failures
still stop immediately. Retries preserve the exact reserved batch and image
hashes; a renderer that survived a disconnected SSH session retains its lock,
so a reconnect cannot start duplicate generation. This handles interruptions;
the underlying cause of the recurring SSH disconnects remains unconfirmed.

The mini's previous renderer is preserved at
`code/remote_image_batch.before-reconnect-20260926.py`. The targeted regression
suite (`test_remote_image*.py`) passed 17 tests, including transport recovery,
bounded retries, STOP handling and refusal to render while its lock is held.

`remote_image_batch.py reserve` acquires the Studio generation lock and reserves
eligible non-pilot first attempts, reference-based variants, and corrections.
Both workers call the same `generation_input` planner for accepted-source
selection, measurement-free prompts, direct-observation instructions, seeds and
retry budgets. Exhausted retries remain held for diagnosed correction, and no
acceptance policy is relaxed. The native generator skips the `remote_reserved`
state. There is at most one outstanding remote batch per worker. On
restart the coordinator reuses its exact manifest and the mini reuses completed,
hash-verified images. Each remote batch has a file lock against duplicate renderers.

Imports verify the batch pin, ownership, original request, generation settings,
image hashes, image encoding/dimensions and complete result set. They preserve
attempt metadata and set state `generated`, never `accepted`. A conflicting or
stale return cannot overwrite another attempt. Completed imports are idempotent.
Lock contention retries safely instead of stopping the central supervisor.

Set `run-v3/REMOTE_STOP` to stop the coordinator between batches. It is independent
of the central worker's STOP file. A failed transfer leaves its reservation intact
for retry; it never releases work speculatively. If abandoning a batch, stop the
coordinator first, then use `remote_image_batch.py cancel --run ... --batch-id ...`.
Cancellation rejects late results from that batch. Schema-1 reservations return
to pending. Schema-2 cancellation restores each job's prior state and preserves
its attempt count and previous image. Image files and audit evidence remain available.

Schema-2 packets include hash-verified reference snapshots under `references/`.
The mini verifies those bytes before passing them to `Flux2KleinEdit`; batches use
one model mode to limit memory. Returned images include the actual attempt number
and source hash. Imports recheck current source acceptance, source bytes, prompts,
seed, previous candidate and reservation ownership before entering the normal QA
queue. An invalidated source rejects the batch instead of accepting stale work.
Imported history remains idempotent when the same job is reserved for a later
attempt. Existing schema-1 standalone packets remain readable.

When eligible edits temporarily run out while source jobs are still pending,
the coordinator reports `waiting_for_eligible_images` and checks once per minute.
`REMOTE_STOP` remains effective during that wait. A temporary source-review delay
therefore no longer permanently removes the mini from the run.

Local state is in `remote-worker-state.json`, `remote-worker-console.log` and
`remote-batches/<id>/`; mini results are in `batches/<id>/output/`. Check real
processes and advancing counts, not only PID or state files.

580 tests ran locally: 574 passed, six skipped. Evidence:
`var/catalog-expansion-20260918/tests-mini-live-setup.log`. The live comparison
also reproduced and fixed a model-path check that incorrectly rejected legitimate
Hugging Face cache links. Model hashes still bind the files, and parent traversal
is rejected.

Model transfer, benchmark, four-image import and quality review are complete.
The first 64-image batch is `d512fbfd33004ee0a28253ca54a60303`. Both existing
catalog installations remain unchanged; source changes are uncommitted.
