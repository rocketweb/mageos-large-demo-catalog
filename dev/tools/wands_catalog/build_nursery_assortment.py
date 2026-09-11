#!/usr/bin/env python3
"""Verify the complete nursery set with an explicit unfolded-valance presentation."""
import argparse
from html import escape
import json
import logging
import math
from pathlib import Path
import tempfile

from PIL import Image
from build_assortment_preview import fit
from build_realism_review import write_json
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from prepare_valance_reference import geometry
from run_catalog_component_pilot import verify_layouts
from run_catalog_media_pilot import verify_pins
from validate_component_cutout import inspect_cutout
from verify_catalog_repairs import check

SKU = 'WANDS-000056'
CANVAS = [1000, 1000]
SCALE = 3
POSITIONS = {'quilt': [150, 60], 'sheets': [650, 60], 'skirt': [210, 540]}


def plan(parts, bounds):
    check(set(parts) == set(bounds) == set(POSITIONS), 'Complete three-component nursery set required')
    check(all(p['quantity'] == 1 for p in parts.values()), 'Nursery sale unit count changed')
    rows, boxes = [], []
    for name, (left, top) in POSITIONS.items():
        dims = parts[name]['dimensions_cm']
        w, h = dims['lab_spec_width_cm'], dims['lab_spec_length_cm']
        if name == 'skirt':
            w, h = geometry(h, w, dims['lab_spec_height_cm'])['envelope_cm']
        check(all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in (w,h)), 'Invalid envelope')
        box = {'x':left, 'y':top, 'width':w*SCALE, 'height':h*SCALE}
        check(left+box['width'] <= CANVAS[0] and top+box['height'] <= CANVAS[1], 'Slot outside canvas')
        for other in boxes:
            check(left+box['width'] <= other['x'] or other['x']+other['width'] <= left or
                  top+box['height'] <= other['y'] or other['y']+other['height'] <= top, 'Overlapping slots')
        boxes.append(box)
        x,y,width,height,scale = fit(bounds[name],box,False)
        rows.append({'component_id':name, 'instance_id':name+'-01',
                     'presentation': 'unfolded_cross' if name=='skirt' else 'original_overhead',
                     'presentation_envelope_cm':[w,h], 'synthetic_slot':box,
                     'x':x, 'y':y, 'width':width, 'height':height, 'uniform_scale':scale,
                     'width_fraction_of_slot':width/box['width'], 'height_fraction_of_slot':height/box['height']})
    return rows


def pin_packet(packet, pins, version):
    packet = packet.resolve()
    m = json.loads((packet/'manifest.json').read_text())
    check(m['version'] == version and m['publication_approved'] is False, 'Wrong or publication-approved packet')
    incoming = {**m['inputs'], str(packet/'manifest.json'):sha256(packet/'manifest.json')}
    for name, expected in m['outputs'].items():
        path = (packet/name).resolve()
        check(path.is_relative_to(packet), 'Output path escapes packet')
        incoming[str(path)] = expected
    check(all(k not in pins or pins[k]==v for k,v in incoming.items()), 'Conflicting provenance')
    verify_pins(incoming); pins.update(incoming)


def build(args):
    output = args.output_dir.resolve()
    check(not output.exists() and not output.is_symlink(), 'Use a fresh nursery output directory')
    briefs,pins = verify_layouts(args.layouts)
    parts = {b['component_id']:b['component'] for b in briefs if b['root_sku']==SKU}
    pin_packet(args.inventory,pins,'wands-component-repair-review-v1')
    pin_packet(args.geometry,pins,'wands-valance-geometry-reference-v1')
    spec = json.loads((args.geometry/'geometry.json').read_text())
    d = parts['skirt']['dimensions_cm']
    expected = geometry(d['lab_spec_length_cm'],d['lab_spec_width_cm'],d['lab_spec_height_cm'])
    check(spec['source_dimensions_cm']==d and spec['envelope_cm']==expected['envelope_cm'] and
          spec['panels']==expected['panels'], 'Geometry differs from unchanged synthetic definition')
    assets = {a['asset_requirement_id']:a for a in read_jsonl(args.inventory/'assets.proposed.jsonl') if a['root_sku']==SKU}
    reviews = json.loads(args.previous_masks.read_text()) + json.loads(args.mask_reviews.read_text())
    check(len({r['asset_requirement_id'] for r in reviews})==len(reviews), 'Duplicate mask review')
    selected = {}
    for r in reviews:
        key = r['asset_requirement_id']
        if key not in assets: continue
        a = assets[key]
        check(a['status']=='initial_visual_pass' and a['proposed_candidate']['image_sha256']==r['source_sha256'],
              'Mask is not the selected component pass')
        check(r['verdict']=='pass' and r['review_method']=='direct_image_inspection_on_white_dark_and_pink'
              and r['finding'].strip() and r['publication_approved'] is False, 'Missing local mask acceptance')
        if a['component_id']=='skirt':
            check(r.get('presentation')=='unfolded_cross', 'Unreviewed valance presentation')
        source,cutout = Path(r['source_path']),Path(r['cutout_path'])
        check(sha256(cutout)==r['cutout_sha256'], 'Reviewed cutout changed')
        contract = inspect_cutout(source,r['source_sha256'],cutout)
        check(contract['contract_status']=='pass', 'Cutout contract failed')
        with Image.open(cutout) as image: size=list(image.size)
        selected[a['component_id']] = {**r,'bounds':contract['foreground_bounds'],'size':size}
        pins[str(source.resolve())] = r['source_sha256']; pins[str(cutout.resolve())] = r['cutout_sha256']
        if 'screenshot_path' in r:
            pins[str(Path(r['screenshot_path']).resolve())] = r['screenshot_sha256']
    placements = plan(parts,{key:r['bounds'] for key,r in selected.items()})
    pictures = []
    for row in placements:
        r = selected[row['component_id']]; scale=row['uniform_scale']; bx,by,_,_=r['bounds']; iw,ih=r['size']
        row.update({'asset_requirement_id':r['asset_requirement_id'],'cutout_sha256':r['cutout_sha256']})
        clip = 'clip-'+row['component_id']
        pictures.append(f'<clipPath id="{clip}"><rect x="{row["x"]}" y="{row["y"]}" width="{row["width"]}" height="{row["height"]}"/></clipPath>'
                        f'<image data-instance="{row["instance_id"]}" clip-path="url(#{clip})" '
                        f'href="{escape(Path(r["cutout_path"]).as_uri(),quote=True)}" x="{row["x"]-bx*scale}" '
                        f'y="{row["y"]-by*scale}" width="{iw*scale}" height="{ih*scale}"/>')
    disclosure = next(b['required_disclosure'] for b in briefs if b['root_sku']==SKU)
    row = {'root_sku':SKU,'required_instances':3,'placements':placements,'status':'preview_ready',
           'canvas':CANVAS,'synthetic_slot_pixels_per_cm':SCALE,'family_visual_acceptance':'pending',
           'presentation_change':'Only the valance changes from folded-under to fully unfolded panels; original component dimensions remain unchanged.',
           'required_disclosure':disclosure,'publication_approved':False}
    html = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Complete nursery assortment</title><style>body{font:17px/1.5 system-ui;background:#eef2ef;color:#192b25;margin:0}'
            'main{max-width:1100px;margin:auto;padding:24px}article{padding:24px;background:white;border:1px solid #ccd8d0;border-radius:12px}'
            'svg{display:block;width:100%;height:auto}p{overflow-wrap:anywhere}@media(max-width:700px){main,article{padding:14px}}</style>'
            '<main><h1>Complete nursery assortment</h1><p>Local proof only. Exactly three separate decorative textiles. '
            'No crib, mattress, infant-sleep arrangement or fit claim.</p><article id="WANDS-000056">'
            '<h2>Ocean Baby Three-Piece Nursery Decor Set</h2><p>One quilt, one empty fitted sheet and one valance with four attached drop panels.</p>'
            '<svg role="img" aria-label="Three separate nursery-decor textiles" viewBox="0 0 1000 1000">'+''.join(pictures)+'</svg>'
            '<p>The valance is unfolded to show all four attached panels. Its derived 193 by 131 cm display envelope is not a new product dimension. '
            'The quilt and sheet retain their existing overhead presentation. Uniform scaling only; no independent-axis stretching.</p><p>'
            +escape(disclosure)+'</p></article><p>Family acceptance is a separate visual review. Nothing is approved for publication.</p></main></html>')
    for path in (Path(__file__),Path(__file__).with_name('prepare_valance_reference.py'),
                 Path(__file__).with_name('build_assortment_preview.py'),args.previous_masks,args.mask_reviews):
        pins[str(path.resolve())]=sha256(path)
    check(not any(Path(p).is_relative_to(output) for p in pins), 'Output contains source evidence')
    protected={Path(p).parent for p in pins if Path(p).name=='manifest.json' or Path(p).suffix.lower() in {'.png','.webp'}}
    check(not any(output.is_relative_to(p) for p in protected), 'Output overlaps source evidence')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='.'+output.name+'-') as folder:
        stage=Path(folder)
        write_json(stage/'assortment.json',row); write_json(stage/'accepted-masks.json',list(selected.values()))
        (stage/'review.html').write_text(html)
        verify_pins(pins)
        write_json(stage/'manifest.json',{'version':'wands-nursery-assortment-v1','inputs':pins,
                   'outputs':{p.name:sha256(p) for p in stage.iterdir()},'publication_approved':False})
        stage.rename(output)
    return {'accepted_masks':len(selected),'rendered_instances':len(placements),'family_visual_acceptance':'pending'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('layouts','inventory','geometry','previous-masks','mask-reviews','output-dir'):
        parser.add_argument('--'+flag,required=True,type=Path)
    args=parser.parse_args(); args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'),level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        logging.info('Nursery preview: %s',json.dumps(build(args),sort_keys=True)); return 0
    except Exception:
        logging.exception('Nursery preview stopped without publication'); return 1


if __name__=='__main__': raise SystemExit(main())
