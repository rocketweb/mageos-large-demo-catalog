#!/usr/bin/env python3
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
from pathlib import Path
import sqlite3
import time
import white_jpeg_glass_outline as policy
import white_jpeg_calibrated_audit as native


def measure(task):
    job, row = task
    original, candidate = native.load_pair(job, row)
    values = policy.features(original, candidate)
    return {'file': row['file'], 'source_sha256': row['source_sha256'],
            'output_sha256': row['output_sha256'], 'identity': policy.identity(),
            'measurements': values, 'decision': policy.choose(values)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--audit', type=Path, required=True)
    args = p.parse_args(); audit = args.audit.resolve(); job = audit.parent; out = audit/'glass-outline-audit'
    scope = json.loads((out/'scope.json').read_text())['images']
    db = sqlite3.connect((audit/'audit.sqlite3').as_uri()+'?mode=ro', uri=True)
    rows = [json.loads(r) for f,r in db.execute('SELECT file,row_json FROM images') if f in scope]
    rows = [r for r in rows if r.get('output_file')]; db.close()
    started = time.time(); results = {}
    def status(done):
        value = {'phase': 'measuring_glass_outlines', 'done': done, 'total': len(rows),
                 'elapsed_seconds': time.time()-started, 'updated_at': time.time()}
        path = out/'status.json'; tmp = path.with_suffix('.tmp'); tmp.write_text(json.dumps(value)); tmp.replace(path)
    status(0)
    with ProcessPoolExecutor(max_workers=8, mp_context=multiprocessing.get_context('spawn')) as pool:
        for done, result in enumerate(pool.map(measure, ((job,r) for r in rows), chunksize=8), 1):
            results[result['file']] = result
            if done%128 == 0: status(done)
    path = out/'measurements.json'; tmp = path.with_suffix('.tmp'); tmp.write_text(json.dumps(results)); tmp.replace(path)
    status(len(rows)); print('Measured',len(results),'source/candidate pairs with verified hashes.',flush=True)


if __name__ == '__main__': main()
