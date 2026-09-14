# Optional detail and room galleries

The separate gallery package adds two illustrations to each of seven products.
Install it only after the full enriched catalog has imported successfully. It
does not replace hero images. Room furnishings are styling, not included items.

From the download directory, with the current verified helper scripts:

```sh
WANDS_GALLERY_PIN=6c1f924b8e9f1e2048f48d0426a3e0e9de885b4e2cc004058a45fa3c08e60ce5
python3 github_download.py --anonymous --repo rocketweb/mageos-large-demo-catalog \
  --tag catalog-2026.09.13-enriched-v2 --profile gallery --cache-dir ./cache \
  --manifest-sha256 "$WANDS_GALLERY_PIN"
python3 release.py "./cache/$WANDS_GALLERY_PIN" \
  --manifest-sha256 "$WANDS_GALLERY_PIN" --extract ./gallery-staging
```

Retain a database backup and the current gallery state for WANDS-000082,
WANDS-000083, WANDS-000084, WANDS-000304, WANDS-000639, WANDS-000710 and
WANDS-000711. All seven must already exist. The CSV changes only additional
images and captions; it contains no base, small or thumbnail role assignment.

Run from the Mage-OS root as its filesystem owner. Replace the example download
directory with its absolute path as seen inside the destination environment:

```sh
WANDS_GALLERY=/path/to/wands-demo/gallery-staging
test ! -e pub/media/import/wands-lab/galleries && \
  mkdir -p pub/media/import/wands-lab/galleries && \
  cp -R "$WANDS_GALLERY/media/wands-lab/galleries/." pub/media/import/wands-lab/galleries/
mkdir -p var/wands-lab/gallery
cp "$WANDS_GALLERY/data/gallery-additions.csv" var/wands-lab/gallery/gallery-additions.csv
php bin/magento lab:wands:import --file=var/wands-lab/gallery/gallery-additions.csv \
  > var/log/wands-gallery.log 2>&1
```

Stop on any nonzero exit. Use the corrected v2 module, which uses native append
behavior. Keep the CSV's nested caption quoting intact: the importer enables
`FIELDS_ENCLOSURE`, so ordinary comma-separated captions are not sufficient.

Reindex and clean caches. Verify exactly 14 additions, their hashes against
`data/gallery-provenance.json`, separate detail/room captions, appended positions
and unchanged prior entries and hero roles. Check the actual storefront slides.
See [the pinned acceptance report](ENRICHED_ACCEPTANCE.md) for tested limits.

The original image files and all earlier package versions remain unchanged.
Rollback restores the retained database/gallery state; do not delete images that
another product references. There is no automatic populated-store rollback tool
in this recipient package.
