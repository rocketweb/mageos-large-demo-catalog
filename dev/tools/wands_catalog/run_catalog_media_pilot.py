#!/usr/bin/env python3
"""Run only an explicitly approved, hash-bound local pilot. Quiet and offline by default."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
from importlib.metadata import version
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
from plan_catalog_media_repairs import SETTINGS, verify_review_packet
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from verify_catalog_repairs import check

VISUAL_FACTS = {'lab_spec_color', 'lab_spec_finish', 'lab_spec_material', 'lab_spec_frame_material',
                'lab_spec_pattern', 'lab_spec_style', 'lab_spec_shape'}


def compile_prompt(case):
    """Keep visual facts in the encoder budget; retain complete provenance in metadata."""
    c = case['acceptance_contract']
    def size(values):
        labels = {'lab_spec_length_cm': 'L', 'lab_spec_width_cm': 'W',
                  'lab_spec_height_cm': 'H', 'lab_spec_depth_cm': 'D'}
        return ' '.join(labels[k] + f'{v:g}cm' for k, v in values.items() if k in labels)
    lines = ['Photorealistic studio catalog product photograph. Neutral seamless background, soft light, full objects in frame.',
             c['product_name'] + '.', 'Selected: ' + ', '.join(c['selected_options'].values()) + '.',
             'Sale unit: ' + c['sale_unit'] + '.', case['pilot_case']['framing']]
    facts = list(dict.fromkeys(str(v['value']) for k, v in c['specifications'].items() if k in VISUAL_FACTS))
    if facts: lines.append('Appearance: ' + ', '.join(facts) + '.')
    if c['components']:
        lines.append('Every component, separately countable: ' + '; '.join(
            f"{p['quantity']} x {p['label']} ({size(p['dimensions_cm'])})" for p in c['components']) + '.')
    else:
        lines.append('Design proportions: ' + size(c['dimensions_cm']) + '.')
    lines.append('No extra products, people, logos, watermarks, lettering or dimension labels. No invented features. '
                 'Use realistic construction and materials. Do not hide included components behind each other.')
    if 'nursery' in c['product_name'].lower():
        lines.append('Separate textile flat lay only. No crib, mattress, infant or sleeping arrangement.')
    return '\n'.join(lines)


def check_token_budget(prompt, tokenizer):
    formatted = tokenizer.apply_chat_template([{'role': 'user', 'content': prompt}], tokenize=False,
                                               add_generation_prompt=True, enable_thinking=False)
    tokens = tokenizer(formatted, truncation=False, add_special_tokens=True)['input_ids']
    check(len(tokens) <= 512, f'Prompt exceeds the runtime 512-token limit: {len(tokens)}; do not silently truncate')
    return len(tokens)


def verify_plan(plan, approved_hash):
    plan = plan.resolve(); manifest = plan/'manifest.json'
    check(re.fullmatch(r'[0-9a-f]{64}', approved_hash or '') and sha256(manifest) == approved_hash,
          'The approved plan fingerprint does not match')
    m = json.loads(manifest.read_text())
    expected = {'plan.md', 'pilot.proposed.jsonl', 'dispositions.proposed.jsonl', 'acceptance.pending.jsonl'}
    check(set(m['outputs']) == expected and {p.name for p in plan.iterdir()} == expected | {'manifest.json'},
          'Unexpected plan outputs')
    check(m['proposed_settings'] == SETTINGS, 'Approved runtime settings changed')
    pins = {**m['inputs'], str(manifest): approved_hash,
            **{str(plan/name): h for name, h in m['outputs'].items()}}
    verify_pins(pins)
    reviews, _ = verify_review_packet(Path(m['review_packet']))
    contracts = {r['contract']['root_sku']: r['contract'] for r in reviews}
    all_rows = read_jsonl(plan/'dispositions.proposed.jsonl'); pilot = read_jsonl(plan/'pilot.proposed.jsonl')
    check(pilot == [r for r in all_rows if r['pilot_case']], 'Pilot differs from planned selection')
    check(0 < len(pilot) <= 12 and len({r['root_sku'] for r in pilot}) == len(pilot), 'Invalid pilot size or duplicate roots')
    check(len(pilot) == m['counts']['pilot_images_proposed'], 'Pilot count differs from approval')
    for case in pilot:
        check(case['acceptance_contract'] == contracts[case['root_sku']], 'Pilot contract changed')
        check(case['definition_sha256'] == digest(case['acceptance_contract']), 'Pilot definition hash changed')
        check(case['proposed_action'] in {'clarify_hero', 'repair_confirmed_defect'}, 'Retained candidate entered pilot')
        check(case['executable'] is False and case['reference_use_approved'] is False, 'Unexpected proposal state')
    return pilot, pins


def verify_pins(pins):
    for path, expected in pins.items():
        check(sha256(Path(path)) == expected, 'Pinned input changed: ' + path)


def safe_target(output, name):
    check(Path(name).name == name and name.endswith('.webp'), 'Unsafe candidate filename')
    path = output/name
    check(not path.is_symlink() and not (output/(name+'.json')).is_symlink(), 'Output symlinks are forbidden')
    return path


def pending_cases(cases, output):
    indexed = {c['root_sku']: c for c in cases}; states = {}; events = output/'events.jsonl'
    check(len(indexed) == len(cases), 'Duplicate execution case')
    if events.exists():
        for line in events.read_text().splitlines():
            event = json.loads(line); sku = event['root_sku']; status = event['status']
            check(sku in indexed, 'Unknown attempted root')
            if status == 'attempt_started':
                check(sku not in states, 'Duplicate attempt')
                states[sku] = event
            else:
                check(status in {'generated', 'failed'} and states.get(sku, {}).get('status') == 'attempt_started',
                      'Invalid attempt history')
                states[sku] = event
    pending = []
    for sku, c in indexed.items():
        target = safe_target(output, c['candidate_filename']); meta = output/(target.name+'.json')
        state = states.get(sku)
        if state:
            check(state['status'] == 'generated', sku + ' was already attempted; no automatic retry is allowed')
            check(state['filename'] == target.name and target.is_file() and meta.is_file(), 'Completed candidate missing')
            check(sha256(target) == state['image_sha256'] and sha256(meta) == state['metadata_sha256'], 'Completed candidate changed')
            data = json.loads(meta.read_text())
            check(data['runtime_prompt_sha256'] == c['runtime_prompt_sha256'] and
                  data['definition_sha256'] == c['definition_sha256'], 'Stale completed candidate')
        else:
            check(not target.exists() and not meta.exists(), 'Untracked output exists; never overwrite it')
            pending.append(c)
    return pending


def publish_exclusive(path, content):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.pilot-', suffix='.tmp') as stream:
        stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.link(stream.name, path)


def generate_cases(cases, output, model, recheck):
    summary = {'generated': 0, 'failed': 0}
    for c in cases:
        recheck()
        target = safe_target(output, c['candidate_filename'])
        check(not target.exists() and not (output/(target.name+'.json')).exists(), 'Candidate appeared after preflight')
        append_event(output/'events.jsonl', {'status': 'attempt_started', 'root_sku': c['root_sku']})
        started = time.monotonic()
        try:
            result = model.generate_image(seed=c['proposed_seed'], prompt=c['runtime_prompt'],
                                          width=SETTINGS['width'], height=SETTINGS['height'],
                                          guidance=1.0, num_inference_steps=SETTINGS['steps'])
            check(result.image.size == (SETTINGS['width'], SETTINGS['height']), 'Unexpected generated dimensions')
            with tempfile.NamedTemporaryFile(dir=output, prefix='.candidate-', suffix='.webp') as stream:
                result.image.convert('RGB').save(stream.name, format='WEBP', quality=90, method=6)
                with Image.open(stream.name) as im: im.verify()
                with open(stream.name, 'rb') as handle: os.fsync(handle.fileno())
                os.link(stream.name, target)
            metadata = {'root_sku': c['root_sku'], 'selected_sku': c['selected_sku'],
                        'definition_sha256': c['definition_sha256'], 'image_sha256': sha256(target),
                        'runtime_prompt_sha256': c['runtime_prompt_sha256'], 'runtime_prompt': c['runtime_prompt'],
                        'required_disclosure': c['acceptance_contract']['required_disclosure'],
                        'acceptance_contract': c['acceptance_contract'], 'settings': SETTINGS,
                        'seed': c['proposed_seed'], 'visual_acceptance': 'pending'}
            meta = output/(target.name+'.json')
            publish_exclusive(meta, (json.dumps(metadata, indent=2, sort_keys=True)+'\n').encode())
            seconds = round(time.monotonic()-started, 2)
            append_event(output/'events.jsonl', {'status': 'generated', 'root_sku': c['root_sku'],
                         'filename': target.name, 'image_sha256': sha256(target), 'metadata_sha256': sha256(meta),
                         'seconds': seconds, 'visual_acceptance': 'pending'})
            summary['generated'] += 1
            logging.info('Generated %s in %.2fs; visual acceptance pending', c['root_sku'], seconds)
        except Exception:
            append_event(output/'events.jsonl', {'status': 'failed', 'root_sku': c['root_sku']})
            summary['failed'] += 1
            logging.exception('Pilot generation failed; stopping without retry')
            break
    return summary


def prepare_runtime(cases):
    os.environ['HF_HUB_OFFLINE'] = '1'; os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from huggingface_hub import hf_hub_download
    from transformers import Qwen2TokenizerFast
    token_config = Path(hf_hub_download('black-forest-labs/FLUX.2-klein-4B', 'tokenizer/tokenizer_config.json', local_files_only=True))
    snapshot = token_config.parent.parent
    tokenizer = Qwen2TokenizerFast.from_pretrained(token_config.parent, local_files_only=True)
    runtime = {'packages': {p: version(p) for p in ('mflux', 'mlx', 'Pillow', 'transformers', 'huggingface-hub')},
               'model_snapshot': str(snapshot), 'tokenizer_hashes': {str(p): sha256(p) for p in sorted(token_config.parent.iterdir()) if p.is_file()}}
    compiled = []
    for case in cases:
        prompt = compile_prompt(case); tokens = check_token_budget(prompt, tokenizer)
        token = digest({'plan_case': case, 'runtime_prompt': prompt, 'settings': SETTINGS})[:16]
        compiled.append({**case, 'runtime_prompt': prompt, 'runtime_prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                         'token_count': tokens, 'candidate_filename': case['root_sku']+'-hero-'+token+'.webp'})
    return compiled, runtime


def run(args):
    cases, pins = verify_plan(args.plan, args.approved_plan_sha256)
    output = args.output_dir.resolve()
    check(not args.output_dir.is_symlink(), 'Output directory symlink is forbidden')
    check(not any(Path(p).is_relative_to(output) for p in pins), 'Output cannot contain a pinned source')
    check(not output.is_relative_to(args.plan.resolve()), 'Output cannot be inside the immutable plan')
    check(not any(output.is_relative_to(Path(c['original_reference_evidence']['path']).parent) for c in cases),
          'Output cannot be in the original media directory')
    compiled, runtime = prepare_runtime(cases)
    pins.update(runtime['tokenizer_hashes'])
    pins[str(Path(__file__).resolve())] = sha256(Path(__file__))
    descriptor = {'approved_plan_sha256': args.approved_plan_sha256, 'runner_sha256': sha256(Path(__file__)),
                  'settings': SETTINGS, 'runtime': runtime, 'cases_sha256': digest(compiled), 'max_attempts': len(compiled)}
    if output.exists() and any(output.iterdir()):
        check((output/'run.json').is_file() and not (output/'run.json').is_symlink(), 'Existing untracked run directory')
        check(json.loads((output/'run.json').read_text()) == descriptor, 'Run descriptor changed; do not resume')
        allowed = {'run.json', '.pilot.lock', 'events.jsonl', 'execution-cases.jsonl'} | {
            name for c in compiled for name in (c['candidate_filename'],c['candidate_filename']+'.json')}
        check({p.name for p in output.iterdir()} <= allowed, 'Unexpected run contents')
        check((output/'execution-cases.jsonl').read_text() == ''.join(json.dumps(c, sort_keys=True)+'\n' for c in compiled),
              'Execution cases changed')
    pending = pending_cases(compiled, output)
    logging.info('Pilot preflight: %s selected, %s pending; token range %s-%s of 512', len(compiled), len(pending),
                 min(c['token_count'] for c in compiled), max(c['token_count'] for c in compiled))
    if not args.run or not pending:
        return {'selected': len(compiled), 'pending': len(pending), 'generated': 0, 'failed': 0, 'dry_run': not args.run}
    output.mkdir(parents=True, exist_ok=True)
    check(not (output/'.pilot.lock').is_symlink() and not (output/'events.jsonl').is_symlink(), 'Run-state symlink is forbidden')
    with (output/'.pilot.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not (output/'run.json').exists():
            publish_exclusive(output/'run.json', (json.dumps(descriptor, indent=2, sort_keys=True)+'\n').encode())
            publish_exclusive(output/'execution-cases.jsonl', ''.join(json.dumps(c, sort_keys=True)+'\n' for c in compiled).encode())
        check(json.loads((output/'run.json').read_text()) == descriptor, 'Concurrent run descriptor differs')
        pins[str(output/'run.json')] = sha256(output/'run.json')
        pins[str(output/'execution-cases.jsonl')] = sha256(output/'execution-cases.jsonl')
        pending = pending_cases(compiled, output)
        from mflux.models.common.config.model_config import ModelConfig
        from mflux.models.flux2.variants import Flux2Klein
        logging.info('Loading cached local FLUX model; hosted services disabled')
        model = Flux2Klein(model_config=ModelConfig.from_name(SETTINGS['model']), model_path=runtime['model_snapshot'], quantize=SETTINGS['quantize'])
        return generate_cases(pending, output, model, lambda: verify_pins(pins))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--approved-plan-sha256', required=True)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--run', action='store_true', help='Generate the approved pilot; without this flag perform CPU-only preflight')
    parser.add_argument('--json', action='store_true', help='Opt in to a terminal summary')
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    saved_stdout = os.dup(sys.stdout.fileno())
    with args.output_dir.with_name(args.output_dir.name+'.log').open('a', buffering=1) as log:
        os.dup2(log.fileno(), sys.stdout.fileno()); os.dup2(log.fileno(), sys.stderr.fileno())
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
        try:
            summary = run(args)
            logging.info('Pilot summary: %s', json.dumps(summary, sort_keys=True))
            if args.json: os.write(saved_stdout, (json.dumps(summary, sort_keys=True)+'\n').encode())
            return int(summary.get('failed', 0) > 0)
        except Exception:
            logging.exception('Pilot stopped; no automatic retry or original-media replacement')
            return 1
        finally:
            os.close(saved_stdout)


if __name__ == '__main__': raise SystemExit(main())
