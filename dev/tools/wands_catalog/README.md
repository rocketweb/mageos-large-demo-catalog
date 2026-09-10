# WANDS catalog tooling

For the proposed reusable package for Mage-OS Lab, see the [community distribution design](COMMUNITY_DISTRIBUTION.md). Tool screenshots and diagrams belong in Git; product images belong in separately versioned media downloads. The design is local preparation, not a published catalog release.

For the current full-catalog release, start with [publication preparation and the phased deployment checklist](DEPLOYMENT_READINESS.md). It includes quiet validation commands, remote snapshot/diff and review-only rollback tooling, storefront cases, and CPU-only repair drafts. Older setup examples below are not authorization to import into a local or remote store.

For the next local realism phase, see the [catalog depth pilot](CATALOG_DEPTH.md): a 300-root acceptance set, shared Magento specification schema, non-executable gallery briefs, evidence-backed recommendation candidates, and a separate enriched-catalog judgment queue. This work does not change the existing release or frozen search benchmark.

For the follow-on implementation, see [catalog corrections and guarded expansion](CATALOG_REPAIRS.md): corrected option and assortment definitions, meaningful parent/child copy, recovered source facets, image-repair drafts and independently verified forward/inverse proposals. The expanded packet is local review work, not a deployed catalog release.

The [remaining-definition resolution batch](DEFINITION_RESOLUTIONS.md) now clears the known 41-family queue and eight overlapping holds using source-supported facts and approved, explicitly synthetic conflict resolutions. It includes a post-correction semantic audit and a reference-impact check of all 50 local bundles.

The follow-on [media reconciliation](MEDIA_RECONCILIATION.md) completes initial visual triage for all 93 corrected roots without using a local model: 81 confirmed defects and 12 uncertain references. A deterministic completeness gate rejects packets with unreviewed roots. All references remain unapproved for generation or deployment, and 465 planned gallery views stay bound to the corrected definitions and blocked pending acceptance.

The [bounded repair pilot](MEDIA_REPAIR_PILOT.md) gives all 12 uncertainties a proposed next action: retain four plausible furniture candidates and prepare clearer views for eight textiles/curtains. The local planner prepares 12 exact pilot cases from 89 repair/clarification candidates, with pinned contracts and pending acceptance checklists. It performs no model calls and produces no executable generation queue.

The separately authorized local pilot has now generated 12 candidates, one attempt each, with no retries or original-media changes. Its initial visual screen finds three passes, two uncertain images and seven failures. The bounded runner rejects over-budget prompts, and the CPU-only review builder binds observations to exact candidate, definition and prompt hashes. A visual pass does not authorize publication, conditioning or bulk expansion. See the [pilot run and review instructions](MEDIA_REPAIR_PILOT.md#completed-local-pilot).

The next [component layout planner](COMPONENT_LAYOUTS.md) prepares five failed assortments as 68 physical positions across 28 component types, including complete flatware settings and a shared-floor lamp scale. It checks counts, grouping and geometry envelopes, and records construction-specific asset requirements. These are CPU-only planning diagrams, not new catalog images or approved generation references.

The subsequent [four-component image pilot](COMPONENT_IMAGE_PILOT.md) generated one floor lamp, one table lamp, one dinner fork and one cake server, with one local attempt each. All four are recognizable single objects; the initial visual screen records one pass, one uncertainty and two proportion failures. No masks or composites exist, and neither complete assortment is approved for publication.

The next [equal-area framing experiment](FRAMING_PILOT.md) compares square and portrait canvases for the failed floor lamp and cake server, preserving prompts, seeds, pixel count and the local model. Every pass retains its original evidence and stays separate from live catalog media.

The [product-specific framing refinement](FRAMING_REFINEMENT.md) uses the observed silhouette drift to calculate two bounded follow-up canvases. It retains the existing prompts and seeds, limits pixel-area change to 1%, and keeps visual acceptance separate from masking, assembly and publication.

This tooling prepares the pinned Wayfair WANDS product corpus for the isolated `wands` Mage-OS website.

## WANDS attribution

This catalog builds on [Wayfair's WANDS dataset](https://github.com/wayfair/WANDS),
not an independently collected product corpus. WANDS requests the following
citation when building on or using the dataset:

```bibtex
@InProceedings{wands,
  title = {WANDS: Dataset for Product Search Relevance Assessment},
  author = {Chen, Yan and Liu, Shujian and Liu, Zheng and Sun, Weiyi and Baltrunas, Linas and Schroeder, Benjamin},
  booktitle = {Proceedings of the 44th European Conference on Information Retrieval},
  year = {2022},
  numpages = {12}
}
```

Source: [upstream citation](https://github.com/wayfair/WANDS#citation).
WANDS is [MIT-licensed](https://github.com/wayfair/WANDS/blob/main/LICENSE).
Redistributions must also retain its copyright and permission notices; the
paper citation is not a substitute for those notices. Prices, stock scenarios,
generated images, rewritten copy, configurable variants, bundles and synthetic
dimensions added by this tool are derived lab content, not original WANDS
observations or newly validated WANDS relevance judgments.

## Prepared outputs

It creates:

- a Magento product-import CSV with deterministic SKUs, categories, inventory, and synthetic prices;
- a JSON Lines image queue with reproducible prompts and seeds;
- a provenance manifest with source and output hashes;
- a media-only Magento CSV for images that have completed generation.

The generated catalog is lab data. `lab_price_synthetic=Yes`, `lab_price_method`, and `lab_price_version` retain that provenance on every product. Pricing is deterministic and based on department, product-class keywords, material, dimensions, rating, review count, and a stable per-product adjustment. It is plausible lab data, not observed retail pricing.

```sh
python3 dev/tools/wands_catalog/prepare_catalog.py \
  --input /Users/matt/code/rocket-search/data/raw/wands/product.csv \
  --output-dir var/wands

php bin/magento lab:wands:provision --base-url=http://relevance.comtom.lab:8080/
php bin/magento lab:wands:import --file=var/wands/products.csv
php bin/magento lab:wands:seed-queries \
  --file=/Users/matt/code/rocket-search/data/raw/wands/query.csv \
  --store=wands

php bin/magento lab:wands:curate-navigation
```

## Local image generation

MFLUX 0.19.1 runs Apple-Silicon image models through Metal without using ChatGPT or Kimi quota. On this Mac Studio, FLUX.2 Klein 4B at 768 square, four steps, and 4-bit quantization is the bulk default. Its warm throughput is about 4.1 seconds per image, or roughly 49 hours for the full catalog when run continuously. The low-priority background worker is closer to 4.5 seconds per image. Z-Image Turbo produced a useful challenger image but was about four times slower. FLUX.2 Klein 9B remains unavailable until the Hugging Face account is approved for its gated repository.

Create the isolated environment once:

```sh
uv venv --python 3.12 .venv-imagegen
uv pip install --python .venv-imagegen/bin/python \
  -r dev/tools/wands_catalog/requirements-imagegen.txt
```

The generator loads the model once, skips completed files, writes each JPEG atomically, and records every success or failure in `pub/media/import/wands/generation-events.jsonl`:

```sh
.venv-imagegen/bin/python dev/tools/wands_catalog/generate_images.py \
  --prompts var/wands/image-prompts.jsonl \
  --output-dir pub/media/import/wands \
  --model flux2-klein-4b \
  --quantize 4 \
  --width 768 \
  --height 768 \
  --steps 4
```

The repository contains local LaunchAgent definitions for the resumable image worker, a 15-minute incremental media importer, and Magento cron. The media importer attaches only completed files that have not passed a successful import checkpoint, in batches of at most 500. These agents are machine-specific because this is a local lab. Bootstrap them from `~/Library/LaunchAgents`, and remove the Magento substitute before returning to Magento's normal `cron:install` crontab entry.

## Attach generated media

Magento 3.4's product importer accepts JPEG, PNG, and GIF, but not WebP. Generated JPEG files belong in `pub/media/import/wands`. Build and import a media snapshot at any point while generation continues:

```sh
python3 dev/tools/wands_catalog/build_media_csv.py \
  --prompts var/wands/image-prompts.jsonl \
  --image-dir pub/media/import/wands \
  --output var/wands/media.csv

php bin/magento lab:wands:import --file=var/wands/media.csv
```

Re-running both commands is safe. The CSV only contains completed files, and the product import updates existing WANDS SKUs.

## Configurable families and room bundles

The merchandising planner deterministically converts 2,000 existing WANDS products into configurable parents, creates 10,800 hidden simple children, and defines 50 dynamic-price room bundles. It preserves each selected parent's original SKU, URL, categories, and `wands_product_id`. Generated children do not receive a WANDS product ID and are not visible individually.

Run the planner from the Mage-OS project root:

```sh
python3 dev/tools/wands_catalog/build_merchandising_catalog.py \
  --source-products /Users/matt/code/rocket-search/data/raw/wands/product.csv \
  --prepared-products var/wands/products.csv \
  --output-dir var/wands/merchandising
```

The builder prints one concise completion line by default. Structured start, completion, and failure events are appended to `var/wands/merchandising/build-merchandising.log`, while the full current result remains in `manifest.json`. Watch the log from another terminal with:

```sh
tail -f var/wands/merchandising/build-merchandising.log
```

Pass `--json` only when the full manifest JSON is intentionally needed on standard output.

The reviewed plan is fixed at these totals:

- 600 one-axis configurable parents with four children each;
- 1,400 two-axis configurable parents with six children each;
- 10,800 generated simple children;
- 50 bundles, five each for Living Room, Bedroom, Dining, Home Office, Patio, Bathroom, Nursery & Kids, Entryway, Reading Nook, and Pet Corner;
- 53,844 total product entities after application;
- 43,044 storefront-visible products, because children remain individually hidden.

`manifest.json` contains source and output hashes, exact distributions, entity counts, and media counts. `configurable-families.jsonl` is the human-reviewable source of truth. A bounded 25-family and five-bundle pilot is under `batches/pilot`, including only the pilot's children, conversion records, parent rows, and media mappings. The full CSV files are accompanied by 100-family import batches under `batches/configurables` and five-bundle theme batches under `batches/bundles`.

The generated descriptions are original deterministic copy based on the product class, category, and planned options. `description-prompts.jsonl` supports an optional second copy pass through either oMLX or Kimi. The prompt contract forbids invented measurements, materials, certifications, compatibility, warranties, and performance claims.

### Optional oMLX description pass

oMLX must listen only on loopback at port 8000 and expose an authenticated OpenAI-compatible API. Keep the API key in `OMLX_API_KEY`; do not put it in a command, prompt file, or repository.

```sh
.venv-imagegen/bin/python dev/tools/wands_catalog/generate_descriptions.py \
  --prompts var/wands/merchandising/description-prompts.jsonl \
  --output var/wands/merchandising/generated-descriptions.jsonl \
  --endpoint http://127.0.0.1:8000/v1 \
  --model YOUR_OMLX_MODEL
```

The description worker validates the authenticated model list before generation, uses an exclusive output lock, skips successful IDs on restart, and records errors without marking them complete. Apply a complete oMLX or Kimi-compatible JSON Lines result to new CSV copies with:

```sh
python3 dev/tools/wands_catalog/apply_description_rewrites.py \
  --descriptions var/wands/merchandising/generated-descriptions.jsonl \
  --configurable-parents var/wands/merchandising/configurable-parents.csv \
  --bundles var/wands/merchandising/bundles.csv \
  --output-dir var/wands/merchandising/rewritten
```

The apply step fails closed when any of the 2,050 parent or bundle descriptions is missing. `--allow-partial` is available only for a deliberate partial preview.

### Preview application order

Do not apply the 2,000-family plan directly to the live lab. First restore a disposable copy of the current lab database and media, stop cron consumers in that preview, and retain the database backup and generated manifest hashes.

Run `bin/magento setup:upgrade` to add the global select attributes and their centralized options. The data patch reuses the core global `color` attribute without changing existing option sort order. The new axes are searchable, filterable, usable in layered navigation, and available in product listings.

For the first 25-family pilot, use the files under `batches/pilot`. For each reviewed batch, use this order:

1. Validate `children.csv` with `lab:wands:import --validate-only`, then import it.
2. Run `lab:wands:convert-parents --dry-run` against the batch conversion manifest.
3. Apply the same bounded conversion manifest. The command uses one transaction per parent and verifies the WANDS product ID and every child SKU before changing the type.
4. Validate `parents.csv` after conversion, then import it to attach configurable variations and rewrite the parent copy.
5. Verify parent option combinations, child visibility, prices, stock, images, categories, and storefront behavior before advancing the checkpoint.

Example for the bounded pilot:

```sh
python3 dev/tools/wands_catalog/build_media_csv.py \
  --prompts=var/wands/merchandising/batches/pilot/configurables/image-prompts.jsonl \
  --image-dir=pub/media/import/wands \
  --output=var/wands/merchandising/batches/pilot/configurables/visual-media.csv

php bin/magento lab:wands:import \
  --file=var/wands/merchandising/batches/pilot/configurables/children.csv \
  --validate-only

php bin/magento lab:wands:import \
  --file=var/wands/merchandising/batches/pilot/configurables/children.csv

php bin/magento lab:wands:convert-parents \
  --file=var/wands/merchandising/batches/pilot/configurables/parent-type-conversions.jsonl \
  --limit=25 \
  --dry-run

php bin/magento lab:wands:convert-parents \
  --file=var/wands/merchandising/batches/pilot/configurables/parent-type-conversions.jsonl \
  --limit=25

php bin/magento lab:wands:import \
  --file=var/wands/merchandising/batches/pilot/configurables/parents.csv \
  --validate-only

php bin/magento lab:wands:import \
  --file=var/wands/merchandising/batches/pilot/configurables/parents.csv

php bin/magento lab:wands:import \
  --file=var/wands/merchandising/batches/pilot/configurables/visual-media.csv \
  --validate-only

php bin/magento lab:wands:import \
  --file=var/wands/merchandising/batches/pilot/configurables/visual-media.csv

php bin/magento lab:wands:import \
  --file=var/wands/merchandising/batches/pilot/configurables/reuse-parent-media.csv \
  --validate-only

php bin/magento lab:wands:import \
  --file=var/wands/merchandising/batches/pilot/configurables/reuse-parent-media.csv
```

Bundle batches use dynamic price, dynamic SKU, dynamic weight, and existing visible simple products as selections. They exclude configurable parents and all generated children. Existing bundle assortments must use the atomic reconciliation path so obsolete choices cannot survive add/update. First run `lab:wands:import --validate-only --reconcile-bundles --file=...` and retain the reported exact would-remove counts. After approval, run the same command without `--validate-only`; cleanup and import then share one transaction. Apply this to `batches/pilot/bundles.csv` and each five-bundle theme CSV under `batches/bundles`.

The pilot keeps bundle hero prompts separate from configurable media so bundle image rows are not validated before their products exist. After importing the pilot bundles, build and import their media with:

```sh
python3 dev/tools/wands_catalog/build_media_csv.py \
  --prompts=var/wands/merchandising/batches/pilot/bundle-image-prompts.jsonl \
  --image-dir=pub/media/import/wands \
  --output=var/wands/merchandising/batches/pilot/bundle-media.csv

php bin/magento lab:wands:import \
  --file=var/wands/merchandising/batches/pilot/bundle-media.csv \
  --validate-only

php bin/magento lab:wands:import \
  --file=var/wands/merchandising/batches/pilot/bundle-media.csv
```

### Variant media

Size-only children reuse the existing parent product image through `reuse-parent-media.csv`. Families with a visual color, finish, or material axis use `image-prompts.jsonl`; one generated image is shared by all size combinations with the same visual value.

The same queue also contains one room-scene hero image for each bundle. The reviewed full plan contains 3,335 configurable-variant prompts and 50 bundle prompts, for 3,385 images total. Bundle prompts use the theme, palette, option groups, and first catalog selection in each group as visual references. They ask for a cohesive representative room scene, not a claim that every selectable combination is pictured.

The existing MFLUX generator accepts the new queue unchanged:

```sh
.venv-imagegen/bin/python dev/tools/wands_catalog/generate_images.py \
  --prompts var/wands/merchandising/image-prompts.jsonl \
  --output-dir pub/media/import/wands \
  --model flux2-klein-4b \
  --quantize 4 \
  --width 768 \
  --height 768 \
  --steps 4
```

Check the resumable workload without loading the model:

```sh
.venv-imagegen/bin/python dev/tools/wands_catalog/generate_images.py \
  --prompts var/wands/merchandising/image-prompts.jsonl \
  --output-dir pub/media/import/wands \
  --model flux2-klein-4b \
  --quantize 4 \
  --width 768 \
  --height 768 \
  --steps 4 \
  --dry-run
```

Stopping the worker is safe. Re-run the generation command without `--overwrite`; completed JPEGs are skipped and only missing outputs are generated. oMLX is used for the optional description pass, not this image queue. MFLUX loads FLUX.2 Klein directly through Metal on the Mac Studio.

`build_media_csv.py` and `sync_generated_media.py` expand each visual image to every matching child SKU while checkpointing only after a successful Magento import.

### Rollback

Before application, retain the database and media backup. To roll back a converted batch without deleting generated audit data:

1. Run `lab:wands:convert-parents` with `--reverse` against that batch manifest. This removes configurable relations and restores the parent type to simple in one transaction per parent.
2. Import `rollback-parents.csv` to restore the original parent content and inventory fields.
3. Import `rollback-disable-bundles.csv` to disable and hide all generated bundles.
4. Reindex and verify the original 42,994 visible WANDS products.

For the bounded pilot, use `batches/pilot/rollback-parents.csv` and `batches/pilot/rollback-disable-bundles.csv`. These contain only the 25 reviewed parents and five pilot bundles.

Generated children remain enabled but individually hidden after this reversible rollback. Deleting them is a separate destructive cleanup and requires an exact reviewed SKU list.
