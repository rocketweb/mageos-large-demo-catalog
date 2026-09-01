# WANDS catalog tooling

This tooling prepares the pinned Wayfair WANDS product corpus for the isolated `wands` Mage-OS website.

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

Bundle batches use dynamic price, dynamic SKU, dynamic weight, and existing visible simple products as selections. They exclude configurable parents and all generated children. After the configurable pilot passes, validate and import `batches/pilot/bundles.csv`. Then import one five-bundle theme CSV at a time from `batches/bundles`.

### Variant media

Size-only children reuse the existing parent product image through `reuse-parent-media.csv`. Families with a visual color, finish, or material axis use `image-prompts.jsonl`; one generated image is shared by all size combinations with the same visual value.

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

`build_media_csv.py` and `sync_generated_media.py` expand each visual image to every matching child SKU while checkpointing only after a successful Magento import.

### Rollback

Before application, retain the database and media backup. To roll back a converted batch without deleting generated audit data:

1. Run `lab:wands:convert-parents` with `--reverse` against that batch manifest. This removes configurable relations and restores the parent type to simple in one transaction per parent.
2. Import `rollback-parents.csv` to restore the original parent content and inventory fields.
3. Import `rollback-disable-bundles.csv` to disable and hide all generated bundles.
4. Reindex and verify the original 42,994 visible WANDS products.

For the bounded pilot, use `batches/pilot/rollback-parents.csv` and `batches/pilot/rollback-disable-bundles.csv`. These contain only the 25 reviewed parents and five pilot bundles.

Generated children remain enabled but individually hidden after this reversible rollback. Deleting them is a separate destructive cleanup and requires an exact reviewed SKU list.
