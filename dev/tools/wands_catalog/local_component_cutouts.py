#!/usr/bin/env python3
"""Local CPU segmentation, alpha-only attachment and read-only contract checks."""
import argparse
from html import escape
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path
import sys

from PIL import Image
from prepare_catalog import sha256
from validate_component_cutout import inspect_cutout
from verify_catalog_repairs import check
from run_catalog_media_pilot import publish_exclusive


def attach_alpha(image,mask):
    check(image.mode=='RGB' and mask.mode=='L' and image.size==mask.size,'Mask differs from original canvas')
    result=image.copy(); result.putalpha(mask); return result


def run(args):
    rows=json.loads(args.selection.read_text());output=args.output_dir
    check(0<len(rows)<=28 and len({r['asset_requirement_id'] for r in rows})==len(rows),'Invalid cutout selection')
    check(not output.exists() and not output.is_symlink(),'Use a fresh cutout directory')
    check(args.weights.is_file() and not args.weights.is_symlink(),'Use existing local weights')
    for r in rows:
        p=Path(r['image_path']);check(r['initial_visual_pass'] is True and sha256(p)==r['image_sha256'],'Unaccepted or changed cutout source')
        check(not p.resolve().is_relative_to(output.resolve()) and not output.resolve().is_relative_to(p.parent.resolve()),'Cutout output overlaps source')
    import onnxruntime as ort
    from rembg import new_session
    from rembg.sessions.birefnet_general import BiRefNetSessionGeneral
    # Use only these already downloaded weights. Do not ask the session to fetch anything.
    model_hash=sha256(args.weights)
    original_download=BiRefNetSessionGeneral.download_models
    BiRefNetSessionGeneral.download_models=classmethod(lambda cls,*a,**kw:str(args.weights.resolve()))
    options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
    try: session=new_session('birefnet-general',providers=['CPUExecutionProvider'],sess_opts=options)
    finally: BiRefNetSessionGeneral.download_models=original_download
    output.mkdir(parents=True); results=[]
    descriptor={'model':'birefnet-general','model_sha256':model_hash,'weights_path':str(args.weights.resolve()),
                'packages':{p:version(p) for p in ('rembg','onnxruntime','Pillow')},'providers':['CPUExecutionProvider'],
                'selection_sha256':sha256(args.selection),'runner_sha256':sha256(Path(__file__)),
                'alpha_method':'unmodified predicted mask; original RGB preserved','publication_approved':False}
    publish_exclusive(output/'run.json',(json.dumps(descriptor,indent=2,sort_keys=True)+'\n').encode())
    for r in rows:
        source=Path(r['image_path']);check(sha256(source)==r['image_sha256'],'Source changed')
        with Image.open(source) as image:
            masks=session.predict(image);check(len(masks)==1,'Expected exactly one segmentation mask')
            result=attach_alpha(image,masks[0])
        target=output/(r['asset_requirement_id']+'.png');result.save(target,'PNG')
        check(sha256(source)==r['image_sha256'],'Source changed during segmentation')
        report={**inspect_cutout(source,r['image_sha256'],target),'asset_requirement_id':r['asset_requirement_id']}
        results.append(report);publish_exclusive(output/(target.name+'.json'),(json.dumps(report,indent=2,sort_keys=True)+'\n').encode())
        logging.info('Cutout %s: %s %s',r['asset_requirement_id'],report['contract_status'],report['failures'])
    check(sha256(args.weights)==model_hash and sha256(args.selection)==descriptor['selection_sha256'],'Inputs changed')
    h=lambda x:escape(str(x),quote=True);cards=[]
    for r in results:
        pictures=''.join('<div style="background:'+color+'"><img src="'+h(Path(r['cutout_path']).as_uri())+'" alt="'+h(r['asset_requirement_id'])+'"></div>' for color in ('#fff','#222','#c94e88'))
        cards.append('<article><h2>'+h(r['asset_requirement_id'])+'</h2><p>Contract: '+h(r['contract_status'])+'; visual mask acceptance pending.</p><section>'+pictures+'</section></article>')
    html='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cutout review</title><style>body{font:16px system-ui;margin:24px;background:#eef2ef}article{background:white;padding:20px;margin-bottom:24px}h2{font-size:18px;overflow-wrap:anywhere}section{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}img{width:100%;height:580px;object-fit:contain}@media(max-width:700px){section{grid-template-columns:1fr}img{height:440px}}</style><h1>Alpha-only cutout evaluation</h1><p>Original product RGB pixels preserved. Contract checks do not approve visual mask quality or complete assortments.</p>'+''.join(cards)+'</html>'
    publish_exclusive(output/'review.html',html.encode())
    publish_exclusive(output/'summary.json',(json.dumps(results,indent=2,sort_keys=True)+'\n').encode())
    return {'processed':len(results),'contract_pass':sum(r['contract_status']=='pass' for r in results),'mask_ready':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('selection','weights','output-dir'):parser.add_argument('--'+flag,required=True,type=Path)
    args=parser.parse_args();args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    with args.output_dir.with_name(args.output_dir.name+'.log').open('a',buffering=1) as log:
        os.dup2(log.fileno(),sys.stdout.fileno());os.dup2(log.fileno(),sys.stderr.fileno())
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
        try:logging.info('Cutout summary: %s',json.dumps(run(args),sort_keys=True));return 0
        except Exception:logging.exception('Cutout pass stopped without changing sources');return 1


if __name__=='__main__':raise SystemExit(main())
