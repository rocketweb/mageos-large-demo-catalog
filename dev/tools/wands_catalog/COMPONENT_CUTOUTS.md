# Component cutout handoff

This is a preparation and validation step, not an executed mask pipeline.
No background-removal runtime or weights were installed during the completion
pass. Keep the original RGB WebP candidates and their metadata unchanged.

## Source and output contract

- Start with a candidate whose current inventory status is `initial_visual_pass`.
  There are ten such component types in `component-readiness-v2`, not ten
  accepted masks. Use the exact proposed image path and SHA256 from that packet.
- Create a new RGBA PNG in an ignored, separate output directory. Retain the
  original canvas dimensions and decoded RGB values wherever alpha is nonzero.
  Do not resize, crop, recolor, composite or overwrite the source.
- Preserve thin fork tines, lamp stems, reflective highlights, quilting and
  other real product edges. White pixels can belong to the product. A simple
  white-threshold mask is not an acceptable substitute for segmentation.
- Transparent background and opaque foreground must both exist, with visible
  product pixels clear of the canvas boundary. Record the removal model's exact
  version, weights hash, settings, input hash and output hash with each result.
- Keep mask acceptance pending until a reviewer inspects the edges on light,
  dark and contrasting backgrounds. A file-contract pass cannot detect a
  missing tine, retained shadow, erased highlight, internal hole or edge halo.

## Read-only validator

Run `dev/tools/wands_catalog/validate_component_cutout.py` from the catalog
worktree, supplying `--source`, `--source-sha256`, `--cutout` and `--log-file`.
All four arguments are required. Use an ignored log path such as
`var/wands/cutout-validation/dinner-fork.log`; output stays quiet by default.
Tail that log to inspect the result. `--json` explicitly enables terminal JSON.
Exit status is zero for a contract pass and one for a failure.

The validator only reads the two image inputs. It checks source identity, RGBA
PNG format, exact canvas size, transparency, foreground margins and unchanged
RGB values under every nonzero alpha pixel. It returns the source and output
hashes, failure reasons and pixel counts. It always leaves `mask_ready`,
`assembly_ready` and `publication_approved` false, even when the contract passes.
Supplying an image as the log destination is rejected without modifying it.

The tests use generated synthetic rectangles, not catalog-image edits. A
successful test run is not evidence that any real product mask is usable.

## First representative evaluation

Evaluate the already passing dinner fork, floor lamp and nursery quilt before
processing the other seven candidates. These exercise thin metal, narrow stems
and pale fabric. Keep all failed masks and findings outside Git. If these
examples lose real geometry, repair the removal method before broad execution.
Family assembly still requires matching construction, finish, camera and scale,
as well as a visual pass for every component type in the assortment.
