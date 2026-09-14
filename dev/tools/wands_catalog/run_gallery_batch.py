"""Run an audited local gallery queue in the background, without installing media."""
import argparse
import fcntl
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from generate_reference_images import run, pending_jobs, require_approved_references
from prepare_catalog import sha256


def write_status(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    os.replace(temporary, path)


def execute(args):
    jobs = [json.loads(line) for line in args.jobs.read_text().splitlines() if line]
    if not 1 <= len(jobs) <= 250:
        raise ValueError('Gallery batches must contain 1 to 250 jobs')
    config = dict(model='flux2-klein-4b', quantize=4, steps=4, width=768, height=768)
    require_approved_references(jobs, args.reference_audit)
    descriptor = {'jobs_sha256': sha256(args.jobs), 'audit_sha256': sha256(args.reference_audit),
                  'runner_sha256': sha256(Path(__file__)), 'config': config,
                  'engine_sha256': sha256(Path(__file__).with_name('generate_reference_images.py'))}
    descriptor_path = args.output_dir / 'run.json'
    if descriptor_path.exists() and json.loads(descriptor_path.read_text()) != descriptor:
        raise ValueError('Run inputs changed; use a fresh output directory')
    write_status(descriptor_path, descriptor)
    pending = pending_jobs(jobs, args.output_dir, config)
    if shutil.disk_usage(args.output_dir).free < 5 * 1024 ** 3:
        raise ValueError('Keep at least 5 GiB free before generation')
    status = dict(pid=os.getpid(), total=len(jobs), pending=len(pending),
                  state='prepared' if args.prepare_only else 'generating', started_at=time.time())
    write_status(args.output_dir / 'status.json', status)
    if args.prepare_only:
        return
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    request = argparse.Namespace(jobs=args.jobs, output_dir=args.output_dir,
        reference_audit=args.reference_audit, steps=4, width=768, height=768,
        sku=None, limit=None, dry_run=False)
    result = run(request)
    write_status(args.output_dir / 'status.json', {**status, **result,
        'state': 'needs_retry' if result['failed'] else 'generated_pending_visual_review',
        'finished_at': time.time(), 'installed': False})
    if result['failed']:
        raise RuntimeError('Generation stopped after a failure; inspect gallery.log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=Path, required=True)
    parser.add_argument('--reference-audit', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--background', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if args.output_dir.is_symlink():
        parser.error('Output directory cannot be a symlink')
    args.output_dir = args.output_dir.resolve()
    args.jobs = args.jobs.resolve()
    args.reference_audit = args.reference_audit.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / 'gallery.log').open('a', buffering=1) as log:
        if args.background:
            command = [sys.executable, str(Path(__file__).resolve()), '--jobs', str(args.jobs),
                       '--reference-audit', str(args.reference_audit), '--output-dir', str(args.output_dir)]
            if args.prepare_only:
                command.append('--prepare-only')
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                     start_new_session=True)
            write_status(args.output_dir / 'launcher.json', {'pid': child.pid, 'command': command})
            return 0
        os.dup2(log.fileno(), sys.stdout.fileno())
        os.dup2(log.fileno(), sys.stderr.fileno())
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
        # One gallery model for this workspace, including jobs in different run directories.
        with (Path(__file__).resolve().parents[3] / 'var/wands/.gallery-gpu.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                logging.error('Another gallery batch owns the GPU lock')
                return 1
            try:
                execute(args)
            except Exception:
                logging.exception('Gallery batch stopped; outputs preserved')
                write_status(args.output_dir / 'failure.json', {'pid': os.getpid(), 'failed_at': time.time()})
                return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
