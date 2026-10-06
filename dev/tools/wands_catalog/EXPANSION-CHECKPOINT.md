# Approved catalog doubling: implementation checkpoint

## Completed installation, 2026-10-06T18:17:45Z

The doubled catalog is installed and verified on the two existing destinations:
Studio and Comtom. Each now has **107,688 WANDS product records**: 103,643
simple products, 3,995 configurable parents and 50 bundles, with 27,736
configurable parent-child links. No third store was created and no products
were deleted. Required image generation, retained-image repairs and category
checks have finished.

Each store passed database acceptance, 15 unsaved cart-model checks and 28
rendered storefront checks. Original product IDs, existing stock, unrelated
products and protected store data were preserved. Search results were verified
nonempty; search ranking, checkout and payments are not qualified by these checks.

The accepted export contains 95,401 distinct JPEGs. Each store has 107,455
accepted media assignments and 322,365 verified image roles. There are 233
explicit disabled media exclusions: 213 reviewed quarantined products and 20
original disabled, imageless records. All 20 affected configurable families and
two affected bundles passed dependency checks. Measurements remain product
data only; the shared image policy prohibits visible measurements and text.

Private, ignored completion evidence is recorded in
`var/catalog-expansion-20260918/completion-authorized-20261004/completion-acceptance.json`.
It pins database, cart, browser and media acceptance evidence for both stores,
plus private backup and ordered inverse receipts. These artifacts contain
installation-specific data and are not shipped in Git. Image workers are stopped.

Source tooling and documentation can be committed independently of distribution.
The expanded media archive has not been published as a release asset. Existing
release downloads retain their original profile and counts. For remaining
testing coverage, see [the product coverage audit](PRODUCT-COVERAGE.md).

Everything below is a historical checkpoint, including its process IDs,
unresolved counts and statements that installation had not yet started.

## Historical checkpoint, 2026-10-06T01:11:15.599527+00:00

Fresh status after Studio restart: 48,816/48,844 new images accepted, 442
existing-image briefs unresolved (15 resolved since the preceding status), two
category checks unresolved, and 112 GiB free on Studio. All former coordinators
and installer were dead. The authenticated oMLX model endpoint was verified
available. Resumed original worker commands using saved sealed packets:
Studio PID 5785, laptop PID 5786, mini PID 5787. Installer PID 5788 uses a fresh
private evidence directory, automatic-installation-post-reboot-20261006T010945Z,
because the installer intentionally rejects reused output directories. Prior
installer evidence confirmed store_imports_started=false; no partial imports
were retried. Current installer is waiting_for_accepted_export with no imports.
Exact receipts: post-reboot-workers-restarted.json and
post-reboot-verified-status.json. The snapshots and historical PIDs below are
superseded by this fresh recovery note; preserve their evidence.

The user explicitly authorized finishing the project and removing procedural
retry/manual approval gates as needed. The measurement/text ban, exact product
identity, saved human Keeps, original files and protected store data remain.
The project is **not yet complete**. There is no full accepted export and no
product/media catalog import on either store.

The full audit at 2026-10-06T00:15:36.940891+00:00 reports
48,816 of 48,844 new images accepted (28 unresolved), 457 existing-image briefs
unresolved and two unresolved category checks. New-image acceptance excludes
existing-image remediation. Since the morning audit, 691 retained briefs were
resolved in 13.84 hours. Only 10 of the last 300 repair reviews passed at the
status snapshot, so the previous seven-hour estimate is not reliable for the
remaining difficult targets. Read live audit and worker states before reporting
current counts. Studio has 55 GiB free at the evening check.

A tested render-only correction now supplies positive sale-item geometry for
122 of the 457 unresolved targets at that snapshot: separate textile sale items,
flat cardboard cutouts, flexible LED strips, appliance pairs, complete table
sets, multi-panel artwork, faucet components and electrical plate openings.
For those explicit recipes, rejected-object diagnostic sentences are omitted
from render prompts; relevant missing-part notes and manual corrections remain.
Frozen briefs, product data, exact component counts, image history, human Keeps,
OCR/text ban and all product/category QA are unchanged. No acceptance or catalog
rows were directly changed by this improvement. The long-term acceptance rate
after this change has not yet been measured. All 457 prompts passed the token
preflight, maximum 417 tokens against the 512-token limit. Full suite:
818 tests ran, six skipped, no failures. The focused recipe regression tests
were watched fail before implementation and pass afterward. Evidence:
`sale-unit-recipes-preview.json`, `sale-unit-token-preflight.json`,
`tests-sale-unit-recipes-verified.log`.

Workers checkpoint-stopped, preserved and imported their sealed batches with
unchanged prompt code, and resumed only after zero reserved packets and free
coordinator locks were verified. Current Studio PID 79913, laptop PID 79914,
mini PID 79915; exact commands and receipts in
`sale-unit-recipes-workers-restarted.json`. A rollback source copy is in
`sale-unit-recipes-before/authorized_completion.py`. Installer PID 47951
continues waiting for the accepted export; no catalog imports have started.

Both existing stores have the reviewed importer/module preparation installed,
DI compiled, schema/options verified, and first 1,000 new and existing-product
CSV rows independently validated with zero errors. Neither product data nor
media has been imported yet. Existing WANDS content will be refreshed on both
stores, including Comtom's prices and descriptions. Exact reviewed deltas:
Studio inserts 64,694, updates 42,994 and converts 1,995 existing parents;
Comtom inserts 53,844 and updates all 53,844 existing products. Zero products
are deleted. Product IDs, existing stock, unrelated products and protected
configuration/customer/order/cart data must be preserved. Only these existing
destinations are used, with no third install, commit, push or publication.

Automatic completion coordinator PID 47951 runs
`finish_expansion_project.py --watch --apply`. Its exact command and private log
are in `completion-authorized-20261004/automatic-installation-started.json`.
Its state is in `automatic-installation-20261005/state.json`. It currently waits
for the full accepted export, then takes fresh private backups, stages immutable
accepted media, validates/applies native import batches, aligns three media
roles, curates/reindexes navigation, checks exact product/link/stock/protected
state, runs unsaved cart probes and rendered storefront acceptance, and records
an exact row inverse on success or partial failure. Failed partial imports are
never blindly retried. A run-wide installation lock prevents two coordinators
from applying concurrently. Original and staged media are never overwritten.
The accepted export alone is not installation completion; the final coordinator
must report both stores installed and verified.

Studio PID 68937 continues with annotation prompt cleanup. Remote workers
were checkpoint-stopped and resumed with fair retained repair allocation:
laptop PID 71968, mini PID 71969. Under authorized completion they now assign
two retained repair packets before each new-product packet, preserving any
existing sealed packet first. The mini and laptop have each reserved eight retained repair images.
The laptop first imported its previously sealed three-image new-product packet. Restart evidence is `remote-allocation-workers-restarted.json`.
The previous annotation restart receipt is also preserved. All renderers
use the approved incumbent runtimes. The cleanup removes literal unwanted
writing from defect diagnostics and the observed appliance/mattress branding
prefixes from render text only. Catalog titles and full QA briefs remain
unchanged. Appliance controls are explicitly plain and unmarked. All 2,615
current unresolved retained prompts passed the 512-token preflight, maximum 411.
Empty-top riser edits were inspected at full size and ordinary/category/source
QA passed for the gray and terracotta examples. The explicitly requested
terracotta-with-black-monitor example retains its separate plain black monitor.

Verification: 806 Python tests ran with six skips and no failures in
`tests-final-remote-allocation.log`; the allocation regression failed before
the fix and passed after it. Existing sealed packet preservation also passed.
Earlier checks are preserved in `tests-final-disproved-sources.log`;  annotation regressions were watched fail
before the fix and pass after it. Unsaved simple cart probes passed on both
stores, with protected data unchanged. Comtom's existing configurable family
also passed correct-child/price/missing-selection probes and rendered dropdown,
photo and cart-form checks, with zero saved quotes or cart submissions. These
are preparation checks, not acceptance of the expanded catalog. Complete final
acceptance still runs after the imports. Receipt directory:
`var/catalog-expansion-20260918/completion-authorized-20261004/`.

The source-revision scan now consults live human feedback only immediately
before changing a stale-source row. Unchanged variants require no individual
feedback scans. Existing reconciled Keeps are still skipped and unreconciled
live Keeps still prevent changes. On a private copy of the live ledger, 48,649
eligible rows scanned in 2.818 seconds, with zero feedback lookups, zero changed
sources and zero live ledger/image writes. This is a scheduling-scan benchmark,
not a full pipeline completion ETA. `source-scan-feedback-live-benchmark.json`
and the red/green source-revision regressions retain the evidence. The live
Studio moved into rendering, and mini/laptop coordinators imported further
batches after this change. The next snapshot showed 58 unconfirmed riser
variants; every one uses a source with an exact native functional-riser
certificate. Ordinary full target QA and category QA still apply, with certified
source geometry eligible for inheritance. No standalone riser awaits a separate
native inspection in that snapshot.

A source that loses acceptance now queues its non-kept variants as rejected,
without changing their images, attempts or prior review evidence. Rendering
remains blocked until a clean source is accepted. This fixes six stale accepted
rows found during live verification, gives their source repairs normal waiting-
product priority, and prevents an invalid source from leaving its dependents
misleadingly accepted. Scoped `reference-revisions.jsonl` events preserve prior
state/update time and both source pins; live and reconciled Keeps still win.
The regression failed before the fix and passed afterward. Studio subprocesses
load this change at phase boundaries without interrupting sealed remote packets.

## Historical checkpoints

October 3, 20:37 EDT: delegated recovery continued with saved previews, immutable
attempts and scoped rollback receipts. The current snapshot has 47,986 of
48,844 new images accepted, 3,684 retained-media briefs unresolved and 89
unresolved category images. General accepted-image counts are separate from
category and direct-inspection export gates. Export is still blocked; neither
existing catalog has been replaced.

Retained-media recovery registered 33 exact-brief copies, 107 matching two- or
three-table set copies, and 83 copies whose only name difference is a collection
prefix. Current ordinary QA accepted 29, 107 and 81 respectively: 217 accepted
replacements. Full target briefs and descriptive features were preserved. Native
inspection also disproved 65 older accepted brief records, including drawer
counts, fixture types and loveseats rendered as armchairs. Those exact brief and
image hashes are now held; unrelated briefs sharing pixels were preserved.

Living Room Table Sets now require a separate unprimed complete-table count.
The counting request does not include the expected quantity or product name.
Upgrading 120 older QA records retained 115 passes and rejected five mismatches.
Missing, mismatching or stale count evidence cannot pass export. The two new
regressions failed before the change and passed afterward. The full suite
passed 690 tests with six skips in `tests-table-count-full-escalated.log`;
`git diff --check` passed.

Riser recovery exposed category-review false positives for closed cabinets and
missing individual cubbies. The additional direct audits, rejection manifests
and source-pool evidence are in `completion-fixes-20261003/`. Two preserved-cubby
context pilots, six subsequent furniture-only color edits and two textured
bamboo color edits passed ordinary QA, independent category QA and native-size
inspection. Optional monitors remain plain black, including their compact
normal feet. Eight earlier context edits removed the required cubby and were
rejected without import. One white bamboo edit also failed ordinary QA and
remains staged. Exact source copies match construction, material and color,
require ordinary QA and category QA, and only then receive hash-bound direct
pixel-inspection evidence. V4 registered 79 such copies; V6 registered six
additional changed-source copies. The unused V5 preview was not applied because
nine proposals repeated the same failed image bytes. No general retry budget
was reset, no saved human Keep was overwritten, and no prior image was removed.

Studio supervisor PID 83949 was resumed after finite repairs and verified alive
in reference review. Mini and laptop coordinators remained alive, with 12 and
20 completed batches since their earlier restart, and were waiting for eligible
jobs at this checkpoint. Use live state files for subsequent activity. The
local review interface returned HTTP 200 and still contains Keep and Redo.
The reported thick side accent border is absent from the current HTML.
Artifacts and inverse rows remain under
`var/catalog-expansion-20260918/completion-fixes-20261003/`.

October 3 delegated completion pass: all 130 new half-round table jobs are now
accepted with exact-photo direct geometry evidence. The successful recovery
preserves a directly inspected D-shaped table in the same material, recolors
only its finish, and reuses the resulting photo only for matching construction,
material and color. Cross-material edits frequently produced quarter-round or
round tops and were rejected. Finite import previews, saved rows, source hashes,
ordinary OCR/vision results and direct receipts are retained under
`var/catalog-expansion-20260918/completion-fixes-20261003/`; all prior images
remain intact. No general retry budget was reset.

All 615 new work-cart jobs have accepted ordinary image QA. Eighteen revised
three-level carts additionally require an explicit unprimed shelf count of
three, following successful same-material reference pilots. The last rejected
two-level wooden cart was replaced with a directly inspected matching blue
wooden source and passed ordinary OCR and vision review. These job counts do
not imply direct inspection of every historically accepted cart.

Monitor riser automatic category passes falsely included upright panels,
colored monitors, tall cabinets, missing storage and monitor logos. Direct
inspection of 53 matching sources confirmed 33 and rejected 20. A further
587-photo review confirmed 337 and rejected 248, with two otherwise plausible
variants blocked by stale source hashes. The next 60-photo review confirmed
56 and rejected four. Exact matching source copies still require ordinary QA.
Export now also requires a hash-bound direct functional-riser certificate:
a separate riser with a broad horizontal load surface, correct furniture
finish, and any optional monitor plain black. No saved Keep was overwritten.
Earlier cubby-riser pilots did not establish a reliable wider repair recipe;
their attempts remain staged and unaccepted.

Two durable review/worker fixes were verified. Resolving a false OCR flag on a
half-round table retains its independent geometry hold, and a stale resolution
hash cannot clear it. Recolor implementation pins now use the named function's
source and compare loaded bytecode without source positions. This avoids false
recovery-admission failures after unrelated line moves, while rejecting actual
implementation drift. The existing admission pin and attempt limits remain
unchanged. Studio was checkpoint-stopped for finite imports, then resumed; mini
and laptop coordinators were restarted after the false pin failure. Read their
live state files for current activity rather than assuming these restarts imply
ongoing generation.

The post-review readiness snapshot has 47,776 of 48,844 new images accepted,
3,946 retained-media briefs unresolved, and 329 unresolved category images.
It is not export-ready; no expanded catalog has been installed or deployed.
These are point-in-time values. The final regression log is
`completion-fixes-20261003/tests-completion-final.log`.
That full suite passed 688 tests with six skips; `git diff --check` also passed.

October 3 image review: the saved Keep pass accepted 84 current images without
changing image bytes, and direct full-size inspection cleared three more false
annotation flags. Two Keeps with actual markings remain held. An explicit user
Redo for `WANDS-SYN-S-OFFICE-02559` now describes a single mountable under-desk
drawer in both the image request and product copy. Its second bounded new
attempt passed the ordinary image review; the first failed for having no drawer
front. The feedback receipt and prior attempts are retained in `run-v3`.

Direct inspection of the 105 accepted images whose brief says `half-round top
and straight legs` found that all showed round or oval tabletops, with no
visible straight rear edge. The normal reviewer also falsely accepted a new
one-product geometry pilot. All 105 exact image hashes were placed on manual
hold for reprocessing without changing their bytes or prior review evidence.
The hash-bound manifest, five numbered contact sheets, receipt, and 431 MB
pre-hold ledger backup are in
`var/catalog-expansion-20260918/completion-fixes-20261003/`. The new pilot was
directly rejected. Newly reviewed half-round images now require direct visual
confirmation of a straight rear edge and curved front even if the ordinary
reviewer passes them; an exact-hash manual resolution records that observation.
At this initial checkpoint, no half-round recipe had yet passed the pilot gate;
the later same-material completion evidence above supersedes that state.
Eight representative count-sensitive reference repairs are admitted for a
bounded, one-extra-attempt pilot with a separate ledger backup in
`run-v3/reference-completion-recovery/70a68ea43ddd151a/`. Their rendering and
review found only the five-drawer pilot visually correct. The other seven
generated images were held by exact hash after direct inspection found missing
drawer fronts or bulbs. Do not expand these drawer and lighting recipes without
a stronger strategy. The repair queue gives admitted finite pilots priority
over generic retries so their outcome can guide a wider recovery.

The half-round geometry-guide edit, followed by neutral-photo recolor tests,
produced six current images that passed OCR, vision, and direct inspection for
the straight rear edge, curved front, and three legs. Two correct bamboo color
variants came from the corrected navy source. A further 124 jobs were admitted
for at most two new MFLUX edits each from the exact accepted white D-shaped
photo, with color and material prompts and a hash-bound source. The activation
receipt and pre-change ledger backup are in
`run-v3/feedback-reprocessing/c824efa3ca5a60c2/`. It changed no accepted
image bytes and no product descriptions. Every output still needs ordinary QA
and direct geometry review. Current status and worker activity must be
read from `run-v3`; the counts in this note are point-in-time observations.

October 1 update: see [PROMPT-RECOVERY.md](PROMPT-RECOVERY.md) for the verified
source-prompt correction, finite recovery of 2,915 exhausted variants, source
review priority, paired renderer comparisons and rollback controls. Live worker
health and counts remain in `run-v3`, not the historical figures below.

Updated September 20, 2026 (UTC). This is an implementation in progress, not a release
or deployment receipt. The user approved bulk implementation, replacement of the
two existing WANDS catalogs, and use of the existing local MFLUX pipeline.

## Scope and verified data

The approved plan is at `CATALOG-EXPANSION-PLAN.md` in the source checkout.
The candidate doubles the accepted 53,844-record release to 107,688 records:
103,643 simples, 3,995 configurable parents, 50 bundles, and 27,736 configurable
links. It adds 32 category leaves in office organization, entryways, laundry,
garage storage, pet furniture, balcony living, gardening, and pantry organization.

The immutable candidate is `var/catalog-expansion-20260918/candidate-v4`.
Its manifest SHA-256 is
`921e5e1a0d8a386c93bf0f80dd6543c9d3561e5ad27e31df5b80b9d3e0d8502e`.
There are 48,844 new image jobs and a 396-image pilot covering 120 representative
designs plus their related family images. All 46,602 original media files were
verified against the accepted release inventory. Earlier candidates and run-v1
are retained development evidence, not deployable artifacts.

## Existing installations only

| Destination | Existing WANDS records | Inserts | Existing content updates | Type conversions | Unrelated products preserved |
| --- | ---: | ---: | ---: | ---: | ---: |
| `/Users/matt/code/mageos-latest` | 42,994 | 64,694 | 42,994 | 1,995 | 192 |
| Comtom `/opt/comtom/stores/relevance/src` | 53,844 | 53,844 | 1,478 | 0 | 1,200 |

Comtom uses `farm-relevance-php-1`, with the application mounted at `/var/www/html`.
Resolve website `wands` on each destination: IDs are currently 5 locally and 2 on
Comtom; store ID is 2 on both. No third store has been created. Neither existing
catalog has been changed during this task.

Fresh read-only snapshots and exact delta plans are under the same work directory:
`local-before-snapshot.json`, `comtom-before-snapshot.json`, `local-update-v2`, and
`comtom-update-v1`. Local-update-v1 is superseded because its converter manifest
included expanded children. V2 converts using the original accepted children,
then leaves expanded relationships to native import. Eleven original families
have two children; the converter now accepts 2, 4 or 6 original children while
retaining SKU, identity, type, and family checks.

## Image contract and running work

All generation entry points enforce `measurement-free-v1`. Measurements remain
in structured specifications, never image prompts or image annotations. OCR and
local vision review reject text, measurements, incoherent construction, component
errors and mismatched colors. New family colors edit the accepted base image;
review compares both source and result. Uniform size variants may share an image.

Active work is `var/catalog-expansion-20260918/run-v3`. Consult `worker-state.json`,
`status.json`, `ledger.sqlite`, `worker-console.log`, `events.jsonl`, `reviews.jsonl`,
and the repair logs for current evidence. The detached supervisor PID is recorded
in `supervisor.pid`; do not assume a recorded PID is still running without checking.
The complete 396-image pilot now has current automated acceptance and hash-bound
direct visual inspection. Full bulk generation is enabled by `pilot-acceptance.json`
and `pilot-direct-acceptance.json`. The supervisor continues new-image generation,
retained-image audit and bounded repairs. Final export still requires every new
image and retained-image brief to pass. No image acceptance, export, or store mutation is implied by a running
worker. The current direct review record is `direct-review-current.json`; the
individual contact sheets, manifests, observations and prior bytes remain intact.

The generation model is the existing cached FLUX.2 Klein 4B, quantized to 4 bits,
at 768 square pixels and four inference steps. Model files and package versions
are pinned in `run.json`. Reviewer: local Qwen3.6-35B-A3B-8bit plus Apple Vision OCR.
Credentials are read locally and are never recorded in generated logs or manifests.

Representative calibration found actual measurement artifacts in WANDS-000007,
WANDS-000008 and WANDS-000027. All three were visually confirmed and rejected by
both the combined review decision and its measurement flag. Wrong component counts
and shapes were also caught in old references. Repairs retain original files and
must independently pass review. A direct review noted missing visible mounting
brackets on the first railing-planter candidate; it was explicitly rejected for
repair. One OCR false alarm on plain desk legs was resolved by full-resolution
direct inspection, with its original OCR and passing vision evidence retained.
The `accept-ocr-review` command is hash-bound and cannot override failed or
uncertain vision checks. An automatic score alone is insufficient for this action.

Initial measured generation is about 5–6 seconds for a new image and 11 seconds
for a reference edit. Single-model vision review is roughly 9–12 seconds per
image. Concurrent generation substantially slows review, so the supervisor runs
serial batches. Full generation, old-image audit and repairs are a multi-day job.

## Resume and acceptance

Use `/Users/matt/code/mageos-latest/.venv-imagegen/bin/python` for the Python tools.
The interpreter includes the existing MFLUX environment. GPU, local network and
Apple Vision access require execution outside the restricted tool sandbox.

```sh
python dev/tools/wands_catalog/run_expansion_batches.py \
  --run var/catalog-expansion-20260918/run-v3 \
  --ocr var/catalog-expansion-20260918/bin/image-ocr \
  --omlx-settings /Users/matt/.omlx/settings.json --batch 64 --bulk \
  --export-output var/catalog-expansion-20260918/accepted-export-v1
```

Do not start a second supervisor. The supervisor lock prevents duplicate workers.
A file named `STOP` in the run directory requests a stop between bounded phases.
Remove it only when intentionally resuming. Every generated attempt is retained;
unfinished generation or review resumes from the ledger. Three failed attempts
are held for investigation rather than automatically accepted.

The complete pilot receipt was created only after direct inspection of all current
396 image hashes, with independent OCR, vision and required component acceptance.
Rounds 1 through 6 are retained. The full worker uses `--bulk` and verifies that
receipt before generation. Any changed pilot bytes or reference acceptance
invalidate the gate. Uncertain images and rejected references cannot pass.

`export_expanded_catalog.py --run ...` checks readiness without exporting. Supplying
`--output` exports only when every new image and retained image brief is accepted,
the pilot receipt remains current, and shared retained-media evidence agrees.
Media uses a new hash-addressed namespace so original image files stay intact.

## Remaining implementation and deployment work

1. COMPLETE: all 396 pilot images passed automated and direct visual review.
2. Run all new jobs and the registered retained-media audit; resolve any failures
   and conflicting accepted repairs to shared images. Export only accepted bytes.
3. Refresh the two destination snapshots. Prepare and verify private database,
   module and gallery backups plus a narrow inverse operation before any mutation.
4. Complete the destination-specific application runner, provision only required
   attribute options/patches, validate native imports, and preserve remote existing
   parent stock when importing relationship updates. Do not use a fresh-install
   recipe or reset a shared database.
5. Apply the approved local and Comtom deltas. Replace only WANDS gallery
   associations with accepted images, retaining original files and rollback data.
   Preserve unrelated products, customers, orders, configuration, themes and modules.
6. Verify counts, relationships, protected-data fingerprints, image hashes,
   reindexing, expanded navigation, real product pages and variant/cart behavior.

No commit, push, release publication, or deployment has occurred. Those states
must not be inferred from a validated data candidate or a running image process.

## Validation receipts

The Python suite ran 556 tests: 550 passed, 6 skipped, no failures. The module PHP suite passed 13 tests and
39 assertions. Final logs are `tests-expansion-deployment-final.log` and
`php-tests-stock-preservation.log` in the work directory. The two-child converter regression
failed before the fix and passed afterward. Hash-bound image and reference gates
also have targeted tests. Native import and storefront acceptance remain pending.

A truncated local vision response stopped the first supervisor safely. Transport
and incomplete-format responses now retry at most three times with a larger
response budget; a complete defect verdict never retries for a different score.
The single-attempt failure was reproduced in an isolated test process and the
new retry tests passed. The resumed supervisor completed all 43 pilot-reference
reviews and progressed to repairs. Current progress remains in the live ledger.

## September 20 continuation

Run-v3 uses the corrected visual-review policy. The migration re-used image bytes
but transferred no acceptances. Run-v2 and its original evidence remain intact.
Additional component checks count distinct drawer fronts and doors without
supplying the intended count to the model; seams, not handles, determine counts.
Manual reference holds cannot be overridden by later automated passes.

Bulk generation is now real, beyond the pilot. The first 32 non-pilot images were
reviewed: 24 initially passed and eight were rejected mainly for incorrect color.
Direct inspection of those 24 found three additional construction mismatches.
These are queued as explicit holds in the current direct-review receipt and are
applied at phase boundaries. Later batches continue from the same SQLite ledger.
Use live status rather than treating these checkpoint counts as current totals.

Direct review rounds 1 through 4 and bulk-direct-review-1 are complete for the
images in their individual manifests. Do not repeat those inspections unless the
image hash changed. Round 4 found six dresser variants with partially unchanged
gold drawer fronts; those current hashes are held for correction. White bench,
white lounge chair and white cabinet knob now use gray backgrounds after two
white-background attempts lost edge detail. Those corrected bytes were inspected
directly and remain subject to automated review.

`migrate_image_review_run.py`, `execute_image_corrections.py`,
`profile_admission.py`, and `component_review.py` preserve provenance and gates.
A changed accepted reference grants a fresh bounded retry budget without erasing
old attempts. Already reviewed variants tied to superseded references are
requeued. Fresh unreviewed explicit corrections must first be compared against
the current accepted source, not discarded merely because their generation input
was an earlier candidate.

Current stock-aware installation snapshots are `local-stock-before-snapshot.json`
and `comtom-stock-before-snapshot.json`. Both were refreshed read-only. Counts,
product identity maps and all prior protected fingerprints matched the earlier
snapshots. Schema 2 additionally records exact existing WANDS stock rows and
protects unrelated stock, entity, website, category and gallery associations.
Refresh again immediately before an actual import.

The optional native import flag `--preserve-existing-stock` is implemented in the
source module, with an outer stock-processor interceptor protecting both legacy
and MSI writes. It captures only pre-existing CSV products assigned exclusively
to WANDS, lets new products receive their intended stock, and releases the scope
in a finally block. Normal imports are unchanged. This is unit-tested but NOT
installed or runtime-accepted on either destination yet.

`verify_expansion_install.py` verifies exact target SKU/type/site/ID sets, 27,736
configurable links, unrelated product preservation, protected fingerprints and
existing stock against schema-2 before/after snapshots. Its regression tests
reject stock changes, missing relationships and unrelated-data changes. Running
it on the current Comtom before-state correctly failed for the missing 53,844
products and 17,000 new links. It does not verify media, complete EAV content or
storefront behavior; those remain separate acceptance requirements.

Remaining deployment work is runtime application of the native runner, private
backups and inverse operation, accepted media staging/gallery replacement,
attribute options, module activation/cache handling, actual imports, and live
acceptance. The background image supervisor does not perform deployments. No
commit, push, release, store change or completion claim is authorized by this
checkpoint alone. The user's prior approval does authorize replacing these two
existing catalogs once the exact artifact is ready and verified.

Uncertain OCR candidates may now receive bounded image repairs followed by fresh
OCR and vision review. This does not convert uncertainty into acceptance. The
three-attempt limit still applies, and a direct false-positive resolution remains
hash-bound. Test coverage verifies reference retry exhaustion.


## Full-pilot acceptance and deployment preparation

All 396 pilot images passed on September 20 UTC. Direct review round 5 identified
14 current defects; round 6 inspected the 20 resulting replacements, including
six reused accepted family images with identical visible briefs and source hashes.
Those six retained fresh, independent reviews under their target briefs. No old
failed attempt or automatic score was converted into a direct visual acceptance.
The complete pilot receipts are now present and full `--bulk` work has started.

The retained-image repair strategy now uses fresh MFLUX rendering when the
review disproves geometry/component counts, or a prior edit fails product identity.
Annotation-only repairs still edit the original. Each attempt remains bounded,
measurement-free and independently reviewed. New reference-based variants now
explicitly preserve empty gaps and hanging hardware; white variants use a neutral
gray background to preserve edge detail. This changes future generation prompts,
not acceptance criteria or the immutable product data.

`prepare_expansion_deployment.py` verifies the complete export, its accepted image
inventory and frozen product files before creating bounded native-import batches.
It rejects partial image acceptance, changed bytes, third destinations and product
data drift. No accepted full export exists yet, so actual deployment batches from
this tool have not been produced.

`expansion_media.php` prepares an exact media-role/gallery dry run, verifies native
imported bytes against accepted image hashes, replaces existing store-view image
overrides and hides obsolete WANDS gallery views without deleting files. Apply
requires a fresh identical plan; its journal supports a conflict-checked inverse.
Ten SQLite acceptance cases passed, including unrelated-product preservation,
exact rollback, missing galleries, wrong hashes and concurrent-row drift. This is
not yet runtime-accepted against either store. Log: `expansion-media-tests.log`.

The supervisor completion test reproduced an early-exit defect when all new jobs
were accepted but retained-media auditing was unfinished. The fixed supervisor
requires full export readiness before declaring the image run ready. A deliberate
phase-boundary restart loads this fix; the SQLite ledger preserves completed work.

Live read-only inspection found local mode `developer` and Comtom mode `production`.
Both installed catalog modules are under `app/code/RocketWeb/LabCatalog`. The local
module predates the existing realism/depth/disclosure attributes and several
baseline importer components. Its update must include those existing components,
not only the new stock-preservation plugin. Comtom also requires compiled-code
handling. No installed source, schema, catalog, stock, media or configuration has
been changed in either destination during this task.


## Current worker and remaining installation boundary

At the September 20 checkpoint the full worker was PID 66246, recorded in `run-v3/supervisor.pid`.
It was restarted cleanly at a phase boundary after reviewing the first complete
bulk batch. It uses `--bulk --batch 64 --export-output .../accepted-export-v1`.
A process-scoped `caffeinate -i -w` keeps the machine awake only while this worker
runs. Verify the PID and live `worker-state.json`; these numbers are observations,
not a permanent service configuration. There is no STOP file after this restart.
The worker exports only when all image gates pass. It does not deploy either store.

The first full-bulk review processed 96 pending images: 91 passed and five were
rejected automatically. Direct inspection then sampled 24 of the 91 accepted
images and held five more for construction mismatches (drawer versus open cubby,
spindles versus ladder rungs, missing alternating partitions, or untapered legs).
All five holds were applied safely between phases. Evidence is in
`bulk-direct-review-2/{manifest.json,observations.json,holds-applied.json}`.
No displayed measurements were observed in that direct sample. This is a sample,
not a claim that all bulk images have been inspected directly.

Media coverage has been independently reconciled against the frozen data:
107,688 products, 107,668 media assignments, and exactly 20 retained disabled,
individually hidden nursery variants that were already imageless in the baseline.
All new products and every enabled product require media. The exporter lists the
20 exclusions explicitly, and deployment preparation rejects any enabled or new
product exclusion. The gallery tool verifies excluded products remain disabled in
the installed database. Evidence: `media-coverage-validation.json`.

`run_expansion_native_imports.py` provides the bounded native application phase.
It defaults to a dry run without store commands, requires the exact prepared-plan
hash, verifies all batch hashes, and confines runtime targets to the existing Mac
installation and Comtom host/container. Apply requires fresh private database and
module backups plus an exact inverse artifact, all hash-bound to the before
snapshot. An immediate read-only snapshot must still equal that before-state.
Each native batch is validated before import with existing-stock preservation;
local parent conversions have a dry run. Failures stop and retain exact receipts;
partial application requires reconciliation before retry. Its completion state
explicitly leaves gallery, navigation, indexes and live verification pending.
The runner's seven boundary tests passed. It has not run against either installation.

Remaining installation preparation still includes the actual accepted export,
fresh target snapshots/backups and exact inverse, module deployment and necessary
attribute options/patches, Comtom compiled-code handling, verified media staging,
then native imports, gallery plan/apply, navigation, reindexing and live acceptance.
These are already authorized for the two named installations; do not request the
same approval again. No commit, push, release or third installation is authorized.

Comtom host Python was verified live as 3.13.5, compatible with the standard-library native runner. Final test logs are `tests-expansion-deployment-final.log` and `expansion-media-tests.log`.

## September 20 evening: local review service outage recovery

The morning restart (PID 85422) exited during `review-references`: every request
failed with `URLError`, and the supervisor stopped after three image-level failure
batches. The user confirmed oMLX had not been started. On the evening check,
oMLX was already running, listening on loopback port 8000 and returning the expected
Qwen3.6 vision model through authenticated `/v1/models`. No service configuration,
credential, model selection or image acceptance policy was changed.

`image_review.py` now distinguishes temporary transport/service outages from
malformed vision responses. After three transport attempts, a service outage
propagates through original-image, candidate and repair review without spending
the image's bounded review budget or accepting it. Safe error codes are retained
in `review-service-errors.jsonl`. The worker subprocess returns exit 75, and the
supervisor records `waiting_for_review_service`, waits one minute, then retries
the same checkpointed phase. A STOP file interrupts the wait within five seconds.
Authentication/configuration errors and malformed review exhaustion still stop or
follow the existing bounded failure path; complete defect verdicts never retry
for a more favorable score. Historical failure records are preserved.

Regression tests reproduced the former stop and failure-budget behavior before
the fix. The full suite now runs 564 tests: 558 passed and six skipped. Evidence:
`var/catalog-expansion-20260918/tests-review-service-recovery.log`.
Runtime verification uses a bounded eight-image full cycle before returning to
the 64-image bulk worker. Read the live PID and ledger for current progress; a
PID file or old `running` state alone is not evidence of a healthy worker.

The bounded cycle completed with exit 0: eight reference reviews, four reference
repair generations, eight repair reviews, eight new-image generations and eight
new-image reviews. New accepted images rose from 706 to 708, accepted retained
briefs from 640 to 645, and accepted repairs from 157 to 159. Image failures stayed
rejected. The full `--bulk --batch 64 --export-output .../accepted-export-v1` run
was then resumed with process-scoped caffeinate. The exact completed-cycle state
and test results are saved in `run-v3/service-recovery-20260920.json`. Both store
installations remain unchanged.

## September 22: Metal debug-wrapper crash recovery

The September 21 post-reboot worker (PID 48233) finished 64 retained-image reviews
and then stopped during `repair-references` with SIGABRT / exit -6. The native
assertion was `MTLDebugComputeCommandEncoder ... bytes argument cannot be nil`.
The tool environment contained `METAL_DEVICE_WRAPPER_TYPE=1`. On September 22,
the exact next checkpointed repair reproduced the abort with that setting and
completed successfully when only that inherited debug-wrapper variable was
removed. The model, seed, prompt, memory limit and image-review policy were kept.

`run_phase` now removes `METAL_DEVICE_WRAPPER_TYPE` from generation subprocesses
(`generate`, `generate-admitted`, `repair-references`) only. This is a local
runtime workaround, not a change to MFLUX or a waiver of image acceptance. It
does not modify the host environment, oMLX service or either installed catalog.
The regression test failed first for all three generation phases, then passed.
Full suite: 565 tests, 559 passed, six skipped. Log:
`var/catalog-expansion-20260918/tests-metal-runtime-recovery.log`.

The subsequent bounded full cycle exited 0, completed repair generation/review,
and generated/reviewed four new images. Three passed; one remained rejected.
Accepted new-image count rose from 3,058 to 3,061. The exact cycle and test counts
are saved in `run-v3/metal-runtime-recovery-20260922.json`. Full 64-image batches
were resumed afterward using the corrected supervisor. No store deployment has
occurred; verify `supervisor.pid` and advancing ledger counts before reporting
the worker healthy.

## September 22: Mac mini worker enabled

The user approved adding their M4 mini as a generation worker and explicitly
approved the Studio public SSH key on `matt@192.168.1.115`. Live hardware reports
M4 Pro / 24 GiB RAM. After the user freed disk space, 78 GiB was available. The
isolated `/Users/matt/wands-image-worker` now has Python 3.12.12, pinned MFLUX/MLX
dependencies and all 16 hash-verified model files. No third store was installed.

The four-image mini benchmark imported successfully into the central QA queue.
Every JPEG matched the Studio comparison byte-for-byte with the same prompts and
seeds. Mean sampling/output time was 20.806 seconds on the mini versus 4.18975 on
the Studio; mini tracked GPU memory peaked at 14.233 GiB. Three images passed
direct inspection and automated QA; one incorrect cabinet-shaped rack stayed
rejected with a direct correction note. No measurements/text were seen. These
sample timings exclude model loading, transfer and review.

See `MINI-WORKER.md` for operation, cancellation and evidence. Central supervisor
PID 43769 and mini coordinator PID 43771 started 64-image bulk batches; verify
them live before reporting health. The benchmark is batch
`64b027657f494fae886a98b7ca9f42f7`, and the first continuous mini batch is
`d512fbfd33004ee0a28253ca54a60303`. Initial accepted image count was 4,509.
Remote images are reserved centrally, verified on return and enter `generated`,
never direct acceptance. `REMOTE_STOP` controls the mini coordinator separately
from the Studio STOP file. No installation, commit, push or release occurred.


## October 3: completion fixes and explicit riser/bench corrections

The user authorized implementing the completion fixes and continuing on the
existing Studio, mini and laptop workers. Existing stores are still unchanged.
Artifacts for this work are under
`var/catalog-expansion-20260918/completion-fixes-20261003/`.

Completed before the category clarification:
- Reconciled 280 human Keeps without changing their images, with hash-bound
  receipts and preserved original automated disagreements. Accepted five separate
  annotation-cleaned copies after paired direct inspection; eight original
  annotation holds remained. Later user reviews are additional live feedback.
- Fixed retained-media export resolution by exact SKU and design, eliminating
  filename-only replacement conflicts. Registered 2,463 missing retained briefs;
  50,239 distinct briefs cover 53,824 retained SKU assignments.
- Corrected deployment preparation to validate approved metadata patches against
  the frozen candidate and trusted run. Only dry-run local/Comtom deltas exist.
- Admitted 448 specific new-image and 121 retained-reference recovery jobs after
  geometry pilots. Each has a bounded additional attempt and immutable receipts.

Latest explicit requirements:
- All 755 monitor-riser images are audited for a separate low wide furniture
  platform or drawer base. The SKU color applies to that base. An optional
  monitor must be a simple black monitor with a normal compact black foot and a
  dark blank screen. A monitor pedestal or complete desk is not a riser.
- All 615 shoe benches are audited for a usable long low seat with accessible
  shoe storage. Open shelves and separate front-facing cubbies are both valid.
  Rounded corners do not mean a circular table with radial fins.
- Shoe-bench Keeps are preserved. Earlier monitor Keeps can be superseded only
  by the explicit new category requirements; compliant monitor Keeps are kept.
- No visible text, numbers, measurements, logos or labels are permitted.

`category_image_corrections.py` adds a separate category audit, frozen admission,
maximum two additional attempts per enrolled image, source-parent gates, live
Keep reconciliation, outage handling, and export gating. The supervisor now
includes bounded category-review batches. The historical pilot receipt permits
remediation of explicitly revised pilot examples while export still requires
current accepted images and current category checks.

Five semantic calibration cases behaved as expected: old circular bench and
colored wooden monitor failed, corrected cubby bench, corrected black-monitor
layout, and user-approved open-storage Moss Dale bench passed. A further fresh
monitor sample became a full desk; the new category check correctly rejected it
although general QA passed. It was never installed into the ledger.

Exact examples:
- Moss Dale, `WANDS-SYN-S-ENTRYWAY-01773`: accepted from the user's saved Keep;
  original hash `5dbd125dd769f3b1bb8d3cb8946c9236a46223f5b5caadd72855099c8b98708b`
  unchanged. Keep receipt and backup: `run-v3/human-keep-acceptance/d40ab3530fdc557c/`.
- Hazel Canyon, `WANDS-SYN-S-ENTRYWAY-01181`: corrected long rectangular bench
  with three open shoe cubbies accepted after direct, OCR, general and category
  checks. Original circular image remains in the prior attempt.
- Harbor Bend, `WANDS-SYN-S-OFFICE-00257`: corrected terracotta drawer box and
  black monitor, with both bezel markings removed. Category and annotation checks
  pass, but general QA disputes the painted Bamboo appearance and drawer depth.
  Latest candidate is `review_required`, protected from another automatic retry
  by a hash-bound manual-review hold. User Keep can resolve the semantic dispute
  while annotation checks remain mandatory. No automatic override was granted.

Registration backup/manifest:
`run-v3/category-corrections/837c52fca50b7194/`.
Two concrete sample imports, lineage and backup:
`completion-fixes-20261003/category-sample-import.json`,
`ledger-before-category-samples.sqlite`, `import_category_samples.py`.
Original image files and all feedback decisions were preserved.

The two previously reserved mini/laptop batches were drained and imported before
activating the category rules. Workers resumed at approximately 09:39 EDT:
Studio supervisor 14854, mini coordinator 14855, laptop coordinator 14856.
Verify these live; PIDs are historical, not a health claim. Studio started category
review and both remote workers started new generation batches. Runtime snapshot:
`completion-fixes-20261003/category-runtime-verification.json`.

Validation: 676 tests ran, 670 passed and six skipped. Log:
`completion-fixes-20261003/tests-category-final.log`. Compilation and
`git diff --check` passed. Existing review UI on port 8877 was refreshed and exact
served image hashes checked. No commit, push, accepted export, store import,
reindex or deployment occurred. Catalog completion remains pending full image
acceptance, retained-media resolution and fresh installation snapshots.


## October 3 evening: finite geometry repairs and exact-input QA reuse

Current work remains incomplete; the latest saved full inspection in
`var/catalog-expansion-20260918/completion-final-20261003/live-completion-readiness.json`
reported 47,761 accepted new images, 1,083 held new images, 3,334 unresolved retained
briefs, and 89 unresolved category checks. That snapshot predates the subsequent
124 cart imports, 26 storage imports, and four confirmed standalone risers. Do not
use it as a current completed count or claim export readiness.

The current completion directory contains immutable previews, exact before rows,
QA evidence, receipts and inverse-operation descriptions. This turn registered
87 exact descriptive retained copies, four geometry repair pilots, 142 related
accepted dresser/loveseat repairs, ten initial and five additional direct count
corrections, 169 directly confirmed open-storage photos, 26 matching storage
copies and 124 matching cart copies. Genuine invalid counts and source geometry
were held, with original photos and evidence retained. Human Keeps were preserved.
The shelf counter comparison failed on three of five inspected ground truths;
its new scoped wording must not be described as a reliable automatic counter.
Direct count certificates require actual exact-photo inspection and cannot clear
general, annotation, geometry, manual or complete-table count failures.

Four standalone white bamboo riser briefs share one native-inspected correct
low wide riser with an accessible side cubby and open center. Independent category
QA passed; general QA had incorrectly inferred that a white coating disproved
bamboo and called it a desk. `direct_riser_acceptance.py` now permits only this
kind of hash-bound, category-passed standalone identity/material correction after
native review. It refuses paired-source edits, annotations, geometry defects,
wrong piece counts, human Keeps and direct holds. It preserves the original
false model evidence. The exact application and rollback are recorded in
`native-white-bamboo-riser-receipt.json`.

An additional 74 retained four/five-drawer briefs have 49 rendered group photos.
Every full-resolution group photo was inspected individually. Groups
4, 5, 12, 16, 17, 18, 21, 33, 38, 40, 41, 44, 45 and 49 are held for genuinely
wrong complete drawer counts, fabric/product mismatch or contradictory finish.
The ordinary QA process, `finalize_four_five_drawer_native_qa.py`, and
`import_four_five_after_finalization.py` are running serial acceptance stages.
Only finalized passing photos may be imported; do not assume a template edit
preserved its component layout. Originals, failed staged photos and histories
remain intact. Final import receipt is authoritative when present.

`Reviewer.inspect` now reuses OCR/model evidence within a reviewer session only
when effective visual brief, candidate bytes, source bytes, component requirements
and scope, table requirements and review identities match exactly. It deep-copies
the evidence and binds the new full design hash, including explicit reuse evidence.
It reuses rejected verdicts too; errors are not cached. This does not generalize
across visually different products or bypass any gate. The 124-cart pass had 45
unique effective inputs, so similar batches can avoid 64 percent of repeated
reviews. A live benchmark preserved an accepted verdict and original evidence:
24.525 seconds for a fresh review and less than one millisecond for exact reuse.
This is a reuse benchmark, not an estimate for overall catalog completion.

The full regression suite passed 706 tests with six skips after these changes;
`tests-final-after-speedups.log` is the current proof. `git diff --check` passed.
The review interface returned HTTP 200. Studio supervisor PID 9911, mini
coordinator PID 9912 and laptop coordinator PID 9913 were restarted using the
pinned Python after verifying the original bulk pilot gate. Verify their current
state and logs before reporting status. At the last check, Studio was processing
reference repairs, mini was generating a 64-image batch, and laptop had completed
three images and was waiting to import under the generation lock. The restart
commands and exact PIDs are in `workers-restarted-after-repairs.json`.
No store import, deployment, commit, push or publication occurred.


### October 3 throughput improvements, current verification

Identical OCR pixels and complete model requests now reuse immutable evidence within one Reviewer instance. Product brief and approved-source checks remain separate when their payloads differ; reused unprimed counts are rebound to the current required counts and can reject a different brief. No persistent cross-session acceptance cache or model switch was added. General, count, table, OCR, geometry, annotation, human Keep, source hash and full design gates remain in force.

A non-mutating pinned-model benchmark measured matching second-brief QA at 3.271s fresh versus 1.381s reused. All benchmark QA verdicts remained accepted. Two warm serial generation/QA pairs had median 11.380s combined, compared with 10.667s overlapped. The approximately 6% combined benefit is a small sample; concurrent QA itself was three times slower, so the existing scheduler and models were retained. This is not a catalog ETA or universal speedup claim. Benchmark photos remain isolated and unapproved; no catalog rows or original image bytes changed.

Local generation and retained-reference rendering now check for an outstanding returned remote packet at image boundaries and yield the generation lock, preserving the completed image and leaving the next attempt untouched. All reservation and import verification stays intact. Operator STOP also checkpoints at those boundaries. Regression evidence includes the mid-image return test failing with two generated attempts before the change and passing with one completed image plus one untouched pending job.

Current full suite: 718 tests run, six skipped and 712 passed, using the pinned image Python with socket permissions; git diff --check passed. Logs: throughput-improvements-tests.log, request-reuse-red.log, request-reuse-green.log, import-mid-image-red.log and import-checkpoint-green.log. Live benchmark: throughput-live-benchmark.json.

The finite four/five drawer batch imported 53 accepted repairs and skipped 21 entries, with zero original image changes; full rows and rollback pins are in four-five-drawer-repairs-import-receipt.json. Studio resumed as PID 61686; existing mini and laptop coordinators were preserved. Mini directly verified rendering 59 of 64 images, most recent photo 16 seconds old. Laptop completed 28 batches and was waiting for eligible jobs, with its GPU idle rather than running an unnecessary server. Review UI returned HTTP 200.

Readiness snapshot after improvements: 47935 of 48,844 new images accepted, 3260 retained briefs unresolved and 85 category corrections unresolved; ready=false. No catalog export, installation, commit, push or publication was performed.

Live follow-through: mini batch 9970cc365b324886a3421f8e3332e272 subsequently imported all 64 images through normal packet validation. Studio advanced to review-repairs; both remote coordinators then waited for newly eligible jobs. Exact worker and batch receipt: throughput-workers-verified.json.

## October 4: retained repairs on all existing renderers

The remote coordinators previously stopped or waited after exhausting eligible new-product jobs while retained-reference repairs remained exclusive to the Studio. `remote_reference_repairs.py` now reserves disjoint retained targets for the existing mini and CUDA laptop renderers. Typed packets preserve the complete frozen brief, original pixels, attempt history, seed, model/environment pins, human Keeps and finite retry eligibility. Renderers receive sealed prompts and source snapshots, not the ledger or review credentials. Returned photos enter ordinary Studio QA with no automatic acceptance. Local generation excludes remote-owned targets. Reservation, import, cancellation, exact before rows and scoped inverse receipts are retained.

Both remote coordinators now use eight-image packets and continue while retained repair or QA work remains. Studio generation yields at image boundaries for returned packets and fresh, lock-owning coordinators waiting to reserve. Stale heartbeat files cannot force a yield. The category correction pass now recognizes retained packets without treating their opaque IDs as new-product jobs. New-product packet/source protections remain intact. No remote model or deployed renderer code changed.

Live pilot inspection exposed two quality issues. A three-light photo passed general QA despite having only two complete emitters; independent, unprimed lighting counts now reject such new candidates and uncertain counts. Supports, brass tubes, finials and reflections are excluded from emitter counts. Legacy accepted evidence and saved human Keeps were not invalidated. Confirmed component-count failures now select fresh structural generation rather than repeatedly editing known incorrect layouts. Shelf recipes specify usable horizontal surfaces, and vanity lighting recipes specify a horizontal wall backplate with separate emitters. Prompt-only cleanup removes hyphenated measurements without changing frozen product briefs or design hashes.

Four pilot repairs passed ordinary packet import; native review and full QA accepted one platform-bed repair and rejected three candidates. First continuous packets exposed seven native-confirmed count/annotation defects, now held. One visually verified four-drawer donor received a narrow count-only correction that preserves the original model evidence. Two identical visible-layout size variants passed full target QA using that verified photo, preserving all prior attempts and original pixels. Exact evidence and inverses are in `completion-throughput-20261004/pilot-reviews-applied.json` and `native-counts-and-size-family-receipt.json`. Two already sealed eight-image packets were drained with their exact earlier recipe snapshots before activating the new count strategies; they were imported for QA only. No retry budgets were reset.

Full verification used the pinned image Python: 741 tests ran with six skips and no failures. Red/green regression logs and final `tests.log` are in `var/catalog-expansion-20260918/completion-throughput-20261004`. The latest restart receipt is `continuous-workers-started.json`; PIDs are historical references and must be checked live. At the recorded verification, Studio PID 53844 was generating, laptop PID 53715 had completed two eight-image retained batches, and mini PID 53756 had completed one. All three processes were live; 24 repairs had been imported for QA since this restart, and the next packets were active. `throughput-workers-live-verified.json` records exact packet states. The review interface returned HTTP 200. Imported candidates are not accepted-image counts.

The saved full readiness audit still reports ready=false: 47,969 of 48,844 new images accepted, 3,175 unresolved retained briefs and 85 unresolved category checks. This audit predates the final native corrections and latest worker output; refresh it before giving current completion counts. Work remains incomplete. No accepted export, store installation, deployment, commit, push or publication occurred.
