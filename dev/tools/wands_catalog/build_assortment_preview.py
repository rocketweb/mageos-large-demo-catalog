#!/usr/bin/env python3
"""Build exact-count local assortment previews only from reviewed components and masks."""
import argparse
from collections import Counter
from html import escape
import json
import logging
from pathlib import Path
import tempfile
from PIL import Image
from build_realism_review import write_json
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from run_catalog_component_pilot import verify_layouts
from run_catalog_media_pilot import verify_pins
from validate_component_cutout import inspect_cutout
from verify_catalog_repairs import check


def fit(bounds,box,baseline):
    w=bounds[2]-bounds[0];h=bounds[3]-bounds[1]
    check(w>0 and h>0 and box['width']>0 and box['height']>0,'Invalid image or layout bounds')
    scale=min(box['width']/w,box['height']/h);width=w*scale;height=h*scale
    return box['x']+(box['width']-width)/2,box['y']+box['height']-height if baseline else box['y']+(box['height']-height)/2,width,height,scale


def build(args):
    check(not args.output_dir.exists() and not args.output_dir.is_symlink(),'Use a fresh assortment review directory')
    _,pins=verify_layouts(args.layouts);packet=args.inventory.resolve();m=json.loads((packet/'manifest.json').read_text())
    check(m['version']=='wands-component-repair-review-v1' and m['publication_approved'] is False,'Wrong component inventory')
    incoming={**m['inputs'],str(packet/'manifest.json'):sha256(packet/'manifest.json'),**{str(packet/k):v for k,v in m['outputs'].items()}}
    check(all(k not in pins or pins[k]==v for k,v in incoming.items()),'Conflicting provenance');verify_pins(incoming);pins.update(incoming)
    assets=read_jsonl(packet/'assets.proposed.jsonl');index={a['asset_requirement_id']:a for a in assets}
    masks=json.loads(args.mask_reviews.read_text());accepted={}
    check(len({r['asset_requirement_id'] for r in masks})==len(masks),'Duplicate mask review')
    for r in masks:
        key=r['asset_requirement_id'];check(key in index and r['verdict']=='pass','Unreviewed mask')
        a=index[key];check(a['status']=='initial_visual_pass' and a['proposed_candidate']['image_sha256']==r['source_sha256'],'Mask source is not the selected visual pass')
        source=Path(r['source_path']);cutout=Path(r['cutout_path']);check(sha256(cutout)==r['cutout_sha256'],'Mask changed')
        check(r['review_method']=='direct_image_inspection_on_white_dark_and_pink' and r['finding'].strip(),'Missing visual mask evidence')
        contract=inspect_cutout(source,r['source_sha256'],cutout);check(contract['contract_status']=='pass','Cutout contract failed')
        with Image.open(cutout) as image:size=list(image.size)
        accepted[key]={**r,'bounds':contract['foreground_bounds'],'size':size}
        pins[str(cutout.resolve())]=r['cutout_sha256'];pins[str(source.resolve())]=r['source_sha256']
    layouts=read_jsonl(args.layouts/'layouts.proposed.jsonl');h=lambda x:escape(str(x),quote=True);families=[];cards=[]
    for layout in layouts:
        sku=layout['root_sku'];parts={a['component_id']:a for a in assets if a['root_sku']==sku}
        missing=[a['label'] for a in parts.values() if a['asset_requirement_id'] not in accepted]
        row={'root_sku':sku,'sale_unit':layout['sale_unit'],'required_instances':len(layout['instances']),
             'missing_components':missing,'status':'blocked' if missing else 'preview_ready','placements':[],
             'family_visual_acceptance':'pending','publication_approved':False}
        content='<p>Missing accepted component and mask: '+h(', '.join(missing))+'.</p>'
        if not missing:
            images=[];ids=[]
            for i,instance in enumerate(layout['instances']):
                a=parts[instance['component_id']];mask=accepted[a['asset_requirement_id']];b=instance['box']
                x,y,w,ht,scale=fit(mask['bounds'],b,layout['profile']=='shared_floor');ids.append(instance['instance_id'])
                bx,by,_,_=mask['bounds'];iw,ih=mask['size'];clip='clip-'+sku+'-'+str(i)
                images.append('<clipPath id="'+clip+'"><rect x="'+str(x)+'" y="'+str(y)+'" width="'+str(w)+'" height="'+str(ht)+'"/></clipPath><image data-instance="'+h(instance['instance_id'])+'" clip-path="url(#'+clip+')" href="'+h(Path(mask['cutout_path']).as_uri())+'" x="'+str(x-bx*scale)+'" y="'+str(y-by*scale)+'" width="'+str(iw*scale)+'" height="'+str(ih*scale)+'"/>')
                row['placements'].append({'instance_id':instance['instance_id'],'asset_requirement_id':a['asset_requirement_id'],
                    'cutout_sha256':mask['cutout_sha256'],'x':x,'y':y,'width':w,'height':ht,'uniform_scale':scale,
                    'width_fraction_of_synthetic_slot':w/b['width'],'height_fraction_of_synthetic_slot':ht/b['height']})
            check(len(set(ids))==len(ids),'Duplicate physical instance')
            check(Counter(i['component_id'] for i in layout['instances'])=={p:a['required_instances'] for p,a in parts.items()},'Assortment count mismatch')
            canvas=layout['canvas'];content='<svg role="img" aria-label="'+h(layout['sale_unit'])+'" viewBox="0 0 '+str(canvas['width'])+' '+str(canvas['height'])+'">'+''.join(images)+'</svg><p>Exact instance counts; uniform contain-fit inside the validated synthetic slots. Actual visual height can be smaller than the nominal slot because width and height are never stretched independently.</p>'
        families.append(row);cards.append('<article id="'+h(sku)+'"><h2>'+h(layout['product_name'])+'</h2><p>'+h(layout['sale_unit'])+' · '+h(row['status'])+'</p>'+content+'<p>'+h(layout['required_disclosure'])+'</p></article>')
    for p in (Path(__file__),args.mask_reviews):pins[str(p.resolve())]=sha256(p)
    output=args.output_dir.resolve();check(not any(Path(p).is_relative_to(output) for p in pins),'Output contains source evidence')
    protected={Path(p).parent for p in pins if Path(p).name=='manifest.json' or Path(p).suffix.lower() in {'.png','.webp','.jpg'}}
    check(not any(output.is_relative_to(p) for p in protected),'Output overlaps source evidence')
    html='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Assortment verification</title><style>body{font:17px/1.5 system-ui;background:#eef2ef;color:#192b25;margin:0}main{max-width:1200px;margin:auto;padding:24px}article{background:white;padding:24px;margin:24px 0;border:1px solid #ccd8d0;border-radius:12px}svg{display:block;width:100%;height:auto;background:white}h1{font-size:2.5rem}p{overflow-wrap:anywhere}@media(max-width:700px){main{padding:14px}article{padding:14px}h1{font-size:2rem}}</style><main><h1>Assortment verification</h1><p>Local review only. Incomplete sets are not assembled. Preview readiness is not family acceptance or publication approval.</p>'+''.join(cards)+'</main></html>'
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='.'+output.name+'-') as folder:
        stage=Path(folder);write_json(stage/'assortments.json',families);write_json(stage/'accepted-masks.json',list(accepted.values()));(stage/'review.html').write_text(html)
        verify_pins(pins);write_json(stage/'manifest.json',{'version':'wands-assortment-preview-v1','inputs':pins,'outputs':{p.name:sha256(p) for p in stage.iterdir()},
            'counts':{'families':len(families),'preview_ready':sum(f['status']=='preview_ready' for f in families),'accepted_masks':len(accepted)},'publication_approved':False})
        stage.rename(output)
    return {'families':len(families),'preview_ready':sum(f['status']=='preview_ready' for f in families),'accepted_masks':len(accepted)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('layouts','inventory','mask-reviews','output-dir'):parser.add_argument('--'+flag,required=True,type=Path)
    args=parser.parse_args();args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_name(args.output_dir.name+'.log'),level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:logging.info('Assortment summary: %s',json.dumps(build(args),sort_keys=True));return 0
    except Exception:logging.exception('Assortment preparation stopped without publication');return 1


if __name__=='__main__':raise SystemExit(main())
