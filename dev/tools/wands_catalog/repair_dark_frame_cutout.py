#!/usr/bin/env python3
"""Recover omitted opaque dark furniture frames on a confirmed white background."""
import argparse
import json
import logging
from pathlib import Path
from PIL import Image, ImageChops, ImageOps
from prepare_catalog import sha256
from repair_solid_cutout import fill_solid_interior
from validate_component_cutout import inspect_cutout
from verify_catalog_repairs import check


def recover_frame(source, cutout, confirmed):
    check(confirmed is True and source.mode == 'RGB' and cutout.mode == 'RGBA' and
          source.size == cutout.size, 'Confirm opaque dark furniture on white, with matching canvas')
    check(source.tobytes() == cutout.convert('RGB').tobytes(), 'Source RGB differs from cutout')
    border = [source.getpixel((x, y)) for x, y in
              [(0, 0), (source.width - 1, 0), (0, source.height - 1), (source.width - 1, source.height - 1)]]
    check(all(min(pixel) >= 240 for pixel in border), 'White backdrop not established')
    gray = ImageOps.grayscale(source)
    # Narrow contrast recovery only: dark frame is <=120, white background and
    # ordinary pale shadows >=160. Gray cushions remain from the segmentation mask.
    dark = gray.point(lambda value: 255 if value <= 120 else 0 if value >= 160
                      else round((160 - value) * 255 / 40))
    union = source.copy()
    union.putalpha(ImageChops.lighter(cutout.getchannel('A'), dark))
    result, _ = fill_solid_interior(union, True)
    difference = ImageChops.difference(result.getchannel('A'), cutout.getchannel('A'))
    count = source.width * source.height - difference.histogram()[0]
    check(result.convert('RGB').tobytes() == source.tobytes(), 'Recovery changed source RGB')
    return result, count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('source', 'cutout', 'output', 'log-file'):
        parser.add_argument('--' + flag, required=True, type=Path)
    for flag in ('source-sha256', 'cutout-sha256'):
        parser.add_argument('--' + flag, required=True)
    parser.add_argument('--confirm-opaque-dark-frame-on-white', action='store_true')
    args = parser.parse_args()
    if args.log_file.resolve() in {args.source.resolve(), args.cutout.resolve(), args.output.resolve()}:
        return 1
    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.log_file, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        check(not args.output.exists() and not args.output.is_symlink(), 'Use a fresh recovery path')
        check(sha256(args.source) == args.source_sha256 and sha256(args.cutout) == args.cutout_sha256,
              'Source or mask changed')
        with Image.open(args.source) as source, Image.open(args.cutout) as cutout:
            result, count = recover_frame(source, cutout, args.confirm_opaque_dark_frame_on_white)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('xb') as stream: result.save(stream, 'PNG')
        report = {**inspect_cutout(args.source, args.source_sha256, args.output),
                  'original_cutout_sha256': args.cutout_sha256, 'changed_alpha_pixels': count,
                  'runner_sha256': sha256(Path(__file__)), 'dark_alpha_range': [120, 160],
                  'method': 'dark-frame alpha union and enclosed solid interior; original RGB unchanged',
                  'visual_mask_acceptance': 'pending'}
        check(sha256(args.cutout) == args.cutout_sha256, 'Original mask changed')
        with args.output.with_name(args.output.name + '.json').open('x') as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
        logging.info('Dark frame recovery: %s', json.dumps(report, sort_keys=True))
        return int(report['contract_status'] != 'pass')
    except Exception:
        logging.exception('Recovery stopped without overwriting evidence')
        return 1


if __name__ == '__main__': raise SystemExit(main())
