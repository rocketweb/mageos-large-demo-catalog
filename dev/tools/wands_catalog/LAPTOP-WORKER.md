# Linux laptop image worker

The additional worker uses `root@192.168.1.7`, hostname `laptop`, with an NVIDIA
RTX 4080 Laptop GPU (12,282 MiB VRAM), 32 GB system RAM and AC power. Everything
installed for this task lives under `/root/wands-image-worker`. Existing N.O.M.A.D.
containers, models, credentials, system Python and drivers are preserved.

## Runtime and benchmark

The worker runs the same pinned FLUX.2 Klein 4B source model through Diffusers
on CUDA, using BF16 with model CPU offloading. It does not use MFLUX's 4-bit MLX
runtime, and byte-identical output across these backends is not expected.
The renderer preserves the frozen prompt, seed, four steps, guidance and 768-square
output. No text or measurement exception is permitted.

`TORCH_DISABLE_NATIVE_JIT=1` selects prebuilt PyTorch operations. PyTorch 2.14's
optional native DSL path otherwise requires an absent C compiler and Python
development headers. No system compiler was installed to work around this.

The environment uses PyTorch 2.14.0/CUDA 13.0, Diffusers 0.40.0, Transformers
5.17.0, Accelerate 1.15.0, Pillow 12.3.0 and Safetensors 0.8.0. Full dependency
versions are in `laptop-setup/requirements.lock`. Source-model files must match
the existing run's hashes; the additional Diffusers model index and scheduler
configuration were fetched from the same pinned revision. The renderer verifies
model, package and code hashes and runs offline after provisioning.

Evidence is under `var/catalog-expansion-20260918/laptop-setup/`: environment
pins, a six-image generation/edit benchmark, results and OCR/vision review.
Benchmark images are separate from the live job ledger and never auto-imported.
A renderer admission receipt is required before reserving live jobs.

September 29 verification: four edits averaged 11.74475 seconds/image; two
standalone generations averaged 7.6955 seconds/image, excluding model loading,
transfers and quality review. Peak allocated GPU memory was 9,204,417,024 bytes.
Five of six passed automated review; direct inspection held two additional material
changes, leaving three accepted benchmark samples and three rejected samples.
No displayed measurements or text were observed. These six samples establish
functionality, not a catalog-wide quality rate or completion estimate.

Live batch `dc8b80c6793545d29e7f269afe72b00f` completed all four reference edits and
imported them as second attempts into the central `generated` queue with exact
CUDA provenance. Direct inspection held two table images for invented chains;
the two chairs remained queued for ordinary central review. No image received
an acceptance override. Continuous operation uses 16-image laptop batches.

The existing shared prompt's generic chain/ring preservation instruction is a
suspected cause of invented hardware in both MFLUX and CUDA table images.
Hash-bound direct correction notes preserve the observed failures. A general
prompt-policy correction remains separate work and must account for already
reserved packets before changing the shared planner.

Verification: `python -m unittest discover -s dev/tools/wands_catalog/tests`
ran 606 tests, with 600 passing and six skipped. The output is saved as
`var/catalog-expansion-20260918/tests-laptop-worker.log`.

## Concurrent operation

```sh
/Users/matt/code/mageos-latest/.venv-imagegen/bin/python \
  dev/tools/wands_catalog/run_remote_image_batches.py \
  --run var/catalog-expansion-20260918/run-v3 \
  --target root@192.168.1.7 --remote-root /root/wands-image-worker \
  --worker-id laptop --batch 16
```

The Studio owns the only catalog ledger. Each remote worker has at most one
outstanding batch, distinct coordinator locks, logs, stop files and reservations.
Legacy batches without worker ownership remain mini batches. The native Studio
generator skips all reserved jobs. Generation and import hold the common ledger
generation lock. Reconnection resumes exact packet bytes; per-image hashes and
renderer locks prevent duplicate generation. The Linux renderer uses a temporary
`systemd-inhibit` process to prevent sleep while working.

The laptop's local state is `run-v3/remote-laptop-state.json`, with activity in
`remote-laptop-console.log`. Its stop file is `REMOTE_STOP-laptop`. The mini keeps
`remote-worker-state.json`, `remote-worker-console.log` and `REMOTE_STOP`.
The Studio keeps its own `worker-state.json` and `STOP` file.

Schema-3 packets additionally pin the admitted CUDA environment. Return imports
must match that profile, model, job ownership, source approval, candidate hash,
attempt budget and original generation inputs. Metadata records the actual
unquantized BF16 renderer; imports always enter `generated` for central QA.
Changing or removing the admission receipt prevents new reservations/imports.

Before starting two remote workers, restart the old mini coordinator so it knows
how to separate ownership. Stop at a safe boundary and retain its outstanding
manifest; the updated coordinator can resume it. Never let an old coordinator
reserve work while a second worker has outstanding batches.

## Stop and rollback

Set only `run-v3/REMOTE_STOP-laptop` to stop the laptop coordinator. If a renderer
survived disconnection, allow it to finish before cancelling the reservation.
Once the coordinator and renderer are stopped, `remote_image_batch.py cancel`
restores reserved jobs to their exact previous states and keeps image history.
Leave completed imports in the central QA queue; stopping a worker does not
invalidate legitimate completed images or waive rejection holds.

Pre-change coordinator code and a consistent SQLite snapshot are preserved in
`laptop-setup/before-cuda/` and `laptop-setup/ledger-before-multi-worker.sqlite`.
Do not restore that older database over later progress. Prefer the scoped
reservation cancellation above. Reverting the coordinator code requires stopping
both remote workers and resolving laptop reservations first.
