#!/usr/bin/env python3
"""Prepare a geometry-only reference, not catalog imagery, for the nursery valance."""
import argparse
import json
import logging
import math
from pathlib import Path
import tempfile

from prepare_catalog import sha256
from run_catalog_component_pilot import verify_layouts
from run_catalog_media_pilot import verify_pins
from verify_catalog_repairs import check


def geometry(length, width, drop):
    check(all(type(v) in (int, float) and math.isfinite(v) and v > 0
              for v in (length, width, drop)), 'Invalid synthetic dimensions')
    return {'envelope_cm': [length + 2*drop, width + 2*drop],
            'panels': {'deck': [drop, drop, length, width],
                       'top': [drop, 0, length, drop],
                       'bottom': [drop, drop+width, length, drop],
                       'left': [0, drop, drop, width],
                       'right': [drop+length, drop, drop, width]}}


def render(spec):
    width, height = spec['envelope_cm']
    boxes = []
    for name, (x,y,w,h) in spec['panels'].items():
        fill = '#d3e7f1' if name == 'deck' else '#76afcb'
        boxes.append(f'<rect data-panel="{name}" x="{x}" y="{y}" width="{w}" '
                     f'height="{h}" fill="{fill}" stroke="#52869d" stroke-width="0.25"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{(width+32)*6}" '
            f'height="{(height+32)*6}" viewBox="-16 -16 {width+32} {height+32}">'
            f'<rect x="-16" y="-16" width="{width+32}" height="{height+32}" fill="white"/>'
            + ''.join(boxes) + '</svg>')


def build(args):
    check(not args.output_dir.exists() and not args.output_dir.is_symlink(), 'Use a fresh reference directory')
    briefs, pins = verify_layouts(args.layouts)
    brief = next(b for b in briefs if b['asset_requirement_id'] == 'WANDS-000056-skirt-3c9f27991ca2')
    dims = brief['component']['dimensions_cm']
    spec = geometry(dims['lab_spec_length_cm'], dims['lab_spec_width_cm'], dims['lab_spec_height_cm'])
    spec.update({'asset_requirement_id': brief['asset_requirement_id'],
                 'source_dimensions_cm': dims,
                 'presentation': 'unfolded attached panels, orthographic overhead; not folded-under footprint',
                 'scope': 'Synthetic geometry reference only, not a product photo, physical size or fit claim',
                 'publication_approved': False})
    pins[str(Path(__file__).resolve())] = sha256(Path(__file__))
    output = args.output_dir.resolve()
    check(not any(Path(p).is_relative_to(output) for p in pins), 'Output contains evidence')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.'+output.name+'-') as folder:
        stage = Path(folder)
        (stage/'geometry.json').write_text(json.dumps(spec, indent=2, sort_keys=True)+'\n')
        (stage/'reference.svg').write_text(render(spec))
        verify_pins(pins)
        manifest = {'version': 'wands-valance-geometry-reference-v1', 'inputs': pins,
                    'outputs': {p.name: sha256(p) for p in stage.iterdir()}, 'publication_approved': False}
        (stage/'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
        stage.rename(output)
    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layouts', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        logging.info('Reference prepared: %s', json.dumps(build(args), sort_keys=True))
        return 0
    except Exception:
        logging.exception('Reference preparation stopped without publication')
        return 1


if __name__ == '__main__': raise SystemExit(main())
