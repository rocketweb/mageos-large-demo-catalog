#!/usr/bin/env python3
"""Read-only cutout contract checks. Never create masks or grant visual acceptance."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from PIL import Image, ImageChops
from prepare_catalog import sha256
from verify_catalog_repairs import check


def inspect_cutout(source, source_sha256, cutout):
    check(source.is_file() and cutout.is_file() and not source.is_symlink() and not cutout.is_symlink(), 'Use regular source and cutout files')
    check(source.resolve() != cutout.resolve() and sha256(source) == source_sha256, 'Source changed or cutout replaces source')
    cutout_sha256 = sha256(cutout); failures = []; bounds = None; transparent = opaque = altered = None
    with Image.open(source) as original, Image.open(cutout) as candidate:
        check(original.mode == 'RGB' and original.format == 'WEBP', 'Expected the unchanged RGB WebP generation candidate')
        if candidate.mode != 'RGBA' or candidate.format != 'PNG': failures.append('expected_rgba_png')
        if candidate.size != original.size: failures.append('canvas_changed')
        if not failures:
            alpha = candidate.getchannel('A'); hist = alpha.histogram()
            transparent = hist[0]; opaque = hist[255]; bounds = alpha.getbbox()
            if not transparent: failures.append('no_fully_transparent_background')
            if not opaque: failures.append('no_fully_opaque_foreground')
            if bounds is None: failures.append('empty_foreground')
            elif bounds[0] == 0 or bounds[1] == 0 or bounds[2] == original.width or bounds[3] == original.height:
                failures.append('foreground_touches_canvas_edge')
            delta = ImageChops.difference(original, candidate.convert('RGB'))
            red, green, blue = delta.split()
            changed = ImageChops.lighter(ImageChops.lighter(red, green), blue).point(lambda v: 255 if v else 0)
            foreground = alpha.point(lambda v: 255 if v else 0)
            altered = ImageChops.multiply(changed, foreground).histogram()[255]
            if altered: failures.append('visible_product_rgb_changed')
    check(sha256(source) == source_sha256 and sha256(cutout) == cutout_sha256, 'Inputs changed during inspection')
    return {'source_path': str(source.resolve()), 'source_sha256': source_sha256,
            'cutout_path': str(cutout.resolve()), 'cutout_sha256': cutout_sha256,
            'contract_status': 'fail' if failures else 'pass', 'failures': failures,
            'foreground_bounds': list(bounds) if bounds else None,
            'transparent_pixels': transparent, 'opaque_pixels': opaque, 'altered_visible_rgb_pixels': altered,
            'visual_mask_acceptance': 'not_evaluated', 'mask_ready': False, 'assembly_ready': False,
            'publication_approved': False,
            'limitations': 'A contract pass cannot detect missing tines, erased highlights, retained shadows, holes or halos. Inspect the mask on contrasting backgrounds and verify family-level acceptance separately.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path); parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--cutout', required=True, type=Path); parser.add_argument('--log-file', required=True, type=Path)
    parser.add_argument('--json', action='store_true'); args = parser.parse_args()
    if args.log_file.resolve() in {args.source.resolve(), args.cutout.resolve()} or args.log_file.is_symlink():
        return 1  # There is no safe log destination; do not fall back to terminal output.
    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.log_file, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        result = inspect_cutout(args.source, args.source_sha256, args.cutout)
        logging.info('Cutout contract: %s', json.dumps(result, sort_keys=True))
        if args.json: print(json.dumps(result, sort_keys=True))
        return int(result['contract_status'] != 'pass')
    except Exception:
        logging.exception('Cutout validation stopped without altering images'); return 1


if __name__ == '__main__': raise SystemExit(main())
