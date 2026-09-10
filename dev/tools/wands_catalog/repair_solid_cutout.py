#!/usr/bin/env python3
"""Repair enclosed alpha holes only for an explicitly confirmed solid silhouette."""
import argparse
import json
import logging
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageOps
from prepare_catalog import sha256
from validate_component_cutout import inspect_cutout
from verify_catalog_repairs import check


def fill_solid_interior(image, confirmed_solid):
    check(confirmed_solid is True and image.mode=='RGBA','Explicit solid-silhouette confirmation is required')
    alpha=image.getchannel('A')
    # Use foreground probability, not original RGB brightness. Soft but confident
    # foreground must form a barrier too; requiring alpha=255 leaks through metal.
    holes=ImageOps.expand(alpha.point(lambda v:0 if v>=128 else 255),border=1,fill=255)
    ImageDraw.floodfill(holes,(0,0),0)
    holes=holes.crop((1,1,image.width+1,image.height+1));count=holes.histogram()[255]
    result=image.copy();result.putalpha(ImageChops.lighter(alpha,holes))
    return result,count


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('source','cutout','output','log-file'):parser.add_argument('--'+flag,required=True,type=Path)
    parser.add_argument('--source-sha256',required=True);parser.add_argument('--cutout-sha256',required=True)
    parser.add_argument('--confirm-solid-silhouette',action='store_true');args=parser.parse_args()
    if args.log_file.resolve() in {args.source.resolve(),args.cutout.resolve(),args.output.resolve()}:return 1
    args.log_file.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.log_file,level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        check(not args.output.exists() and not args.output.is_symlink(),'Use a fresh repaired cutout path')
        check(sha256(args.source)==args.source_sha256 and sha256(args.cutout)==args.cutout_sha256,'Source or mask changed')
        with Image.open(args.cutout) as im:fixed,count=fill_solid_interior(im,args.confirm_solid_silhouette)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('xb') as stream:fixed.save(stream,'PNG')
        check(sha256(args.source)==args.source_sha256 and sha256(args.cutout)==args.cutout_sha256,'Inputs changed')
        result={**inspect_cutout(args.source,args.source_sha256,args.output),'original_cutout_sha256':args.cutout_sha256,
                'filled_enclosed_alpha_pixels':count,'method':'solid silhouette only; enclosed alpha holes filled; exterior and RGB unchanged',
                'visual_mask_acceptance':'pending'}
        with args.output.with_name(args.output.name+'.json').open('x') as stream:json.dump(result,stream,indent=2,sort_keys=True)
        logging.info('Solid cutout repair: %s',json.dumps(result,sort_keys=True));return int(result['contract_status']!='pass')
    except Exception:logging.exception('Solid cutout repair stopped without overwriting inputs');return 1


if __name__=='__main__':raise SystemExit(main())
