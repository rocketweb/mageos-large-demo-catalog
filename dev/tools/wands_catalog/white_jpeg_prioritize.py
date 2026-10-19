#!/usr/bin/env python3
"""Measure pending pairs in parallel so low-risk reviews can run first.

Ranking changes review order only. It cannot approve a processed image.
"""
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import argparse
import json
import multiprocessing
from pathlib import Path
import sqlite3
import sys
import time


def measure(task):
    job, code, row = task
    if str(code) not in sys.path:
        sys.path.insert(0, str(code))
    import white_jpeg_calibrated_audit as checks
    original, candidate = checks.load_pair(job, row)
    metrics = checks.features(original, candidate)
    return row, metrics, checks.screen(row, metrics)


def run(job, audit, workers):
    sys.path.insert(0, str(audit / 'runtime-code'))
    import white_jpeg_calibrated_audit as checks
    from white_jpeg_worker import atomic_json, sha256
    root = audit / 'review-priority'
    root.mkdir(exist_ok=True)
    with sqlite3.connect((audit / 'audit.sqlite3').as_uri() + '?mode=ro', uri=True) as source:
        rows = [json.loads(r[0]) for r in source.execute("SELECT row_json FROM images WHERE decision IS NULL AND json_extract(row_json,'$.output_file') IS NOT NULL ORDER BY n")]
    db = sqlite3.connect(root / 'features.sqlite3')
    db.execute('CREATE TABLE IF NOT EXISTS features(file TEXT PRIMARY KEY,source_sha256 TEXT,output_sha256 TEXT,identity TEXT,features TEXT,screen TEXT,region_count INTEGER)')
    identity = checks.decision_identity()
    existing = {r[0]: r[1:] for r in db.execute('SELECT file,source_sha256,output_sha256,identity FROM features')}
    for row in rows:
        if row['file'] in existing and existing[row['file']] != (row['source_sha256'], row['output_sha256'], identity):
            raise ValueError('Priority measurements changed')
    todo = iter(row for row in rows if row['file'] not in existing)
    started = time.time()
    done = 0

    def progress():
        atomic_json(root / 'status.json', {'state': 'measuring', 'done': len(existing) + done, 'total': len(rows),
            'updated_at': time.time(), 'elapsed_seconds': time.time() - started, 'checks_identity': identity,
            'policy': 'Review order only; every approved JPG still needs the qualified individual model and region reviews.'})

    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn')) as pool:
        pending = set()
        def submit():
            row = next(todo, None)
            if row is not None:
                pending.add(pool.submit(measure, (job, audit / 'runtime-code', row)))
        for _ in range(workers * 2):
            submit()
        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                pending.remove(future)
                row, metrics, reason = future.result()
                db.execute('INSERT INTO features VALUES(?,?,?,?,?,?,?)', (row['file'], row['source_sha256'],
                    row['output_sha256'], identity, json.dumps(metrics), reason, len(metrics['risk_regions'])))
                done += 1
                if done % 64 == 0:
                    db.commit()
                if done % 500 == 0:
                    progress()
                    print(json.dumps({'measured': done, 'seconds': time.time() - started}), flush=True)
                submit()
    db.commit()
    ordered = [r[0] for r in db.execute('SELECT file FROM features WHERE screen IS NULL ORDER BY region_count,file')]
    screened = db.execute('SELECT count(*) FROM features WHERE screen IS NOT NULL').fetchone()[0]
    histogram = dict(db.execute('SELECT region_count,count(*) FROM features WHERE screen IS NULL GROUP BY region_count'))
    db.close()
    result = {'state': 'ready', 'files': ordered, 'screened_keep_original': screened, 'regions': histogram,
              'checks_identity': identity, 'measured': len(existing) + done, 'created_at': time.time(),
              'elapsed_seconds': time.time() - started, 'database_sha256': sha256(root / 'features.sqlite3'),
              'policy': 'Ordering only. No processed JPG is approved by these measurements.'}
    atomic_json(root / 'ready.json', result)
    atomic_json(root / 'status.json', {k: v for k, v in result.items() if k != 'files'})
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    run(args.job.resolve(), args.audit.resolve(), args.workers)
