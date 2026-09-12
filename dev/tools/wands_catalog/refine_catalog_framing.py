#!/usr/bin/env python3
"""Run one bounded, occupancy-based framing refinement; preserve every prior candidate."""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
from html import escape
import json
import logging
import math
import os
from pathlib import Path
import sys
import tempfile

from build_realism_review import write_json, write_jsonl
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from review_catalog_framing_pilot import verify_run, bind_observations
from run_catalog_component_pilot import prepare_runtime
from run_catalog_framing_pilot import TARGETS, generate, pending, validate_directory
from run_catalog_media_pilot import publish_exclusive, verify_pins
from verify_catalog_repairs import check


def choose_canvas(aspect):
    check(type(aspect) in (int,float) and math.isfinite(aspect) and 1<=aspect<=8,'Invalid refinement aspect')
    options=[(abs(math.log(h/w/aspect)),abs(w*h/(768**2)-1),w,h)
             for w in range(256,769,16) for h in range(768,2049,16) if abs(w*h/(768**2)-1)<=.01]
    _,_,w,h=min(options)
    check(abs(math.log(h/w/aspect))<=.04,'No bounded canvas approximates the requested aspect')
    return w,h


def refine_cases(rows):
    indexed={(r['case']['asset_requirement_id'],r['case']['arm']):r for r in rows}
    check(len(indexed)==len(rows)==4 and set(indexed)=={(key,arm) for key in TARGETS for arm in ('square','portrait')},
          'Refinement must use the exact paired framing review')
    cases=[]
    for key in TARGETS:
        row=indexed[(key,'portrait')]; c=row['case']; s=c['settings']
        check(row['verdict']=='fail' and row['checks']['proportions']=='fail' and
              all(v=='pass' for k,v in row['checks'].items() if k!='proportions'),'Refine only a proportion-only failure')
        target=row['target_ratio']; observed=row['estimated_ratio']
        check(all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in (target,observed)),'Invalid source ratios')
        desired=(s['height']/s['width'])*target/observed; width,height=choose_canvas(desired)
        proposal={**{k:v for k,v in c.items() if k!='candidate_filename'},'trial_id':key+'-refined','arm':'refined',
                  'settings':{**s,'width':width,'height':height},
                  'calibration':{'status':'hypothesis_not_acceptance','source_review_row_sha256':digest(row),
                                 'previous_image_sha256':row['image_sha256'],'desired_canvas_aspect':desired,
                                 'area_change_fraction':width*height/(768**2)-1,
                                 'method':'Previous canvas aspect times synthetic target divided by approximate observed silhouette ratio.'}}
        cases.append({**proposal,'candidate_filename':proposal['trial_id']+'-'+digest(proposal)[:12]+'.webp'})
    return cases


def prepare(source,approved_hash):
    source=source.resolve(); m=json.loads((source/'manifest.json').read_text())
    check(sha256(source/'manifest.json')==approved_hash and m['version']=='wands-framing-review-v1' and
          set(m['outputs'])=={'reviews.jsonl','review.html'} and {p.name for p in source.iterdir()}=={'manifest.json',*m['outputs']} and
          m['publication_approved'] is False,'Invalid refinement source fingerprint or state')
    pins={**m['inputs'],str(source/'manifest.json'):approved_hash,**{str(source/k):v for k,v in m['outputs'].items()}}
    verify_pins(pins); original_cases,original_pins=verify_run(Path(m['run']))
    check(all(pins.get(k)==v for k,v in original_pins.items()),'Missing refinement provenance')
    rows=read_jsonl(source/'reviews.jsonl')
    check([r['case'] for r in rows]==original_cases,'Source review differs from original trials')
    cases=refine_cases(rows)
    pins[str(Path(__file__).resolve())]=sha256(Path(__file__))
    runtime=json.loads((Path(m['run'])/'run.json').read_text())['runtime']
    descriptor={'version':'wands-framing-refinement-v1','source_review':str(source),'source_sha256':approved_hash,
                'inputs':pins,'runtime':runtime,'cases_sha256':digest(cases),'max_attempts':2,'publication_approved':False}
    return cases,rows,descriptor


def verify_output(output,cases,descriptor):
    validate_directory(output,cases)
    if output.exists() and any(output.iterdir()):
        check(json.loads((output/'run.json').read_text())==descriptor and read_jsonl(output/'execution-cases.jsonl')==cases,
              'Refinement descriptor or execution cases changed')
    return pending(cases,output)


def render(rows,prior):
    h=lambda v:escape(str(v),quote=True); cards=[]
    previous={r['case']['asset_requirement_id']:r for r in prior if r['case']['arm']=='portrait'}
    for r in rows:
        c=r['case']; old=previous[c['asset_requirement_id']]; s=c['settings']; source=c['source_case']
        figures=''.join('<figure><figcaption>'+h(label)+'</figcaption><a href="'+h(Path(path).as_uri())+'"><img src="'+
                       h(Path(path).as_uri())+'" alt="'+h(source['brief']['component']['label']+' '+label)+'"></a></figure>'
                       for label,path in [('Earlier portrait: 384 × 1536',old['image_path']),
                                          ('Refined: '+str(s['width'])+' × '+str(s['height']),r['image_path'])])
        cards.append('<article><h2>'+h(source['brief']['component']['label'])+'</h2><p><strong>'+h(r['verdict'].upper())+
            '</strong></p><div class="pair">'+figures+'</div><p>'+h(r['finding'])+'</p><p>Approximate silhouette H/W: '+
            f"{old['estimated_ratio']:.2f} → {r['estimated_ratio']:.2f}"+'; synthetic target '+f"{r['target_ratio']:.2f}"+
            '; signed ratio error '+f"{r['relative_ratio_error']:+.1%}"+'.</p><p><strong>Next:</strong> '+h(r['next_direction'])+
            '</p><details><summary>Actual prompt and provenance</summary><pre>'+h(source['runtime_prompt'])+'</pre><p>Seed '+str(source['seed'])+
            '; area change '+f"{c['calibration']['area_change_fraction']:+.2%}"+'.</p><p>'+h(source['brief']['required_disclosure'])+
            '</p><code>Image SHA256: '+h(r['image_sha256'])+'</code></details></article>')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Component framing refinement</title><style>*{box-sizing:border-box}body{background:#eef2ef;color:#192b25;font:17px/1.55 system-ui;margin:0}
main{max-width:1220px;margin:auto;padding:32px 24px}h1{font-size:clamp(2rem,4vw,3rem);line-height:1.15}article{background:white;padding:28px;margin:28px 0;border:1px solid #d0dcd3;border-radius:12px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}figure{margin:0;min-width:0}img{display:block;width:100%;height:600px;object-fit:contain}figcaption{margin:10px 0;font-size:14px}
.notice{background:#fff1cf;padding:18px;border-left:4px solid #a37322}summary,a{color:#165e8a}summary{cursor:pointer}pre,code{font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}pre{padding:18px;background:#eff3f0}
@media(max-width:700px){main{padding:20px 14px}article{padding:16px}.pair{grid-template-columns:1fr}img{height:480px}}
</style></head><body><main><h1>Product-specific framing refinement</h1><p>One new attempt per product. Prompt, seed and model stay unchanged;
canvas dimensions are selected from the prior observed silhouette. Pixel area stays within 1% of the earlier run, not exactly equal.</p>
<p class="notice">This calibration is a hypothesis, not a new acceptance threshold. Geometry remains a direct visual judgment against explicitly synthetic designs.
No masks, composites, catalog replacements or publication approvals are created. Canvas changes may alter construction details.</p>'''+''.join(cards)+'</main></body></html>\n'


def review(cases,prior,descriptor,output,notes_path,destination):
    check(not destination.exists() and not destination.is_symlink(),'Use a fresh refinement review directory')
    check(not verify_output(output,cases,descriptor),'Refinement is incomplete')
    pins={**descriptor['inputs'],**{str(p):sha256(p) for p in output.iterdir() if p.name!='.pilot.lock'},str(notes_path.resolve()):sha256(notes_path)}
    dest=destination.resolve(); protected={Path(p).parent for p in pins if Path(p).name in {'manifest.json','run.json'} or Path(p).suffix.lower() in {'.jpg','.png','.webp'}}
    check(not any(Path(p).is_relative_to(dest) for p in pins) and not any(dest.is_relative_to(p) for p in protected),'Review overlaps inputs')
    rows=bind_observations(cases,json.loads(notes_path.read_text()),output)
    counts=Counter(r['verdict'] for r in rows); counts={**{k:counts[k] for k in ('pass','fail','uncertain')},'reviewed':len(rows),'mask_ready':0,'assembly_ready':0,'publication_approved':0}
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent,prefix='.'+destination.name+'-') as folder:
        stage=Path(folder); write_jsonl(stage/'reviews.jsonl',rows); (stage/'review.html').write_text(render(rows,prior)); verify_pins(pins)
        write_json(stage/'manifest.json',{'version':'wands-framing-refinement-review-v1','inputs':pins,'outputs':{p.name:sha256(p) for p in sorted(stage.iterdir())},
                                        'counts':counts,'publication_approved':False})
        stage.rename(destination)
    return counts


def run(args):
    cases,prior,descriptor=prepare(args.source_review,args.approved_source_sha256); output=args.output_dir.resolve(); pins=descriptor['inputs']
    check(not args.output_dir.is_symlink() and not any(Path(p).is_relative_to(output) for p in pins),'Output overlaps source')
    protected={Path(p).parent for p in pins if Path(p).name=='manifest.json' or Path(p).suffix.lower() in {'.jpg','.png','.webp'}}
    check(not any(output.is_relative_to(p) for p in protected),'Output is inside source media or packet')
    check(bool(args.observations)==bool(args.review_dir) and not (args.run and args.observations),'Choose generation or a complete review request')
    if args.observations: return review(cases,prior,descriptor,output,args.observations,args.review_dir)
    _,runtime=prepare_runtime([c['source_case'] for c in cases]); check(runtime==descriptor['runtime'],'Runtime changed')
    todo=verify_output(output,cases,descriptor)
    logging.info('Refinement canvases: %s',json.dumps([{k:c[k] for k in ('trial_id','settings','calibration')} for c in cases],sort_keys=True))
    if not args.run or not todo: return {'selected':2,'pending':len(todo),'generated':0,'failed':0,'dry_run':not args.run}
    output.mkdir(parents=True,exist_ok=True); check(not (output/'.pilot.lock').is_symlink(),'Lock symlink is forbidden')
    with (output/'.pilot.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); validate_directory(output,cases)
        if not (output/'run.json').exists():
            publish_exclusive(output/'run.json',(json.dumps(descriptor,indent=2,sort_keys=True)+'\n').encode())
            publish_exclusive(output/'execution-cases.jsonl',''.join(json.dumps(c,sort_keys=True)+'\n' for c in cases).encode())
        todo=verify_output(output,cases,descriptor); pins={**pins,**{str(output/n):sha256(output/n) for n in ('run.json','execution-cases.jsonl')}}
        if not todo: return {'generated':0,'failed':0,'pending':0}
        verify_pins(pins)
        from mflux.models.common.config.model_config import ModelConfig
        from mflux.models.flux2.variants import Flux2Klein
        model=Flux2Klein(model_config=ModelConfig.from_name('flux2-klein-4b'),model_path=runtime['model_snapshot'],quantize=4)
        return generate(todo,output,model,lambda:verify_pins(pins))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('source-review','output-dir'): parser.add_argument('--'+flag,required=True,type=Path)
    parser.add_argument('--approved-source-sha256',required=True); parser.add_argument('--run',action='store_true')
    parser.add_argument('--observations',type=Path); parser.add_argument('--review-dir',type=Path); parser.add_argument('--json',action='store_true')
    args=parser.parse_args(); sink=args.review_dir or args.output_dir; sink.parent.mkdir(parents=True,exist_ok=True); saved=os.dup(sys.stdout.fileno())
    with sink.with_name(sink.name+'.log').open('a',buffering=1) as log:
        os.dup2(log.fileno(),sys.stdout.fileno()); os.dup2(log.fileno(),sys.stderr.fileno())
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
        try:
            result=run(args); logging.info('Refinement summary: %s',json.dumps(result,sort_keys=True))
            if args.json: os.write(saved,(json.dumps(result,sort_keys=True)+'\n').encode())
            return int(result.get('failed',0)>0)
        except Exception:
            logging.exception('Refinement stopped without retries, masks or catalog changes'); return 1
        finally: os.close(saved)


if __name__=='__main__':
    raise SystemExit(main())
