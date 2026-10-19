#!/usr/bin/env python3
"""Measure source material loss for candidates with local native flags."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing
from pathlib import Path
import sqlite3
import time

import white_jpeg_expanded_fast as policy
import white_jpeg_calibrated_audit as checks


def measure(task):
    job, row = task
    original, candidate = checks.load_pair(job, row)
    return (row['file'], row['source_sha256'], row['output_sha256'],
            policy.measurement_identity(), json.dumps(policy.features(original, candidate), sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--source-audit', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    args = parser.parse_args()
    meta = json.loads((args.source_audit/'image-categories.json').read_text())
    source = sqlite3.connect((args.source_audit/'audit.sqlite3').resolve().as_uri()+'?mode=ro', uri=True)
    cache = sqlite3.connect(args.audit/'expanded-features.sqlite3')
    cache.execute('CREATE TABLE IF NOT EXISTS expanded_features(file TEXT PRIMARY KEY,source_sha256 TEXT,output_sha256 TEXT,identity TEXT,features TEXT)')
    cached = {f: (s, o, i) for f, s, o, i in cache.execute('SELECT file,source_sha256,output_sha256,identity FROM expanded_features')}
    rows = []
    for encoded, f in source.execute('SELECT i.row_json,f.features FROM images i JOIN category_features f USING(file) WHERE i.decision IS NULL'):
        row = json.loads(encoded)
        if policy.route(row, json.loads(f), meta[row['file']])[0] != 'measure':
            continue
        if cached.get(row['file']) == (row['source_sha256'], row['output_sha256'], policy.measurement_identity()):
            continue
        rows.append(row)
    source.close()
    started = time.time()
    def progress(done):
        value = {'done': done, 'total': len(rows), 'elapsed_seconds': time.time()-started,
                 'updated_at': time.time(), 'measurement_identity': policy.measurement_identity()}
        path = args.audit/'expanded-measurements-status.json'
        temp = path.with_suffix('.tmp'); temp.write_text(json.dumps(value, indent=2)); temp.replace(path)
        print(json.dumps(value), flush=True)
    progress(0)
    with ProcessPoolExecutor(max_workers=8, mp_context=multiprocessing.get_context('spawn')) as pool:
        batch = []
        for done, result in enumerate(pool.map(measure, ((args.job, row) for row in rows), chunksize=8), 1):
            batch.append(result)
            if len(batch) >= 128:
                with cache:
                    cache.executemany('INSERT OR REPLACE INTO expanded_features VALUES(?,?,?,?,?)', batch)
                batch = []; progress(done)
        if batch:
            with cache:
                cache.executemany('INSERT OR REPLACE INTO expanded_features VALUES(?,?,?,?,?)', batch)
    progress(len(rows)); cache.close()


if __name__ == '__main__': main()
