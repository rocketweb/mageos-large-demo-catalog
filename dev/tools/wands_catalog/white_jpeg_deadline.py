#!/usr/bin/env python3
"""Build complete launch selections on a deadline without changing the full audit.

Only qualified, hash-bound positive pair reviews can select a processed image.
Unresolved images retain their originals in a separate snapshot database.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime
import fcntl
from html import escape
import json
import io
import os
from pathlib import Path
import sqlite3
import re
import subprocess
import sys
import time
from zoneinfo import ZoneInfo


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    os.replace(temporary, path)


def prepare_decisions(db, checks):
    """Validate positive evidence, then retain originals for unfinished reviews."""
    counts = {'reviewed_white': 0, 'resolved_original': 0, 'unfinished_original': 0}
    records = db.execute('SELECT row_json,decision FROM images ORDER BY n').fetchall()
    for encoded, decision in records:
        row = json.loads(encoded)
        if decision == 'white':
            feature = db.execute('SELECT features FROM calibrated_features WHERE file=?', (row['file'],)).fetchone()
            review = db.execute("SELECT identity,source_sha256,output_sha256,review,details FROM calibrated_reviews WHERE file=? AND kind='pair'", (row['file'],)).fetchone()
            if not feature or not review:
                raise ValueError('Selected white image lacks individual evidence: ' + row['file'])
            identity, source_hash, output_hash, encoded_review, encoded_details = review
            details = json.loads(encoded_details)
            if (identity != checks.decision_identity() or source_hash != row['source_sha256'] or
                    output_hash != row.get('output_sha256') or details.get('model') != checks.MODEL or
                    details.get('review_identity') != checks.review_identity(checks.MODEL)):
                raise ValueError('Selected white image evidence changed: ' + row['file'])
            parsed = checks.parse(encoded_review)
            approved, _ = checks.choose(row, json.loads(feature[0]), parsed, details.get('focus'))
            if approved != 'white':
                raise ValueError('Selected white image no longer passes: ' + row['file'])
            counts['reviewed_white'] += 1
        elif decision == 'original':
            counts['resolved_original'] += 1
        elif decision is None or decision in {'pending', 'eligible'}:
            counts['unfinished_original'] += 1
        else:
            raise ValueError('Unexpected audit decision: ' + str(decision))
    with db:
        db.execute("UPDATE images SET decision='original',reason='launch_deadline_unfinished_review_keep_original' WHERE decision IS NULL OR decision IN ('pending','eligible')")
    return counts


def snapshot(job, audit, config, slot):
    root = audit / 'launch-delivery'
    destination = root / slot
    destination.mkdir(exist_ok=True)
    sys.path.insert(0, str(audit / 'runtime-code'))
    import white_jpeg_calibrated_run as controller
    import white_jpeg_audit_run as exporter
    from white_jpeg_worker import sha256

    controller.verify_runtime(audit)
    controller.validate_pilot(audit)
    receipt = destination / 'snapshot.json'
    if not receipt.exists():
        target = destination / 'audit.sqlite3'
        with sqlite3.connect((audit / 'audit.sqlite3').as_uri() + '?mode=ro', uri=True) as source:
            with sqlite3.connect(target) as db:
                source.backup(db)
                total = db.execute('SELECT count(*) FROM images').fetchone()[0]
                if total != 95401:
                    raise ValueError('Expected the complete 95,401-image catalog')
                counts = prepare_decisions(db, controller.checks)
                db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        identity = {'kind': 'deadline_launch_selection', 'created_at': time.time(), 'slot': slot,
                    'source_audit': str(audit), 'checks_identity': controller.checks.decision_identity(),
                    'pilot_validation_sha256': sha256(audit / 'pilot-validation.json'),
                    'deadline_at': config['deadline_at'], 'counts_at_snapshot': counts,
                    'database_sha256': sha256(target), 'unresolved_action': 'keep_original',
                    'source_modified': False, 'catalog_imported': False, 'published': False}
        write_json(destination / 'identity.json', identity)
        write_json(receipt, identity)
    identity = json.loads(receipt.read_text())
    if identity['checks_identity'] != controller.checks.decision_identity():
        raise ValueError('Snapshot checks changed')
    expected_csv = json.loads((audit / 'source-integrity.json').read_text())['original_media_csv_sha256']
    report = exporter.select(job, destination,
        review_method='Qualified individual pair reviews for processed JPGs; originals for all unfinished reviews.',
        expected_original_csv_sha256=expected_csv,
        progress_callback=lambda done: write_json(root / 'status.json', {
            'state': 'building', 'slot': slot, 'done': done, 'total': 95401,
            'updated_at': time.time(), 'pid': os.getpid()}))
    counts = identity['counts_at_snapshot']
    # The exporter verifies every original and selected hash. Hash verification
    # does not make an unfinished visual review a completed image audit.
    report.update(kind='deadline_launch_selection', images_audited=counts['reviewed_white'] + counts['resolved_original'],
                  unfinished_reviews_kept_original=counts['unfinished_original'],
                  complete_catalog_images=95401, deadline_at=config['deadline_at'],
                  full_visual_audit_complete=counts['unfinished_original'] == 0,
                  source_audit=str(audit), pilot_validation_sha256=identity['pilot_validation_sha256'])
    write_json(destination / 'verification.json', report)
    latest = {'state': 'verified', 'slot': slot, 'verified_at': time.time(),
              'verification': str(destination / 'verification.json'),
              'verification_sha256': sha256(destination / 'verification.json'),
              'media': report['selected_media'], 'media_csv': str(destination / 'selected-data/4-media.csv'),
              'selection_csv': str(destination / 'selection.csv'), 'counts': report['counts'],
              'unfinished_reviews_kept_original': counts['unfinished_original'],
              'deadline_at': config['deadline_at'], 'published': False, 'catalog_imported': False}
    # This pointer exposes the snapshot only after all hashes and CSV references
    # have been verified and the truthful visual-review counts are recorded.
    write_json(root / 'latest.json', latest)
    write_json(root / 'status.json', {**latest, 'updated_at': time.time(), 'pid': os.getpid()})
    return latest


def process_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def due_slot(config, latest, now):
    if latest and latest.get('slot') == 'deadline':
        return None
    if now >= config['freeze_at']:
        return 'deadline'
    if not latest:
        return 'baseline'
    return None


def maybe_start(job, audit, config):
    root = audit / 'launch-delivery'
    with (root / 'schedule.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state_path = root / 'status.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if state.get('state') == 'needs_attention':
            return
        process_file = root / 'process.json'
        process = json.loads(process_file.read_text()) if process_file.exists() else {}
        if process_alive(process.get('pid')):
            return
        latest_path = root / 'latest.json'
        latest = json.loads(latest_path.read_text()) if latest_path.exists() else None
        slot = due_slot(config, latest, time.time())
        if not slot:
            return
        arguments = ['/usr/bin/caffeinate', '-i', config['python'], '-B', str(Path(__file__).resolve()),
                     'build', '--job', str(job), '--audit', str(audit), '--slot', slot]
        with (root / 'build.log').open('a') as log:
            proc = subprocess.Popen(arguments, cwd=str(job), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                    start_new_session=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        write_json(process_file, {'pid': proc.pid, 'arguments': arguments, 'started_at': time.time(), 'slot': slot})


def panel(audit, config):
    root = audit / 'launch-delivery'
    latest = json.loads((root / 'latest.json').read_text()) if (root / 'latest.json').exists() else None
    state = json.loads((root / 'status.json').read_text()) if (root / 'status.json').exists() else {}
    date = lambda value: datetime.fromtimestamp(value, ZoneInfo('America/Indiana/Indianapolis')).strftime('%a %b %d, %I:%M %p %Z')
    result = '<section id="launch-deadline"><h2>Tomorrow launch: 20-hour deadline</h2>'
    result += '<p>Ready by <strong>' + escape(date(config['deadline_at'])) + '</strong>. Final image selection starts ' + escape(date(config['freeze_at'])) + ', with one hour reserved for export and verification.</p>'
    result += '<p>The complete catalog uses verified white JPGs and the two approved mirror replacements. Scenes, rejected cutouts and unfinished reviews keep their originals. The full audit continues separately.</p>'
    priority_path = audit / 'review-priority/status.json'
    if priority_path.exists():
        priority = json.loads(priority_path.read_text())
        measured = priority.get('done', priority.get('measured', 0))
        result += '<p>Parallel native checks: <strong>' + escape(f'{measured:,}') + '</strong> pairs measured. The review queue checks the simplest cutouts first, using the same individual model and region checks.</p>'
    if latest:
        result += '<p><strong>Complete launch selection verified</strong> (' + escape(latest['slot']) + ', ' + escape(date(latest['verified_at'])) + ').</p><pre>' + escape(json.dumps(latest['counts'], indent=2)) + '</pre>'
        for key, label in [('media_csv', 'Launch media CSV'), ('media', 'Launch image folder'), ('verification', 'Verification report'), ('selection_csv', 'Image selection CSV')]:
            result += '<a href="' + escape(Path(latest[key]).as_uri(), quote=True) + '">' + label + '</a> | '
    else:
        result += '<p>Building and verifying the initial complete selection.</p>'
    if state.get('state') == 'needs_attention':
        result += '<p><strong>Launch selection needs attention:</strong> ' + escape(state.get('error', 'Unknown error')) + '</p>'
    result += '<p>Originals remain intact. Import and publication have not been performed.</p></section>'
    return result


def qualify_progress(html, console):
    html = re.sub(r'(<p>Current review pass: [^;]+); estimate: .*?</p>',
                  r'\1. Reviews run in order of measured complexity.</p>', html)
    html = re.sub(r'<p>Estimated full selection ready: .*?</p>',
                  '<p>The full visual audit continues separately. Its completion estimate is unavailable while simple cutouts run first. The launch selection uses the fixed deadline above.</p>', html)
    console = re.sub(r'^(Current review: [^;\n]+); ETA .*$',
                     r'\1; prioritized by complexity, full-audit ETA unavailable', console, flags=re.MULTILINE)
    return html, console


def monitor(job, audit, config, do_notify):
    sys.path.insert(0, str(audit / 'runtime-code'))
    import white_jpeg_monitor as original_monitor
    maybe_start(job, audit, config)
    output = io.StringIO()
    with redirect_stdout(output):
        original_monitor.check(job, do_notify=do_notify)
    html_path = job / 'status.html'
    html = html_path.read_text()
    console = output.getvalue()
    if (audit / 'review-priority/controller-transition.json').exists():
        html, console = qualify_progress(html, console)
    print(console, end='', flush=True)
    boundary = html.index('</h1>') + len('</h1>')
    temporary = html_path.with_suffix('.deadline.tmp')
    temporary.write_text(html[:boundary] + panel(audit, config) + html[boundary:])
    os.replace(temporary, html_path)
    root = audit / 'launch-delivery'
    state = json.loads((root / 'status.json').read_text()) if (root / 'status.json').exists() else {}
    event = 'failed' if state.get('state') == 'needs_attention' else 'final_ready' if state.get('slot') == 'deadline' and state.get('state') == 'verified' else None
    notified = root / 'notification.json'
    previous = json.loads(notified.read_text()) if notified.exists() else {}
    if do_notify and event and event != previous.get('event'):
        message = 'Launch image selection is complete and verified. Originals are preserved.' if event == 'final_ready' else 'Launch image export needs attention: ' + state.get('error', '')[:160]
        notification = original_monitor.notify(message)
        write_json(notified, {'event': event, 'at': time.time(), 'notification': notification})
    print('Launch deadline: ' + datetime.fromtimestamp(config['deadline_at'], ZoneInfo('America/Indiana/Indianapolis')).isoformat(), flush=True)
    print('Launch selection: ' + str(state.get('state', 'scheduled')), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['monitor', 'build'])
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--slot', choices=['baseline', 'deadline'])
    parser.add_argument('--no-notify', action='store_true')
    args = parser.parse_args()
    job, audit = args.job.resolve(), args.audit.resolve()
    if not audit.is_relative_to(job):
        raise ValueError('Audit must be within its job')
    root = audit / 'launch-delivery'
    config = json.loads((root / 'config.json').read_text())
    if args.command == 'monitor':
        monitor(job, audit, config, not args.no_notify)
        return
    if not args.slot:
        parser.error('build requires --slot')
    with (root / 'build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            write_json(root / 'status.json', {'state': 'building', 'slot': args.slot, 'updated_at': time.time(), 'pid': os.getpid()})
            result = snapshot(job, audit, config, args.slot)
            print(json.dumps(result, indent=2), flush=True)
        except BaseException as error:
            write_json(root / 'status.json', {'state': 'needs_attention', 'slot': args.slot, 'error': str(error), 'updated_at': time.time(), 'pid': os.getpid()})
            raise


if __name__ == '__main__':
    main()
