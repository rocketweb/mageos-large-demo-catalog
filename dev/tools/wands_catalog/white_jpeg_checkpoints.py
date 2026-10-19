"""Refresh private, verified launch snapshots while background reviews continue."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def safety(database, completed=False, total=95401, rooms=50):
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        count = db.execute('SELECT count(*) FROM images').fetchone()[0]
        held = db.execute("SELECT count(*) FROM images i JOIN glass_outline_checks g USING(file) "
                          "WHERE g.verdict!='preserved' AND i.decision='white'").fetchone()[0]
        room_count = db.execute("SELECT count(*) FROM images WHERE reason='room_bundle_preserve_scene' "
                                "AND decision='original'").fetchone()[0]
        pending = db.execute('SELECT count(*) FROM images WHERE decision IS NULL').fetchone()[0]
    if count != total or held or room_count != rooms or (completed and pending):
        raise ValueError('Snapshot must preserve Room Bundles and all unresolved glass outlines')
    return {'images': count, 'held_glass_selected_white': held,
            'room_bundle_originals': room_count, 'pending': pending}


def maybe_checkpoint(job, audit, here, catalog, now=None):
    now = time.time() if now is None else now
    with (here / 'checkpoint-schedule.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'scheduler_busy'
        state = read(audit / 'export-status.json')
        if state.get('state') == 'needs_attention':
            return 'needs_attention'
        receipt = read(here / 'checkpoint-process.json')
        if alive(receipt.get('pid')) or (state.get('state') == 'building' and alive(state.get('pid'))):
            return 'building'
        # All exporters share this lock, including completion and deadline exports.
        with (audit / 'export.lock').open('a') as export_lock:
            try:
                fcntl.flock(export_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 'building'
        latest = read(audit / 'latest.json')
        unfinished = receipt.get('slot') and not (audit / 'selections' / receipt['slot'] / 'verification.json').exists()
        if not unfinished:
            if now - latest.get('verified_at', 0) < 3600:
                return 'current'
            snapshot = read(Path(latest['verification']).parent / 'snapshot.json') if latest else {}
            with sqlite3.connect((audit / 'audit.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
                changed = max(db.execute('SELECT max(decided_at) FROM category_evidence').fetchone()[0] or 0,
                              db.execute('SELECT max(updated_at) FROM glass_outline_checks').fetchone()[0] or 0)
            if changed <= snapshot.get('created_at', 0):
                return 'unchanged'
        if shutil.disk_usage(audit).free < 15 * 1024**3:
            catalog.write(here / 'checkpoint-status.json', {'state': 'needs_attention',
                          'error': 'Less than 15 GiB free; retaining the last verified export.', 'updated_at': now})
            return 'needs_attention'
        slot = receipt['slot'] if unfinished else 'overnight-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(now))
        config = read(audit / 'config.json')
        command = ['/usr/bin/caffeinate', '-i', config['python'], '-B', str(here / 'checkpoints.py'),
                   'run', '--job', str(job), '--audit', str(audit), '--glass', str(here), '--slot', slot]
        with (here / 'checkpoint.log').open('a') as log:
            process = subprocess.Popen(command, cwd=job, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       start_new_session=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1',
                                       'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'})
        catalog.write(here / 'checkpoint-process.json', {'pid': process.pid, 'slot': slot, 'started_at': now})
        catalog.write(here / 'checkpoint-status.json', {'state': 'building', 'slot': slot,
                                                      'pid': process.pid, 'updated_at': now})
        return 'started'


def run_checkpoint(job, audit, here, slot, catalog):
    previous = read(audit / 'latest.json')
    try:
        safety(audit / 'audit.sqlite3')
        report = catalog.export_selection(job, audit, slot)
        proof = safety(audit / 'selections' / slot / 'audit.sqlite3', completed=True)
        catalog.write(audit / 'selections' / slot / 'overnight-safety.json', proof)
        catalog.write(here / 'checkpoint-status.json', {'state': 'verified', 'slot': slot,
                      'updated_at': time.time(), 'counts': report['counts'], 'safety': proof})
    except BaseException as error:
        # An unsuccessful checkpoint never replaces the previous usable selection.
        with (audit / 'export.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if previous and read(audit / 'latest.json').get('slot') == slot:
                catalog.write(audit / 'latest.json', previous)
            failure = {'state': 'needs_attention', 'slot': slot, 'error': str(error), 'updated_at': time.time()}
            catalog.write(audit / 'export-status.json', failure)
            catalog.write(here / 'checkpoint-status.json', failure)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run'])
    for name in ['job', 'audit', 'glass']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--slot', required=True)
    args = parser.parse_args()
    if not args.audit.is_relative_to(args.job) or not args.glass.is_relative_to(args.audit):
        parser.error('Checkpoint paths must stay within the existing job')
    if not args.slot.startswith('overnight-') or Path(args.slot).name != args.slot:
        parser.error('Invalid private snapshot slot')
    sys.path.insert(0, str(args.audit / 'runtime-code'))
    import white_jpeg_category_run as catalog
    run_checkpoint(args.job, args.audit, args.glass, args.slot, catalog)
