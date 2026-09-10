#!/usr/bin/env python3
"""Compare four local, equal-area canvas trials. Offline, quiet, immutable, no automatic retries."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from PIL import Image
from catalog_repairs import read_jsonl
from generate_images import append_event
from plan_catalog_media_repairs import SETTINGS
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from review_catalog_component_pilot import verify_completed
from run_catalog_component_pilot import prepare_runtime
from run_catalog_media_pilot import publish_exclusive, safe_target, verify_pins
from verify_catalog_repairs import check

TARGETS = ('WANDS-035295-floor-lamp-61065fe722ea', 'WANDS-017842-cake-server-e8b0f8c3de5c')
CANVASES = {'square':(768,768), 'portrait':(384,1536)}


def make_cases(rows):
    indexed = {r['case']['asset_requirement_id']:r for r in rows}
    check(len(indexed)==len(rows) and set(TARGETS)<=set(indexed), 'Missing or duplicate framing sources')
    cases=[]
    for key in TARGETS:
        row=indexed[key]
        check(row['verdict']=='fail', 'Framing scope must remain the two failed components')
        for arm,(width,height) in CANVASES.items():
            c={'trial_id':key+'-'+arm, 'asset_requirement_id':key, 'arm':arm,
               'source_case':row['case'], 'source_image_sha256':row['image_sha256'],
               'settings':{'model':SETTINGS['model'],'quantize':4,'width':width,'height':height,'steps':4,'guidance':1.0},
               'max_attempts':1, 'reference_inputs':[], 'publication_approved':False}
            cases.append({**c,'candidate_filename':c['trial_id']+'-'+digest(c)[:12]+'.webp'})
    return cases


def verify_source(packet, approved_hash):
    check(re.fullmatch(r'[0-9a-f]{64}',approved_hash or '') is not None, 'Invalid source approval fingerprint')
    packet=packet.resolve(); path=packet/'manifest.json'
    check(sha256(path)==approved_hash,'Source review fingerprint changed')
    m=json.loads(path.read_text())
    check(m['version']=='wands-component-image-review-v1' and set(m['outputs'])=={'reviews.jsonl','review.html'} and
          {p.name for p in packet.iterdir()}=={'manifest.json',*m['outputs']},'Unexpected source review')
    check(m['publication_approved'] is False and m['assembly_ready'] is False,'Source approval state changed')
    pins={**m['inputs'],str(path):approved_hash,**{str(packet/k):v for k,v in m['outputs'].items()}}
    verify_pins(pins)
    layouts=[Path(p).parent for p in pins if Path(p).name=='manifest.json' and
             'component-briefs.proposed.jsonl' in json.loads(Path(p).read_text()).get('outputs',{})]
    check(len(layouts)==1,'Source review must pin exactly one component layout packet')
    selections=[Path(p) for p in pins if Path(p).name=='media_component_pilot_selection.json']
    check(len(selections)==1,'Source review must pin its exact component selection')
    source_cases,source_pins=verify_completed(layouts[0],selections[0],Path(m['run']))
    check(all(pins.get(k)==v for k,v in source_pins.items()),'Source review omitted component provenance')
    rows=read_jsonl(packet/'reviews.jsonl')
    check([r['case'] for r in rows]==source_cases,'Source review cases changed')
    return make_cases(rows),pins


def validate_directory(output,cases):
    check(not output.is_symlink(),'Run directory symlinks are forbidden')
    if not output.exists(): return
    allowed={'run.json','execution-cases.jsonl','events.jsonl','.pilot.lock'} | {
        n for c in cases for n in (c['candidate_filename'],c['candidate_filename']+'.json')}
    check(output.is_dir() and {p.name for p in output.iterdir()}<=allowed and
          all(p.is_file() and not p.is_symlink() for p in output.iterdir()),'Unexpected framing run contents')


def pending(cases,output):
    indexed={c['trial_id']:c for c in cases}; states={}; ledger=output/'events.jsonl'
    check(len(indexed)==len(cases) and not ledger.is_symlink(),'Duplicate trial or ledger symlink')
    if ledger.exists():
        for e in read_jsonl(ledger):
            key=e['trial_id']; status=e['status']
            check(key in indexed,'Unknown framing trial')
            if status=='attempt_started': check(key not in states,'Duplicate framing attempt')
            else: check(status in {'generated','failed'} and states.get(key,{}).get('status')=='attempt_started','Orphan trial result')
            states[key]=e
    todo=[]
    for key,c in indexed.items():
        image=safe_target(output,c['candidate_filename']); meta=output/(image.name+'.json')
        if key not in states:
            check(not image.exists() and not meta.exists(),'Untracked framing candidate; never overwrite')
            todo.append(c); continue
        e=states[key]
        check(e['status']=='generated',key+' already attempted; no automatic retry')
        check(e['filename']==image.name and image.is_file() and meta.is_file(),'Missing framing candidate')
        check(sha256(image)==e['image_sha256'] and sha256(meta)==e['metadata_sha256'],'Framing candidate changed')
        data=json.loads(meta.read_text())
        check(data['case']==c and data['execution_case_sha256']==digest(c) and data['image_sha256']==sha256(image),
              'Framing metadata changed')
    return todo


def generate(cases,output,model,recheck):
    summary={'generated':0,'failed':0}
    for c in cases:
        recheck(); target=safe_target(output,c['candidate_filename']); source=c['source_case']; s=c['settings']
        check(not target.exists() and not (output/(target.name+'.json')).exists(),'Candidate appeared after preflight')
        append_event(output/'events.jsonl',{'trial_id':c['trial_id'],'status':'attempt_started'})
        started=time.monotonic()
        try:
            result=model.generate_image(seed=source['seed'],prompt=source['runtime_prompt'],
                width=s['width'],height=s['height'],num_inference_steps=s['steps'],guidance=s['guidance'])
            check(result.image.size==(s['width'],s['height']),'Unexpected framing dimensions')
            with tempfile.NamedTemporaryFile(dir=output,prefix='.framing-',suffix='.webp') as stream:
                result.image.convert('RGB').save(stream.name,format='WEBP',quality=90,method=6)
                with Image.open(stream.name) as image: image.verify()
                with open(stream.name,'rb') as handle: os.fsync(handle.fileno())
                os.link(stream.name,target)
            meta=output/(target.name+'.json')
            data={'case':c,'execution_case_sha256':digest(c),'image_sha256':sha256(target),
                  'visual_acceptance':'pending','mask_acceptance':'pending','has_alpha':False,
                  'publication_approved':False,'reference_use_approved':False,
                  'required_disclosure':source['brief']['required_disclosure']}
            publish_exclusive(meta,(json.dumps(data,indent=2,sort_keys=True)+'\n').encode())
            seconds=round(time.monotonic()-started,2)
            append_event(output/'events.jsonl',{'trial_id':c['trial_id'],'status':'generated','filename':target.name,
                'image_sha256':sha256(target),'metadata_sha256':sha256(meta),'seconds':seconds})
            logging.info('Generated %s in %.2fs; visual acceptance pending',c['trial_id'],seconds)
            summary['generated']+=1
        except Exception:
            append_event(output/'events.jsonl',{'trial_id':c['trial_id'],'status':'failed'})
            logging.exception('Framing generation failed; stopping without retry'); summary['failed']+=1
            break
    return summary


def run(args):
    cases,pins=verify_source(args.source_review,args.approved_source_sha256)
    _,runtime=prepare_runtime([c['source_case'] for c in cases[::2]])
    source_manifest=json.loads((args.source_review/'manifest.json').read_text())
    original=json.loads((Path(source_manifest['run'])/'run.json').read_text())
    check(runtime==original['runtime'],'Runtime differs from original component pilot')
    for name in ('run_catalog_framing_pilot.py','review_catalog_component_pilot.py','run_catalog_component_pilot.py',
                 'run_catalog_media_pilot.py','generate_images.py'):
        p=Path(__file__).with_name(name).resolve(); pins[str(p)]=sha256(p)
    pins.update(runtime['tokenizer_hashes'])
    output=args.output_dir.resolve()
    check(not args.output_dir.is_symlink() and not any(Path(p).is_relative_to(output) for p in pins), 'Output overlaps source')
    protected={Path(p).parent for p in pins if Path(p).name=='manifest.json' or Path(p).suffix.lower() in {'.jpg','.png','.webp'}}
    check(not any(output.is_relative_to(p) for p in protected),'Output is inside a source packet or media folder')
    descriptor={'version':'wands-framing-pilot-v1','source_review':str(args.source_review.resolve()),
                'source_sha256':args.approved_source_sha256,'inputs':pins,'runtime':runtime,
                'cases_sha256':digest(cases),'max_attempts':4,'publication_approved':False}
    validate_directory(output,cases)
    if output.exists() and any(output.iterdir()):
        check(json.loads((output/'run.json').read_text())==descriptor and read_jsonl(output/'execution-cases.jsonl')==cases,
              'Existing framing run differs; preserve it')
    todo=pending(cases,output)
    logging.info('Framing preflight: %d selected, %d pending; equal area %d pixels',len(cases),len(todo),768**2)
    if not args.run or not todo: return {'selected':4,'pending':len(todo),'generated':0,'failed':0,'dry_run':not args.run}
    output.mkdir(parents=True,exist_ok=True)
    check(not (output/'.pilot.lock').is_symlink(),'Lock symlink is forbidden')
    with (output/'.pilot.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        validate_directory(output,cases)
        if not (output/'run.json').exists():
            publish_exclusive(output/'run.json',(json.dumps(descriptor,indent=2,sort_keys=True)+'\n').encode())
            publish_exclusive(output/'execution-cases.jsonl',''.join(json.dumps(c,sort_keys=True)+'\n' for c in cases).encode())
        check(json.loads((output/'run.json').read_text())==descriptor and read_jsonl(output/'execution-cases.jsonl')==cases,
              'Concurrent framing run differs')
        pins={**pins,**{str(output/n):sha256(output/n) for n in ('run.json','execution-cases.jsonl')}}
        todo=pending(cases,output)
        if not todo: return {'generated':0,'failed':0,'pending':0}
        verify_pins(pins)
        from mflux.models.common.config.model_config import ModelConfig
        from mflux.models.flux2.variants import Flux2Klein
        logging.info('Loading cached FLUX for %d framing attempts',len(todo))
        model=Flux2Klein(model_config=ModelConfig.from_name(SETTINGS['model']),model_path=runtime['model_snapshot'],quantize=4)
        return generate(todo,output,model,lambda:verify_pins(pins))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-review',required=True,type=Path)
    parser.add_argument('--approved-source-sha256',required=True)
    parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--json',action='store_true',help='Opt in to terminal summary')
    args=parser.parse_args(); args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    saved=os.dup(sys.stdout.fileno())
    with args.output_dir.with_name(args.output_dir.name+'.log').open('a',buffering=1) as log:
        os.dup2(log.fileno(),sys.stdout.fileno()); os.dup2(log.fileno(),sys.stderr.fileno())
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
        try:
            result=run(args); logging.info('Framing summary: %s',json.dumps(result,sort_keys=True))
            if args.json: os.write(saved,(json.dumps(result,sort_keys=True)+'\n').encode())
            return int(result.get('failed',0)>0)
        except Exception:
            logging.exception('Framing stopped; no retries or original-image changes'); return 1
        finally: os.close(saved)


if __name__=='__main__':
    raise SystemExit(main())
