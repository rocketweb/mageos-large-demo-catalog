#!/usr/bin/env python3
"""Complete selected component trials in fixed batches; no retries, downloads or live media writes."""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
from html import escape
import json
import logging
import os
from pathlib import Path
import sys
import tempfile

from build_realism_review import write_json, write_jsonl
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from review_catalog_framing_pilot import bind_observations
from run_catalog_component_pilot import select_cases, verify_layouts, prepare_runtime
from run_catalog_framing_pilot import generate, pending, validate_directory
from run_catalog_media_pilot import publish_exclusive, verify_pins
from verify_catalog_repairs import check

BATCHES=('lamps','flatware','bakeware','nursery','outdoor')


def plan_cases(briefs,selection,states,previous):
    known={b['asset_requirement_id']:b for b in briefs}
    check(isinstance(selection,list) and 0<len(selection)<=25,'Select at most 25 exact components')
    ids=[s['asset_requirement_id'] for s in selection]
    check(len(set(ids))==len(ids) and set(ids)<=set(known),'Unknown or duplicate selected component')
    cases=[]
    for s in selection:
        key=s['asset_requirement_id']; b=known[key]
        check(states.get(key) in {'unattempted','uncertain'},'Do not regenerate a passed component')
        check(s['batch'] in BATCHES and type(s['preserve_previous_prompt']) is bool,'Invalid batch or prompt policy')
        dims=s['canvas']
        check(isinstance(dims,list) and len(dims)==2 and all(type(v) is int and 256<=v<=2048 and v%16==0 for v in dims) and
              500000<=dims[0]*dims[1]<=650000,'Invalid or excessive canvas')
        if s['preserve_previous_prompt']:
            check(key in previous and previous[key]['brief']==b,'Previous prompt is missing or bound to another brief')
            source=previous[key]
        else:
            check(isinstance(s['visual_instruction'],str) and s['visual_instruction'].strip(),'Missing visual instruction')
            source=select_cases([b],[{'asset_requirement_id':key,'visual_instruction':s['visual_instruction'],
                                      'purpose':'One initial component candidate for '+s['batch'],'max_attempts':1}])[0]
        cases.append({'trial_id':key+'-completion','asset_requirement_id':key,'batch':s['batch'],'source_case':source,
                      'settings':{'model':'flux2-klein-4b','quantize':4,'width':dims[0],'height':dims[1],'steps':4,'guidance':1.0},
                      'selection':s,'max_attempts':1,'reference_inputs':[],'publication_approved':False,
                      'appearance_instructions_are_synthetic':True})
    return cases


def finalize_cases(cases,tokens):
    check(len(cases)==len(tokens) and all(type(t) is int and 0<t<=512 for t in tokens),'Invalid actual prompt token counts')
    output=[]
    for c,t in zip(cases,tokens):
        item={**c,'source_case':{**c['source_case'],'token_count':t}}
        output.append({**item,'candidate_filename':c['trial_id']+'-'+digest(item)[:12]+'.webp'})
    return output


def prepare(args):
    check(sha256(args.selection)==args.selection_sha256,'Selection fingerprint changed')
    briefs,pins=verify_layouts(args.layouts); packet=args.readiness.resolve(); m=json.loads((packet/'manifest.json').read_text())
    check(m['version']=='wands-component-readiness-v1' and m['publication_approved'] is False and
          set(m['outputs'])=={'assets.proposed.jsonl','families.jsonl','review.html'},'Unexpected readiness packet')
    incoming={**m['inputs'],str(packet/'manifest.json'):sha256(packet/'manifest.json'),**{str(packet/k):v for k,v in m['outputs'].items()}}
    check(all(k not in pins or pins[k]==v for k,v in incoming.items()),'Conflicting readiness provenance')
    verify_pins(incoming);pins.update(incoming); states={};previous={}
    for a in read_jsonl(packet/'assets.proposed.jsonl'):
        states[a['asset_requirement_id']]=a['status']
        if a['proposed_candidate']:
            meta=Path(a['proposed_candidate']['image_path']+'.json')
            check(str(meta) in pins,'Candidate metadata is not pinned')
            c=json.loads(meta.read_text())['case'];previous[a['asset_requirement_id']]=c.get('source_case',c)
    all_cases=plan_cases(briefs,json.loads(args.selection.read_text()),states,previous)
    cases=[c for c in all_cases if c['batch']==args.batch]
    check(0<len(cases)<=8,'Batch must contain one to eight attempts')
    pins[str(args.selection.resolve())]=args.selection_sha256
    for name in ('component_completion.py','run_catalog_framing_pilot.py','review_catalog_framing_pilot.py'):
        p=Path(__file__).with_name(name).resolve();pins[str(p)]=sha256(p)
    output=args.output_dir.resolve()
    check(not args.output_dir.is_symlink() and not any(Path(p).is_relative_to(output) for p in pins),'Output overlaps source')
    protected={Path(p).parent for p in pins if Path(p).name=='manifest.json' or Path(p).suffix.lower() in {'.jpg','.png','.webp'}}
    check(not any(output.is_relative_to(p) for p in protected),'Output inside source media or packets')
    return cases,pins,output


def descriptor(cases,pins,runtime,batch):
    return {'version':'wands-component-completion-v1','batch':batch,'inputs':pins,'runtime':runtime,
            'cases_sha256':digest(cases),'max_attempts':len(cases),'publication_approved':False}


def verify_output(output,cases,description):
    validate_directory(output,cases)
    if output.exists() and any(output.iterdir()):
        check(json.loads((output/'run.json').read_text())==description and read_jsonl(output/'execution-cases.jsonl')==cases,
              'Existing batch descriptor or cases changed')
    return pending(cases,output)


def render(rows):
    h=lambda v:escape(str(v),quote=True);cards=[]
    for r in rows:
        c=r['case'];s=c['source_case'];dims=c['settings']
        cards.append('<article><p>'+h(c['asset_requirement_id'])+'</p><h2>'+h(s['brief']['component']['label'])+'</h2><p><strong>'+h(r['verdict'].upper())+
            '</strong></p><a href="'+h(Path(r['image_path']).as_uri())+'"><img src="'+h(Path(r['image_path']).as_uri())+'" alt="'+h(s['brief']['component']['label'])+
            '"></a><p>'+h(r['finding'])+'</p><p>Approximate envelope H/W '+f"{r['estimated_ratio']:.2f}"+'; synthetic target '+f"{r['target_ratio']:.2f}"+
            '.</p><p><strong>Next:</strong> '+h(r['next_direction'])+'</p><details><summary>Actual prompt and provenance</summary><pre>'+h(s['runtime_prompt'])+
            '</pre><p>Seed '+str(s['seed'])+'; '+str(s['token_count'])+'/512 tokens; '+str(dims['width'])+' × '+str(dims['height'])+
            '.</p><p>'+h(s['brief']['required_disclosure'])+'</p><code>'+h(r['image_sha256'])+'</code></details></article>')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Component completion review</title><style>*{box-sizing:border-box}body{margin:0;background:#eef2ef;color:#192b25;font:17px/1.55 system-ui}
main{max-width:1200px;margin:auto;padding:30px 24px}h1{font-size:clamp(2rem,4vw,3rem)}.cards{display:grid;grid-template-columns:1fr 1fr;gap:24px}
article{min-width:0;padding:24px;background:white;border:1px solid #d0dcd3;border-radius:12px}article>p:first-child{font-size:12px;overflow-wrap:anywhere}
img{width:100%;height:420px;object-fit:contain}pre,code{font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}pre{background:#eef2ef;padding:15px}
.notice{padding:18px;background:#fff1cf;border-left:4px solid #a37322}summary,a{color:#165e8a}summary{cursor:pointer}
@media(max-width:700px){main{padding:20px 14px}.cards{grid-template-columns:1fr}article{padding:16px}}
</style></head><body><main><h1>Component completion review</h1><p class="notice">Initial component screening, not assembly acceptance.
No masks, complete-set approvals or live media assignments are created. Bounds are approximate diagnostics, not manufacturer dimensions.
Matching finishes, viewpoints and component roles still require family-level checks.</p><div class="cards">'''+''.join(cards)+'</div></main></body></html>\n'


def review(args,raw,pins,output):
    d=json.loads((output/'run.json').read_text()); executed=read_jsonl(output/'execution-cases.jsonl')
    verify_pins(d['inputs']); runtime=d['runtime']; pins={**pins,**runtime['tokenizer_hashes']}
    cases=finalize_cases(raw,[c['source_case']['token_count'] for c in executed])
    check(not verify_output(output,cases,descriptor(cases,pins,runtime,args.batch)),'Batch is incomplete')
    notes=args.observations; destination=args.review_dir
    check(not destination.exists() and not destination.is_symlink(),'Use a fresh completion review directory')
    pins={**pins,**{str(p):sha256(p) for p in output.iterdir() if p.name!='.pilot.lock'},str(notes.resolve()):sha256(notes)}
    dest=destination.resolve();protected={Path(p).parent for p in pins if Path(p).name in {'manifest.json','run.json'} or Path(p).suffix.lower() in {'.jpg','.png','.webp'}}
    check(not any(Path(p).is_relative_to(dest) for p in pins) and not any(dest.is_relative_to(p) for p in protected),'Review overlaps source')
    rows=bind_observations(cases,json.loads(notes.read_text()),output);counts=Counter(r['verdict'] for r in rows)
    counts={**{k:counts[k] for k in ('pass','fail','uncertain')},'reviewed':len(rows),'mask_ready':0,'assembly_ready':0,'publication_approved':0}
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent,prefix='.'+destination.name+'-') as folder:
        stage=Path(folder);write_jsonl(stage/'reviews.jsonl',rows);(stage/'review.html').write_text(render(rows));verify_pins(pins)
        write_json(stage/'manifest.json',{'version':'wands-component-completion-review-v1','batch':args.batch,'inputs':pins,
                   'outputs':{p.name:sha256(p) for p in stage.iterdir()},'counts':counts,'publication_approved':False})
        stage.rename(destination)
    return counts


def run(args):
    raw,pins,output=prepare(args)
    check(bool(args.observations)==bool(args.review_dir) and not(args.run and args.observations),'Choose generation or review mode')
    if args.observations:return review(args,raw,pins,output)
    compiled,runtime=prepare_runtime([c['source_case'] for c in raw])
    cases=finalize_cases(raw,[c['token_count'] for c in compiled]);pins={**pins,**runtime['tokenizer_hashes']}
    d=descriptor(cases,pins,runtime,args.batch);todo=verify_output(output,cases,d)
    logging.info('Completion preflight: %s, %d selected, %d pending; prompt tokens %s',args.batch,len(cases),len(todo),[c['source_case']['token_count'] for c in cases])
    if not args.run or not todo:return {'selected':len(cases),'pending':len(todo),'generated':0,'failed':0,'dry_run':not args.run}
    output.mkdir(parents=True,exist_ok=True);check(not(output/'.pilot.lock').is_symlink(),'Lock symlink is forbidden')
    with (output/'.pilot.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);validate_directory(output,cases)
        if not(output/'run.json').exists():
            publish_exclusive(output/'run.json',(json.dumps(d,indent=2,sort_keys=True)+'\n').encode())
            publish_exclusive(output/'execution-cases.jsonl',''.join(json.dumps(c,sort_keys=True)+'\n' for c in cases).encode())
        todo=verify_output(output,cases,d);pins={**pins,**{str(output/n):sha256(output/n) for n in ('run.json','execution-cases.jsonl')}}
        if not todo:return {'generated':0,'failed':0,'pending':0}
        verify_pins(pins)
        from mflux.models.common.config.model_config import ModelConfig
        from mflux.models.flux2.variants import Flux2Klein
        model=Flux2Klein(model_config=ModelConfig.from_name('flux2-klein-4b'),model_path=runtime['model_snapshot'],quantize=4)
        return generate(todo,output,model,lambda:verify_pins(pins))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('layouts','readiness','selection','output-dir'):parser.add_argument('--'+flag,required=True,type=Path)
    parser.add_argument('--selection-sha256',required=True);parser.add_argument('--batch',choices=BATCHES,required=True)
    parser.add_argument('--run',action='store_true');parser.add_argument('--observations',type=Path);parser.add_argument('--review-dir',type=Path);parser.add_argument('--json',action='store_true')
    args=parser.parse_args();sink=args.review_dir or args.output_dir;sink.parent.mkdir(parents=True,exist_ok=True);saved=os.dup(sys.stdout.fileno())
    with sink.with_name(sink.name+'.log').open('a',buffering=1) as log:
        os.dup2(log.fileno(),sys.stdout.fileno());os.dup2(log.fileno(),sys.stderr.fileno())
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
        try:
            result=run(args);logging.info('Completion summary: %s',json.dumps(result,sort_keys=True))
            if args.json:os.write(saved,(json.dumps(result,sort_keys=True)+'\n').encode())
            return int(result.get('failed',0)>0)
        except Exception:logging.exception('Completion stopped without retries or live changes');return 1
        finally:os.close(saved)


if __name__=='__main__':raise SystemExit(main())
