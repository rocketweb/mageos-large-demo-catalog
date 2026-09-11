#!/usr/bin/env python3
"""Restore alpha inside an explicitly reviewed solid handle, never its slotted head."""
import argparse
import json
import logging
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter
from prepare_catalog import sha256
from repair_solid_cutout import fill_solid_interior
from validate_component_cutout import inspect_cutout
from verify_catalog_repairs import check


def repair_handle(image, box, confirmed):
    check(confirmed is True and image.mode == 'RGBA', 'Explicit reviewed solid-handle confirmation required')
    check(len(box) == 4 and all(type(v) is int for v in box), 'Invalid handle region')
    x0, y0, x1, y1 = box
    check(0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height, 'Handle region outside image')
    crop = image.crop(box)
    filled, _ = fill_solid_interior(crop, True)
    # Confident silhouette plus enclosed-hole repair, eroded one pixel to retain
    # the model's antialiased outside contour. Only this solid handle may be opaque.
    interior = filled.getchannel('A').point(lambda v: 255 if v >= 128 else 0).filter(ImageFilter.MinFilter(3))
    alpha = ImageChops.lighter(crop.getchannel('A'), interior)
    repaired = image.copy()
    whole_alpha = image.getchannel('A').copy()
    whole_alpha.paste(alpha, (x0, y0))
    repaired.putalpha(whole_alpha)
    difference = ImageChops.difference(image.getchannel('A'), whole_alpha)
    changed = image.width * image.height - difference.histogram()[0]
    check(repaired.convert('RGB').tobytes() == image.convert('RGB').tobytes(), 'RGB changed')
    return repaired, changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('source', 'cutout', 'output', 'log-file'):
        parser.add_argument('--' + flag, required=True, type=Path)
    for flag in ('source-sha256', 'cutout-sha256'):
        parser.add_argument('--' + flag, required=True)
    parser.add_argument('--handle-box', type=int, nargs=4, required=True)
    parser.add_argument('--confirm-solid-handle', action='store_true')
    args = parser.parse_args()
    if args.log_file.resolve() in {args.source.resolve(), args.cutout.resolve(), args.output.resolve()}:
        return 1
    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.log_file, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        check(not args.output.exists() and not args.output.is_symlink(), 'Output would overwrite evidence')
        check(sha256(args.source) == args.source_sha256 and sha256(args.cutout) == args.cutout_sha256,
              'Source or cutout changed')
        with Image.open(args.cutout) as image:
            repaired, count = repair_handle(image, args.handle_box, args.confirm_solid_handle)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('xb') as stream:
            repaired.save(stream, 'PNG')
        result = {**inspect_cutout(args.source, args.source_sha256, args.output),
                  'original_cutout_sha256': args.cutout_sha256, 'handle_box': args.handle_box,
                  'changed_alpha_pixels': count, 'runner_sha256': sha256(Path(__file__)),
                  'method': 'reviewed solid handle interior only; RGB and outside region unchanged',
                  'visual_mask_acceptance': 'pending'}
        check(sha256(args.cutout) == args.cutout_sha256, 'Original cutout changed')
        with args.output.with_name(args.output.name + '.json').open('x') as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
        logging.info('Handle alpha repair: %s', json.dumps(result, sort_keys=True))
        return int(result['contract_status'] != 'pass')
    except Exception:
        logging.exception('Handle repair stopped without overwriting source evidence')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
