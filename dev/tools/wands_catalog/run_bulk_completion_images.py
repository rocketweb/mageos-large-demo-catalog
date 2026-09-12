#!/usr/bin/env python3
"""Run the delegated bulk image queue locally, with quiet logs and resumable hashes."""
import argparse
import fcntl
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from build_realism_review import write_json
from catalog_repairs import read_jsonl
from generate_images import append_event
from generate_reference_images import fingerprint, safe_target, completed
from prepare_catalog import sha256
from run_catalog_media_pilot import check_token_budget
from verify_catalog_repairs import check

CONFIG = {'model': 'flux2-klein-4b', 'quantize': 4, 'width': 768, 'height': 768, 'steps': 4}


def pending(jobs, media, events):
    done = completed(events)
    result, seen = [], set()
    for job in jobs:
        target = safe_target(media, job['output_file'])
        check(target.name not in seen, 'Duplicate image destination')
        seen.add(target.name)
        if target.exists():
            record = done.get(target.name, {})
            check(record.get('request_sha256') == fingerprint(job, CONFIG) and record.get('image_sha256') == sha256(target), 'Untracked or changed image; preserve it and use a fresh run')
        else:
            result.append(job)
    return result


def status(root, **values):
    temporary = root/'status.tmp'
    write_json(temporary, {'pid': os.getpid(), 'updated_at': time.time(), **values})
    os.replace(temporary, root/'status.json')


def run(args):
    manifest = json.loads((args.packet/'manifest.json').read_text())
    check(manifest['version'] == 'wands-bulk-completion-v1', 'Wrong bulk packet')
    for name, digest in manifest['outputs'].items():
        check(Path(name).name == name and sha256(args.packet/name) == digest, 'Bulk packet drift')
    jobs = read_jsonl(args.packet/'image-jobs.jsonl')
    reuse = read_jsonl(args.packet/'reused-images.jsonl')
    media = args.run_dir/'media'
    media.mkdir(exist_ok=True)
    events = args.run_dir/'events.jsonl'
    descriptor = {'packet_sha256': sha256(args.packet/'manifest.json'), 'config': CONFIG,
                  'runner_sha256': sha256(Path(__file__)), 'jobs': len(jobs), 'reuse': len(reuse)}
    record_path = args.run_dir/'run.json'
    if record_path.exists():
        check(json.loads(record_path.read_text()) == descriptor, 'Run inputs changed')
    else:
        write_json(record_path, descriptor)
    for job in reuse:
        target = safe_target(media, job['output_file'])
        check(sha256(Path(job['source'])) == job['source_sha256'], 'Reviewed assortment changed')
        if not target.exists():
            shutil.copyfile(job['source'], target)
        check(sha256(target) == job['source_sha256'], 'Reused image differs')
    queue = pending(jobs, media, events)
    status(args.run_dir, state='preflight', total=len(jobs), generated=len(jobs)-len(queue), reused=len(reuse))
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from huggingface_hub import hf_hub_download
    from transformers import Qwen2TokenizerFast
    token_config = Path(hf_hub_download('black-forest-labs/FLUX.2-klein-4B', 'tokenizer/tokenizer_config.json', local_files_only=True))
    tokenizer = Qwen2TokenizerFast.from_pretrained(token_config.parent, local_files_only=True)
    token_counts = [check_token_budget(job['prompt'], tokenizer) for job in jobs]
    logging.info('Queue %d images; %d pending; prompt tokens %d to %d', len(jobs), len(queue), min(token_counts), max(token_counts))
    if args.prepare_only:
        status(args.run_dir, state='prepared', total=len(jobs), pending=len(queue), reused=len(reuse), max_prompt_tokens=max(token_counts))
        return
    if not queue:
        status(args.run_dir, state='generated_pending_batch_review', total=len(jobs), generated=len(jobs), reused=len(reuse))
        return
    from mflux.models.common.config.model_config import ModelConfig
    from mflux.models.flux2.variants import Flux2Klein
    model = Flux2Klein(model_config=ModelConfig.from_name(CONFIG['model']), model_path=str(token_config.parent.parent), quantize=CONFIG['quantize'])
    failed = 0
    generated = len(jobs)-len(queue)
    for job in queue:
        started = time.monotonic()
        status(args.run_dir, state='generating', total=len(jobs), generated=generated, failed=failed, reused=len(reuse), current_sku=job['sku'])
        try:
            result = model.generate_image(seed=job['seed'], prompt=job['prompt'], width=CONFIG['width'], height=CONFIG['height'], guidance=1.0, num_inference_steps=CONFIG['steps'])
            check(result.image.size == (CONFIG['width'], CONFIG['height']), 'Wrong image size')
            target = safe_target(media, job['output_file'])
            with tempfile.NamedTemporaryFile(dir=media, suffix='.jpg') as temp:
                result.image.convert('RGB').save(temp.name, 'JPEG', quality=92, optimize=True)
                with open(temp.name, 'rb') as handle:
                    os.fsync(handle.fileno())
                os.link(temp.name, target)
            append_event(events, {'status': 'generated', 'sku': job['sku'], 'output_file': target.name,
                'request_sha256': fingerprint(job, CONFIG), 'image_sha256': sha256(target),
                'seconds': round(time.monotonic()-started, 2), 'visual_acceptance': 'pending_batch_review'})
            generated += 1
            logging.info('Generated %d/%d: %s in %.1fs', generated, len(jobs), job['sku'], time.monotonic()-started)
        except Exception:
            failed += 1
            append_event(events, {'status': 'failed', 'sku': job['sku'], 'output_file': job['output_file']})
            logging.exception('Image failed; continuing remaining test-catalog jobs')
    status(args.run_dir, state='needs_retry' if failed else 'generated_pending_batch_review', total=len(jobs), generated=generated, failed=failed, reused=len(reuse))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--background', action='store_true')
    args = parser.parse_args()
    args.packet = args.packet.resolve()
    check(not args.run_dir.is_symlink(), 'Run directory cannot be a symlink')
    args.run_dir = args.run_dir.resolve()
    args.run_dir.mkdir(parents=True, exist_ok=True)
    with (args.run_dir/'bulk.log').open('a', buffering=1) as log:
        if args.background:
            command = [sys.executable, str(Path(__file__).resolve()), '--packet', str(args.packet), '--run-dir', str(args.run_dir)]
            if args.prepare_only:
                command.append('--prepare-only')
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            write_json(args.run_dir/'launcher.json', {'pid': child.pid, 'command': command, 'launched_at': time.time()})
            return 0
        os.dup2(log.fileno(), sys.stdout.fileno())
        os.dup2(log.fileno(), sys.stderr.fileno())
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
        with (args.run_dir/'.bulk.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                logging.error('This bulk run is already active')
                return 1
            try:
                run(args)
                return 0
            except Exception:
                logging.exception('Bulk job stopped; consult log and resume the same packet')
                status(args.run_dir, state='failed', log='bulk.log')
                return 1


if __name__ == '__main__':
    raise SystemExit(main())
