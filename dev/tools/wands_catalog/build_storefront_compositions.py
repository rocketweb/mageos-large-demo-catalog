#!/usr/bin/env python3
"""Compact accepted pilot assortments into self-contained square storefront candidates."""
import argparse
import base64
from html import escape
import json
import logging
import math
from pathlib import Path
import tempfile
from build_nursery_assortment import pin_packet
from build_realism_review import write_json
from prepare_catalog import sha256
from run_catalog_media_pilot import verify_pins
from verify_catalog_repairs import check

GROUPS={'WANDS-000056':[2,1],'WANDS-003897':[4,4,2],'WANDS-017842':[15,15,15],
        'WANDS-030335':[3,4],'WANDS-035295':[3]}


def validate_acceptance(row, actual, expected):
    check(actual==expected and row['verdict']=='initial_visual_pass' and row['checks'] and
          all(v=='pass' for v in row['checks'].values()),'Missing or changed visual acceptance')


def pack(rows, groups):
    check(rows and sum(groups)==len(rows) and all(type(n) is int and n>0 for n in groups), 'Incomplete composition')
    check(len({r['instance_id'] for r in rows})==len(rows),'Duplicate physical piece')
    check(all(type(r[k]) in (int,float) and math.isfinite(r[k]) and r[k]>0
              for r in rows for k in ('width','height','uniform_scale')),'Invalid geometry')
    gap=20; blocks=[];cursor=0
    for count in groups:
        items=rows[cursor:cursor+count];cursor+=count
        blocks.append((items,sum(r['width'] for r in items)+gap*(count-1),max(r['height'] for r in items)))
    width=max(b[1] for b in blocks);height=sum(b[2] for b in blocks)+gap*(len(blocks)-1)
    scale=840/max(width,height);top=(1000-height*scale)/2;result=[]
    for items,w,h in blocks:
        left=(1000-w*scale)/2
        for r in items:
            result.append({**r,'x':left,'y':top+(h-r['height'])*scale,
                           'width':r['width']*scale,'height':r['height']*scale,
                           'uniform_scale':r['uniform_scale']*scale})
            left+=(r['width']+gap)*scale
        top+=(h+gap)*scale
    return result


def svg(rows,masks):
    images=[]
    for i,r in enumerate(rows):
        m=masks[r['asset_requirement_id']]
        check(sha256(Path(m['cutout_path']))==r['cutout_sha256'],'Cutout changed')
        encoded=base64.b64encode(Path(m['cutout_path']).read_bytes()).decode()
        bx,by,_,_=m['bounds'];iw,ih=m['size'];s=r['uniform_scale']
        images.append(f'<clipPath id="p{i}"><rect x="{r["x"]}" y="{r["y"]}" width="{r["width"]}" height="{r["height"]}"/></clipPath>'
                      f'<image data-instance="{escape(r["instance_id"])}" clip-path="url(#p{i})" href="data:image/png;base64,{encoded}" '
                      f'x="{r["x"]-bx*s}" y="{r["y"]-by*s}" width="{iw*s}" height="{ih*s}"/>')
    return '<svg xmlns="http://www.w3.org/2000/svg" width="2000" height="2000" viewBox="0 0 1000 1000"><rect width="1000" height="1000" fill="white"/>'+''.join(images)+'</svg>'


def build(args):
    out=args.output_dir.resolve();check(not out.exists() and not out.is_symlink(),'Use a fresh output directory')
    pins={};pin_packet(args.assortments,pins,'wands-assortment-preview-v1')
    pin_packet(args.nursery,pins,'wands-nursery-assortment-v1')
    old=json.loads((args.assortments/'assortments.json').read_text())
    nursery=json.loads((args.nursery/'assortment.json').read_text())
    observations=json.loads(args.observations.read_text());nobs=json.loads(args.nursery_observations.read_text())
    rows=[nursery]+[r for r in old if r['root_sku']!='WANDS-000056']
    check({r['root_sku'] for r in rows}==set(GROUPS) and len(rows)==5,'Pilot scope changed')
    validate_acceptance(nobs,sha256(args.nursery/'assortment.json'),nobs['assortment_sha256'])
    for r in rows[1:]:
        obs=next(x for x in observations['families'] if x['root_sku']==r['root_sku'])
        validate_acceptance(obs,sha256(args.assortments/'assortments.json'),observations['assortments_sha256'])
    mask_rows=json.loads((args.assortments/'accepted-masks.json').read_text())+json.loads((args.nursery/'accepted-masks.json').read_text())
    masks={}
    for m in mask_rows:
        key=m['asset_requirement_id']
        check(key not in masks or masks[key]['cutout_sha256']==m['cutout_sha256'],'Conflicting masks')
        masks[key]=m
    for p in (Path(__file__),args.observations,args.nursery_observations):pins[str(p.resolve())]=sha256(p)
    check(not any(Path(p).is_relative_to(out) or out.is_relative_to(Path(p).parent) for p in pins if Path(p).name=='manifest.json'),'Output overlaps evidence')
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent,prefix='.'+out.name+'-') as folder:
        stage=Path(folder);compositions=[];cards=[]
        for r in rows:
            sku=r['root_sku'];placements=pack(r['placements'],GROUPS[sku]);filename=sku+'.svg'
            check(len(placements)==r['required_instances'],'Sale unit changed')
            (stage/filename).write_text(svg(placements,masks))
            compositions.append({'root_sku':sku,'required_instances':r['required_instances'],'placements':placements,
                                 'svg':filename,'canvas':[2000,2000],'visual_acceptance':'pending','publication_approved':False})
            cards.append(f'<article id="{sku}"><h2>{sku}</h2><p>{r["required_instances"]} physical pieces. Compact inclusion composition.</p>'
                         f'<img src="{filename}" alt="{sku} complete synthetic assortment"><p>Synthetic lab design; not manufacturer verified. No physical fit or safety claim.</p></article>')
        write_json(stage/'compositions.json',compositions);write_json(stage/'accepted-masks.json',list(masks.values()))
        (stage/'review.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Storefront composition candidates</title><style>body{font:17px/1.5 system-ui;background:#eef2ef;color:#192b25;margin:0}main{max-width:1000px;margin:auto;padding:24px}'
            'article{background:white;padding:24px;margin:24px 0;border-radius:12px}img{width:100%;height:auto}p{overflow-wrap:anywhere}</style>'
            '<main><h1>Storefront composition candidates</h1><p>Local review. Same accepted pieces, tighter spacing, common scaling, no invented scene or extra accessories. Publication remains unapproved.</p>'+''.join(cards)+'</main></html>')
        verify_pins(pins);write_json(stage/'manifest.json',{'version':'wands-storefront-compositions-v1','inputs':pins,
            'outputs':{p.name:sha256(p) for p in stage.iterdir()},'publication_approved':False})
        stage.rename(out)
    return {'families':5,'physical_instances':sum(r['required_instances'] for r in rows)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for f in ('assortments','nursery','observations','nursery-observations','output-dir'):p.add_argument('--'+f,required=True,type=Path)
    a=p.parse_args();a.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=a.output_dir.with_suffix('.log'),level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:logging.info('Composition summary: %s',json.dumps(build(a),sort_keys=True));return 0
    except Exception:logging.exception('Composition stopped without publication');return 1


if __name__=='__main__':raise SystemExit(main())
