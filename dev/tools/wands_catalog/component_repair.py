#!/usr/bin/env python3
"""Bounded local component repairs with explicit prompts and immutable attempt records."""
import argparse
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys

from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from run_catalog_component_pilot import verify_layouts, prepare_runtime
from run_catalog_framing_pilot import pending, validate_directory, generate
from run_catalog_media_pilot import verify_pins, publish_exclusive
from verify_catalog_repairs import check


def plan(briefs, assets, selection, pass_id):
    check(re.fullmatch(r'[a-z0-9-]+', pass_id) is not None, 'Invalid pass identifier')
    known = {(b['root_sku'], b['component_id']): b for b in briefs}
    allowed = {a['asset_requirement_id'] for a in assets if a['status'] in {'failed', 'uncertain'}}
    keys = [(s['root_sku'], s['component_id']) for s in selection]
    check(0 < len(keys) <= 18 and len(set(keys)) == len(keys) and set(keys) <= set(known), 'Invalid repair scope')
    cases = []
    for s in selection:
        b = known[s['root_sku'], s['component_id']]; key = b['asset_requirement_id']; w, h = s['canvas']
        check(key in allowed, 'Do not replace an initially passing component')
        check(all(type(v) is int and 256 <= v <= 3072 and v % 16 == 0 for v in (w,h)) and 500000 <= w*h <= 700000, 'Invalid canvas')
        check(isinstance(s['instruction'], str) and s['instruction'].strip(), 'Missing targeted repair instruction')
        prompt = 'Photorealistic studio catalog photograph of a single finished product on pure white. Soft diffuse upper-left light, minimal shadow.\n' + s['instruction'] + '\nEntire object visible with clear margins. No text, numbers, diagrams, labels, watermark, collage, extra products or people.'
        source = {'asset_requirement_id':key, 'root_sku':b['root_sku'], 'component_id':b['component_id'], 'brief':b,
                  'brief_sha256':digest(b), 'runtime_prompt':prompt, 'runtime_prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                  'seed':int(digest({'brief':b, 'selection':s, 'pass':pass_id})[:8],16)}
        cases.append({'trial_id':key+'-'+pass_id, 'asset_requirement_id':key, 'source_case':source, 'selection':s,
                      'settings':{'model':'flux2-klein-4b', 'quantize':4, 'width':w, 'height':h, 'steps':4, 'guidance':1.0},
                      'max_attempts':1, 'reference_inputs':[], 'publication_approved':False})
    return cases


def run(args):
    briefs, pins = verify_layouts(args.layouts); p = args.readiness.resolve(); m = json.loads((p/'manifest.json').read_text())
    check(m['version']=='wands-component-readiness-v2' and m['publication_approved'] is False, 'Unexpected readiness')
    incoming = {**m['inputs'], str(p/'manifest.json'):sha256(p/'manifest.json'), **{str(p/k):v for k,v in m['outputs'].items()}}
    check(all(k not in pins or pins[k]==v for k,v in incoming.items()), 'Conflicting provenance')
    verify_pins(incoming); pins.update(incoming)
    raw = plan(briefs, read_jsonl(p/'assets.proposed.jsonl'), json.loads(args.selection.read_text()), args.pass_id)
    compiled, runtime = prepare_runtime([c['source_case'] for c in raw]); pins.update(runtime['tokenizer_hashes'])
    cases=[]
    for c,s in zip(raw,compiled):
        item={**c,'source_case':{**c['source_case'],'token_count':s['token_count']}}
        cases.append({**item,'candidate_filename':c['trial_id']+'-'+digest(item)[:12]+'.webp'})
    for file in (args.selection, Path(__file__)):
        pins[str(file.resolve())]=sha256(file)
    output=args.output_dir.resolve()
    protected={Path(k).parent for k in pins if Path(k).name=='manifest.json' or Path(k).suffix.lower() in {'.webp','.png','.jpg'}}
    check(not args.output_dir.is_symlink() and not any(Path(k).is_relative_to(output) for k in pins) and not any(output.is_relative_to(k) for k in protected),'Output overlaps evidence')
    descriptor={'version':'wands-component-repair-v1','inputs':pins,'runtime':runtime,'cases_sha256':digest(cases),'max_attempts':len(cases),'publication_approved':False}
    validate_directory(output,cases)
    if (output/'run.json').exists():
        check(json.loads((output/'run.json').read_text())==descriptor and read_jsonl(output/'execution-cases.jsonl')==cases,'Repair inputs changed')
    todo=pending(cases,output); logging.info('Repair preflight: %d selected, %d pending',len(cases),len(todo))
    if not args.run or not todo:return {'pending':len(todo),'generated':0,'failed':0}
    output.mkdir(parents=True,exist_ok=True)
    with (output/'.pilot.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); validate_directory(output,cases)
        if not(output/'run.json').exists():
            publish_exclusive(output/'run.json',(json.dumps(descriptor,indent=2,sort_keys=True)+'\n').encode())
            publish_exclusive(output/'execution-cases.jsonl',''.join(json.dumps(c,sort_keys=True)+'\n' for c in cases).encode())
        todo=pending(cases,output); pins={**pins,**{str(output/n):sha256(output/n) for n in ('run.json','execution-cases.jsonl')}}
        verify_pins(pins)
        from mflux.models.common.config.model_config import ModelConfig
        from mflux.models.flux2.variants import Flux2Klein
        model=Flux2Klein(model_config=ModelConfig.from_name('flux2-klein-4b'),model_path=runtime['model_snapshot'],quantize=4)
        return generate(todo,output,model,lambda:verify_pins(pins))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('layouts','readiness','selection','output-dir'):parser.add_argument('--'+flag,required=True,type=Path)
    parser.add_argument('--pass-id',required=True);parser.add_argument('--run',action='store_true');args=parser.parse_args()
    args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    with args.output_dir.with_name(args.output_dir.name+'.log').open('a',buffering=1) as log:
        os.dup2(log.fileno(),sys.stdout.fileno());os.dup2(log.fileno(),sys.stderr.fileno())
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
        try:
            result=run(args);logging.info('Repair summary: %s',json.dumps(result,sort_keys=True));return int(result['failed']>0)
        except Exception:logging.exception('Repair stopped without retries');return 1


if __name__=='__main__':raise SystemExit(main())
