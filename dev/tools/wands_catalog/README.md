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
