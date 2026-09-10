#!/usr/bin/env python3
"""Run at most four hash-bound local component attempts. Quiet, offline, no retries or compositing."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
from importlib.metadata import version
import json
import logging
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from PIL import Image
from catalog_repairs import read_jsonl
from generate_images import append_event
from plan_catalog_component_layouts import read_review, validate_layout
from plan_catalog_media_repairs import SETTINGS
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from run_catalog_media_pilot import VISUAL_FACTS, check_token_budget, publish_exclusive, safe_target, verify_pins
from verify_catalog_repairs import check

MAX_ASSETS = 4


def compile_prompt(brief, choice):
    part = brief['component']; d = part['dimensions_cm']
    width = d.get('lab_spec_width_cm')
    height = d.get('lab_spec_height_cm') if brief['view'] == 'front elevation' else d.get('lab_spec_length_cm', d.get('lab_spec_depth_cm'))
    check(all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in (width, height)), 'Invalid component proportions')
    appearance = list(dict.fromkeys(str(v['value']) for k, v in brief['parent_specifications'].items() if k in VISUAL_FACTS))
    appearance += [str(v) for k, v in brief['selected_options'].items() if k in {'color', 'wands_color', 'wands_finish', 'wands_material'} and str(v) not in appearance]
    lines = ['Photorealistic studio catalog photograph on a uniform white background. Soft upper-left light, minimal faint shadow.',
             'Subject: exactly ONE complete ' + part['label'] + ', by itself.',
             choice['visual_instruction'],
             'View: ' + brief['view'] + '. Center the entire object, upright in the image, with clear margins on every side.']
    if appearance:
        lines.append('Appearance: ' + ', '.join(appearance) + '.')
    lines += [f'Proportions: visible overall height about {height/width:.2f} times maximum width.',
              'No extra objects, labels, letters, numbers, arrows, dimension graphics, logos, watermarks or people. '
              'No split views, collages, detached pieces or cropped edges. This is one finished object, not a diagram.']
    return '\n'.join(lines)


def select_cases(briefs, choices):
    check(isinstance(choices, list) and 0 < len(choices) <= MAX_ASSETS, 'Select one to four exact component assets')
    indexed = {b['asset_requirement_id']: b for b in briefs}
    check(len(indexed) == len(briefs), 'Duplicate component requirement')
    ids = [c['asset_requirement_id'] for c in choices]
    check(len(set(ids)) == len(ids) and set(ids) <= set(indexed), 'Unknown or duplicate selected asset')
    cases = []
    for choice in choices:
        check(type(choice['max_attempts']) is int and choice['max_attempts'] == 1, 'Only one attempt per component is allowed')
        check(all(isinstance(choice[k], str) and choice[k].strip() for k in ('visual_instruction', 'purpose')), 'Incomplete component selection')
        b = indexed[choice['asset_requirement_id']]
        prompt = compile_prompt(b, choice)
        cases.append({'asset_requirement_id': b['asset_requirement_id'], 'root_sku': b['root_sku'],
                      'component_id': b['component_id'], 'brief': b, 'brief_sha256': digest(b), 'selection': choice,
                      'runtime_prompt': prompt, 'runtime_prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                      'seed': int(digest({'brief': b, 'choice': choice})[:8], 16)})
    return cases


def verify_layouts(packet):
    packet = packet.resolve(); manifest = packet/'manifest.json'; m = json.loads(manifest.read_text())
    outputs = {'layouts.proposed.jsonl', 'component-briefs.proposed.jsonl', 'coverage.jsonl', 'review.html'}
    check(set(m['outputs']) == outputs and {p.name for p in packet.iterdir()} == outputs | {'manifest.json'}, 'Unexpected layout packet')
    check(all(m[k] is False for k in ('executable', 'generation_approved', 'publication_approved')), 'Layout proposal state changed')
    pins = {**m['inputs'], str(manifest): sha256(manifest), **{str(packet/k):v for k,v in m['outputs'].items()}}
    verify_pins(pins)
    reviews, review_pins = read_review(Path(m['source_review']))
    check(all(pins.get(k) == v for k,v in review_pins.items()), 'Layout omitted source review pins')
    contracts = {r['root_sku']:r['contract'] for r in reviews}
    layouts = read_jsonl(packet/'layouts.proposed.jsonl'); indexed = {l['root_sku']:l for l in layouts}
    check(len(indexed) == len(layouts) == m['counts']['layouts'], 'Layout scope changed')
    for layout in layouts:
        validate_layout(layout, contracts[layout['root_sku']])
    briefs = read_jsonl(packet/'component-briefs.proposed.jsonl')
    expected_keys = {(sku,p['component_id']) for sku in indexed for p in contracts[sku]['components']}
    check(len(briefs) == len(expected_keys) == m['counts']['component_types'] and
          {(b['root_sku'],b['component_id']) for b in briefs} == expected_keys, 'Component brief scope changed')
    for b in briefs:
        c = contracts[b['root_sku']]; layout = indexed[b['root_sku']]
        part = next(p for p in c['components'] if p['component_id'] == b['component_id'])
        check(b['component'] == part and b['definition_sha256'] == digest(c) and b['layout_sha256'] == digest(layout),
              'Component brief differs from corrected definition or layout')
        expected_id = b['root_sku'] + '-' + b['component_id'] + '-' + digest({'definition':digest(c),'component':part,'profile':layout['profile']})[:12]
        check(b['asset_requirement_id'] == expected_id and b['required_instances'] == part['quantity'] and
              b['instance_ids'] == [s['instance_id'] for s in layout['instances'] if s['component_id'] == b['component_id']],
              'Component instance binding changed')
        check(b['selected_options'] == c['selected_options'] and b['parent_specifications'] == c['specifications'] and
              b['parent_constraints'] == c['constraints'] and b['required_disclosure'] == c['required_disclosure'],
              'Component context changed')
        check(b['view'] == ('front elevation' if layout['profile'] == 'shared_floor' else 'orthographic top view') and
              b['acceptance'] == 'pending' and b['executable'] is False and b['reference_use_approved'] is False,
              'Component viewpoint or approval state changed')
    return briefs, pins


def pending_assets(cases, output):
    indexed = {c['asset_requirement_id']:c for c in cases}
    check(len(indexed) == len(cases), 'Duplicate runtime component')
    states = {}; ledger = output/'events.jsonl'
    check(not ledger.is_symlink(), 'Attempt ledger symlink is forbidden')
    if ledger.exists():
        for e in read_jsonl(ledger):
            key = e['asset_requirement_id']; status = e['status']
            check(key in indexed, 'Unknown component attempt')
            if status == 'attempt_started':
                check(key not in states, 'Duplicate component attempt')
            else:
                check(status in {'generated', 'failed'} and states.get(key,{}).get('status') == 'attempt_started', 'Orphan or invalid component result')
            states[key] = e
    pending = []
    for key,c in indexed.items():
        target = safe_target(output,c['candidate_filename']); meta = output/(target.name+'.json')
        if key not in states:
            check(not target.exists() and not meta.exists(), 'Untracked component output exists; never overwrite')
            pending.append(c); continue
        state = states[key]
        check(state['status'] == 'generated', key + ' already attempted; automatic retries are forbidden')
        check(state['filename'] == target.name and target.is_file() and meta.is_file(), 'Completed component is missing')
        check(sha256(target) == state['image_sha256'] and sha256(meta) == state['metadata_sha256'], 'Completed component bytes changed')
        data = json.loads(meta.read_text())
        check(data['execution_case_sha256'] == digest(c) and data['case'] == c and data['image_sha256'] == sha256(target),
              'Completed component metadata changed')
    return pending


def generate_assets(cases, output, model, recheck):
    summary = {'generated':0, 'failed':0}
    for c in cases:
        recheck(); key = c['asset_requirement_id']; target = safe_target(output,c['candidate_filename'])
        check(not target.exists() and not (output/(target.name+'.json')).exists(), 'Component appeared after preflight')
        append_event(output/'events.jsonl', {'asset_requirement_id':key, 'status':'attempt_started'})
        started = time.monotonic()
        try:
            result = model.generate_image(seed=c['seed'],prompt=c['runtime_prompt'],width=768,height=768,guidance=1.0,num_inference_steps=4)
            check(result.image.size == (768,768), 'Unexpected generated component dimensions')
            with tempfile.NamedTemporaryFile(dir=output,prefix='.component-',suffix='.webp') as stream:
                result.image.convert('RGB').save(stream.name,format='WEBP',quality=90,method=6)
                with Image.open(stream.name) as im: im.verify()
                with open(stream.name,'rb') as handle: os.fsync(handle.fileno())
                os.link(stream.name,target)
            metadata = {'asset_requirement_id':key,'root_sku':c['root_sku'],'component_id':c['component_id'],
                        'execution_case_sha256':digest(c),'case':c,'image_sha256':sha256(target),
                        'settings':SETTINGS,'visual_acceptance':'pending','mask_acceptance':'pending',
                        'has_alpha':False,'publication_approved':False,'reference_use_approved':False,
                        'required_disclosure':c['brief']['required_disclosure']}
            meta = output/(target.name+'.json')
            publish_exclusive(meta,(json.dumps(metadata,indent=2,sort_keys=True)+'\n').encode())
            seconds = round(time.monotonic()-started,2)
            append_event(output/'events.jsonl',{'asset_requirement_id':key,'status':'generated','filename':target.name,
                         'image_sha256':sha256(target),'metadata_sha256':sha256(meta),'seconds':seconds})
            summary['generated'] += 1
            logging.info('Generated component %s in %.2fs; visual and mask acceptance pending',key,seconds)
        except Exception:
            append_event(output/'events.jsonl',{'asset_requirement_id':key,'status':'failed'})
            summary['failed'] += 1
            logging.exception('Component generation stopped without retry')
            break
    return summary


def prepare_runtime(cases):
    os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'
    from huggingface_hub import hf_hub_download
    from transformers import Qwen2TokenizerFast
    config = Path(hf_hub_download('black-forest-labs/FLUX.2-klein-4B','tokenizer/tokenizer_config.json',local_files_only=True))
    tokenizer = Qwen2TokenizerFast.from_pretrained(config.parent,local_files_only=True)
    runtime = {'model_snapshot':str(config.parent.parent),
               'packages':{p:version(p) for p in ('mflux','mlx','Pillow','transformers','huggingface-hub')},
               'tokenizer_hashes':{str(p):sha256(p) for p in sorted(config.parent.iterdir()) if p.is_file()}}
    compiled = [{**c,'token_count':check_token_budget(c['runtime_prompt'],tokenizer),
                 'candidate_filename':c['asset_requirement_id']+'-'+digest({'case':c,'settings':SETTINGS})[:12]+'.webp'} for c in cases]
    return compiled, runtime


def run(args):
    raw = args.selection.read_bytes()
    check(re.fullmatch(r'[0-9a-f]{64}',args.approved_selection_sha256 or '') and
          hashlib.sha256(raw).hexdigest() == args.approved_selection_sha256, 'Selection approval fingerprint differs')
    briefs,pins = verify_layouts(args.layouts)
    pins[str(args.selection.resolve())] = args.approved_selection_sha256
    pins[str(Path(__file__).resolve())] = sha256(Path(__file__))
    cases,runtime = prepare_runtime(select_cases(briefs,json.loads(raw)))
    pins.update(runtime['tokenizer_hashes'])
    output = args.output_dir.resolve()
    check(not args.output_dir.is_symlink() and not any(Path(p).is_relative_to(output) for p in pins),
          'Run output cannot contain a pinned source or be a symlink')
    protected = {Path(p).parent for p in pins if Path(p).name == 'manifest.json' or Path(p).suffix.lower() in {'.jpg','.png','.webp'}}
    check(not any(output.is_relative_to(p) for p in protected), 'Run output cannot be inside source packets or media')
    descriptor = {'layout_manifest_sha256':sha256(args.layouts/'manifest.json'),'selection_sha256':args.approved_selection_sha256,
                  'runner_sha256':sha256(Path(__file__)),'runtime':runtime,'settings':SETTINGS,'max_attempts':len(cases),
                  'cases_sha256':digest(cases)}
    if output.exists() and any(output.iterdir()):
        allowed = {'run.json','execution-cases.jsonl','events.jsonl','.pilot.lock'} | {
            n for c in cases for n in (c['candidate_filename'],c['candidate_filename']+'.json')}
        check({p.name for p in output.iterdir()} <= allowed and all(not p.is_symlink() for p in output.iterdir()), 'Unexpected run contents')
        check(json.loads((output/'run.json').read_text()) == descriptor and read_jsonl(output/'execution-cases.jsonl') == cases,
              'Run descriptor or execution cases changed')
    pending = pending_assets(cases,output)
    logging.info('Component preflight: %d selected, %d pending; tokens %d-%d of 512',len(cases),len(pending),
                 min(c['token_count'] for c in cases),max(c['token_count'] for c in cases))
    if not args.run or not pending:
        return {'selected':len(cases),'pending':len(pending),'generated':0,'failed':0,'dry_run':not args.run}
    output.mkdir(parents=True,exist_ok=True)
    check(not (output/'.pilot.lock').is_symlink(), 'Run lock symlink is forbidden')
    with (output/'.pilot.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not (output/'run.json').exists():
            publish_exclusive(output/'run.json',(json.dumps(descriptor,indent=2,sort_keys=True)+'\n').encode())
            publish_exclusive(output/'execution-cases.jsonl',''.join(json.dumps(c,sort_keys=True)+'\n' for c in cases).encode())
        check(json.loads((output/'run.json').read_text()) == descriptor and read_jsonl(output/'execution-cases.jsonl') == cases,
              'Concurrent component run differs')
        pins[str(output/'run.json')] = sha256(output/'run.json')
        pins[str(output/'execution-cases.jsonl')] = sha256(output/'execution-cases.jsonl')
        pending = pending_assets(cases,output)
        if not pending: return {'generated':0,'failed':0,'pending':0}
        verify_pins(pins)
        from mflux.models.common.config.model_config import ModelConfig
        from mflux.models.flux2.variants import Flux2Klein
        logging.info('Loading cached local FLUX model for at most %d component attempts',len(pending))
        model = Flux2Klein(model_config=ModelConfig.from_name(SETTINGS['model']),model_path=runtime['model_snapshot'],quantize=4)
        return generate_assets(pending,output,model,lambda:verify_pins(pins))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layouts',required=True,type=Path)
    parser.add_argument('--selection',required=True,type=Path)
    parser.add_argument('--approved-selection-sha256',required=True)
    parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--run',action='store_true',help='Generate the exact local pilot; default is CPU-only preflight')
    parser.add_argument('--json',action='store_true',help='Opt in to terminal summary')
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    saved_stdout = os.dup(sys.stdout.fileno())
    with args.output_dir.with_name(args.output_dir.name+'.log').open('a',buffering=1) as log:
        os.dup2(log.fileno(),sys.stdout.fileno()); os.dup2(log.fileno(),sys.stderr.fileno())
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
        try:
            result = run(args)
            logging.info('Component pilot summary: %s',json.dumps(result,sort_keys=True))
            if args.json: os.write(saved_stdout,(json.dumps(result,sort_keys=True)+'\n').encode())
            return int(result.get('failed',0)>0)
        except Exception:
            logging.exception('Component pilot stopped; no retry, compositing or original replacement')
            return 1
        finally:
            os.close(saved_stdout)


if __name__=='__main__':
    raise SystemExit(main())
