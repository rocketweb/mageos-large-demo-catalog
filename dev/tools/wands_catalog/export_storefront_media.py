#!/usr/bin/env python3
"""Rasterize reviewed self-contained SVGs and prepare content-addressed local derivatives."""
import argparse
from html import escape
import io
import json
import logging
from pathlib import Path
import subprocess
import tempfile
from PIL import Image,ImageChops,__version__ as pillow_version
from build_nursery_assortment import pin_packet
from build_realism_review import write_json
from prepare_catalog import sha256
from run_catalog_media_pilot import verify_pins
from verify_catalog_repairs import check
import hashlib


def verify_master(im):
    check(im.mode=='RGB' and im.size==(2000,2000),'Wrong raster canvas or mode')
    delta=ImageChops.difference(im,Image.new('RGB',im.size,'white')).convert('L')
    count=sum(delta.histogram()[12:])
    check(.01<count/(2000*2000)<.85,'Empty or implausibly full raster')
    check(all(min(im.getpixel(p))>=250 for p in ((0,0),(1999,0),(0,1999),(1999,1999))),'Non-white canvas corners')


def derivatives(im,sku,out):
    results=[]
    for role,fmt,edge,options in [('master','PNG',2000,{}),('import','JPEG',2000,{'quality':92,'subsampling':0,'optimize':True}),
                                   ('web','WEBP',1200,{'quality':88,'method':6}),('thumbnail','WEBP',400,{'quality':88,'method':6})]:
        image=im if edge==2000 else im.resize((edge,edge),Image.Resampling.LANCZOS)
        buffer=io.BytesIO();image.save(buffer,format=fmt,**options);content=buffer.getvalue();digest=hashlib.sha256(content).hexdigest()
        name=f'{sku}-{role}-{digest[:12]}.'+{'JPEG':'jpg','PNG':'png','WEBP':'webp'}[fmt]
        with (out/name).open('xb') as f:f.write(content)
        results.append({'role':role,'file':name,'sha256':digest,'bytes':len(content),'size':[edge,edge],'format':fmt})
    return results


def build(a):
    out=a.output_dir.resolve();check(not out.exists() and not out.is_symlink(),'Use a fresh export directory')
    pins={};pin_packet(a.compositions,pins,'wands-storefront-compositions-v1')
    observations=json.loads(a.observations.read_text())
    check(observations['compositions_sha256']==sha256(a.compositions/'compositions.json') and observations['publication_approved'] is False,'Review changed')
    rows=json.loads((a.compositions/'compositions.json').read_text());accepted={r['root_sku']:r for r in observations['families']}
    check(len(rows)==len(accepted)==5 and {r['root_sku'] for r in rows}==set(accepted),'Export scope changed')
    for p in (a.observations,Path(__file__)):pins[str(p.resolve())]=sha256(p)
    renderer=subprocess.run([a.magick,'-version'],check=True,capture_output=True,text=True).stdout.splitlines()[0]
    check(not any(Path(p).is_relative_to(out) or out.is_relative_to(Path(p).parent) for p in pins if Path(p).name=='manifest.json'),'Output overlaps evidence')
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent,prefix='.'+out.name+'-') as folder:
        stage=Path(folder);exports=[];cards=[]
        for row in rows:
            sku=row['root_sku'];source=a.compositions/row['svg'];review=accepted[sku]
            check(review['verdict']=='initial_visual_pass' and sha256(source)==review['svg_sha256'],'Unreviewed SVG')
            pins[str(Path(review['screenshot_path']).resolve())]=review['screenshot_sha256']
            # A pure format conversion of our hash-verified embedded-image SVG; no AI image edit.
            result=subprocess.run([a.magick,str(source),'-background','white','-alpha','remove','-alpha','off','-strip','png:-'],check=True,capture_output=True)
            with Image.open(io.BytesIO(result.stdout)) as image:im=image.convert('RGB')
            verify_master(im);files=derivatives(im,sku,stage)
            exports.append({'root_sku':sku,'physical_instances':row['required_instances'],'files':files,
                            'visual_acceptance':'pending','publication_approved':False})
            main=next(r for r in files if r['role']=='import');thumb=next(r for r in files if r['role']=='thumbnail')
            cards.append(f'<article id="{sku}"><h2>{sku}</h2><p>{row["required_instances"]} physical pieces. Synthetic lab design.</p>'
                         f'<img class="hero" src="{escape(main["file"])}" alt="{sku} complete assortment">'
                         f'<p>2000px JPEG: {main["bytes"]:,} bytes. 400px thumbnail below.</p><img class="thumb" src="{escape(thumb["file"])}" alt="{sku} thumbnail"></article>')
        write_json(stage/'exports.json',exports)
        (stage/'review.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Catalog raster exports</title>'
            '<style>body{font:17px/1.5 system-ui;background:#eef2ef;color:#192b25;margin:0}main{max-width:1000px;margin:auto;padding:24px}article{background:white;padding:24px;margin:24px 0;border-radius:12px}.hero{width:100%;height:auto}.thumb{max-width:100%;width:400px;height:auto}p{overflow-wrap:anywhere}</style>'
            '<main><h1>Catalog raster exports</h1><p>Five local candidates. Not uploaded or assigned. Synthetic assortments and dimensions, not manufacturer verified.</p>'+''.join(cards)+'</main></html>')
        verify_pins(pins);write_json(stage/'manifest.json',{'version':'wands-storefront-exports-v1','inputs':pins,
            'outputs':{p.name:sha256(p) for p in stage.iterdir()},'renderer':renderer,'pillow':pillow_version,
            'counts':{'families':5,'images':20,'import_files':5},'publication_approved':False})
        stage.rename(out)
    return {'families':5,'images':20,'import_bytes':sum(f['bytes'] for r in exports for f in r['files'] if f['role']=='import')}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for f in ('compositions','observations','output-dir'):p.add_argument('--'+f,required=True,type=Path)
    p.add_argument('--magick',default='magick');a=p.parse_args();a.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=a.output_dir.with_suffix('.log'),level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:logging.info('Export summary: %s',json.dumps(build(a),sort_keys=True));return 0
    except Exception:logging.exception('Export stopped without publication');return 1


if __name__=='__main__':raise SystemExit(main())
