#!/usr/bin/env python3
"""Category-based white JPEG selection with a fast path and focused review."""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, wait, FIRST_COMPLETED
import fcntl
import hashlib
from html import escape
import io
import inspect
import json
import math
import multiprocessing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import white_jpeg_category_policy as policy
import white_jpeg_expanded_fast as expanded
import white_jpeg_human_approval as human
import white_jpeg_dark_fast as dark

NATIVE_IDENTITY = 'a021edad17b9dcc08972cf4459ef7af328a1b7ebac796d1f1297c4dac66b906c'


def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    os.replace(temp, path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native(audit):
    sys.path.insert(0, str(audit / 'runtime-code'))
    import white_jpeg_calibrated_audit
    return white_jpeg_calibrated_audit


def connect(audit):
    db = sqlite3.connect(audit / 'audit.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    db.executescript('''CREATE TABLE IF NOT EXISTS category_features(file TEXT PRIMARY KEY,
        source_sha256 TEXT,output_sha256 TEXT,native_identity TEXT,features TEXT);
        CREATE TABLE IF NOT EXISTS category_evidence(file TEXT PRIMARY KEY,policy TEXT,method TEXT,
        source_sha256 TEXT,output_sha256 TEXT,feature_sha256 TEXT,review TEXT,details TEXT,decided_at REAL);
        CREATE TABLE IF NOT EXISTS category_meta(key TEXT PRIMARY KEY,value TEXT);''')
    db.execute('''CREATE TABLE IF NOT EXISTS expanded_features(file TEXT PRIMARY KEY,
        source_sha256 TEXT,output_sha256 TEXT,identity TEXT,features TEXT)''')
    return db


def progress(audit, db, phase, **extra):
    counts = dict(db.execute("SELECT coalesce(decision,'pending'),count(*) FROM images GROUP BY decision"))
    methods = human.methods(db)
    state = {'phase': phase, 'audit_kind': 'category', 'updated_at': time.time(), 'pid': os.getpid(),
             'total': 95401, 'decisions': counts, 'methods': methods,
             'metrics_complete': db.execute('SELECT count(*) FROM category_features').fetchone()[0],
             'individual_reviews': db.execute("SELECT count(*) FROM category_evidence WHERE method='context_review'").fetchone()[0],
             'originals_modified': False, 'catalog_imported': False, 'error': None, **extra}
    write(audit / 'status.json', state)
    return state


def initialize(job, audit):
    checks = native(audit)
    import white_jpeg_calibrated_run as prior_controller
    prior_controller.verify_runtime(audit)
    if checks.decision_identity() != NATIVE_IDENTITY:
        raise ValueError('Native measurement protocol changed')
    config = json.loads((audit / 'config.json').read_text())
    db = connect(audit)
    ident = {'version': policy.VERSION, 'policy_identity': policy.identity(), 'policy': policy.POLICY,
             'model': policy.MODEL, 'native_identity': checks.decision_identity(),
             'metadata_sha256': sha(audit / 'image-categories.json'),
             'original_inventory_sha256': sha(job / 'audit-inputs.json'),
             'source_csv_sha256': json.loads((audit / 'source-integrity.json').read_text())['original_media_csv_sha256']}
    if config.get('expanded_fast_checks'):
        ident['expanded_policy_identity'] = expanded.identity()
    identity_path = audit / 'identity.json'
    if identity_path.exists() and json.loads(identity_path.read_text()) != ident:
        raise ValueError('Category policy or input metadata changed')
    if not identity_path.exists():
        write(identity_path, ident)
    if db.execute("SELECT value FROM category_meta WHERE key='initialized'").fetchone():
        return db
    if db.execute('SELECT count(*) FROM images').fetchone()[0] != 95401:
        raise ValueError('Expected the complete catalog inventory')
    with db:
        db.execute('CREATE TABLE IF NOT EXISTS category_prior_decisions AS SELECT file,decision,reason FROM images')
        db.execute('UPDATE images SET decision=NULL,reason=NULL')
        db.execute("INSERT INTO category_meta VALUES('initialized',?)", (policy.identity(),))
    inventory = {r['file']: json.loads(r['row_json']) for r in db.execute('SELECT file,row_json FROM images')}
    old = Path(config['old_audit'])
    with sqlite3.connect((old / 'review-priority/features.sqlite3').as_uri() + '?mode=ro', uri=True) as cached:
        batch = []
        for file, src, out, identity, metrics in cached.execute('SELECT file,source_sha256,output_sha256,identity,features FROM features'):
            row = inventory.get(file)
            if row and (src, out, identity) == (row['source_sha256'], row.get('output_sha256'), ident['native_identity']):
                batch.append((file, src, out, identity, metrics))
        with db:
            db.executemany('INSERT OR IGNORE INTO category_features VALUES(?,?,?,?,?)', batch)
    batch = []
    for record in db.execute('SELECT i.row_json,f.features FROM images i JOIN calibrated_features f ON i.file=f.file'):
        row = json.loads(record[0]); m = json.loads(record[1])
        if row.get('output_file') and 'white_border' in m:
            batch.append((row['file'], row['source_sha256'], row['output_sha256'], ident['native_identity'], record[1]))
    with db:
        db.executemany('INSERT OR IGNORE INTO category_features VALUES(?,?,?,?,?)', batch)
    return db


def measure(task):
    job, audit, row = task
    checks = native(audit)
    original, candidate = checks.load_pair(job, row)
    return row, checks.features(original, candidate)


def measure_missing(job, audit, db):
    rows = [json.loads(r[0]) for r in db.execute("SELECT row_json FROM images WHERE json_extract(row_json,'$.output_file') IS NOT NULL AND file NOT IN (SELECT file FROM category_features)")]
    started = time.time(); completed = 0
    progress(audit, db, 'measuring_remaining_pairs', phase_done=0, phase_total=len(rows))
    identity = native(audit).decision_identity()
    with ProcessPoolExecutor(max_workers=8, mp_context=multiprocessing.get_context('spawn')) as pool:
        iterator = pool.map(measure, ((job, audit, row) for row in rows), chunksize=8)
        batch = []
        for row, m in iterator:
            batch.append((row['file'], row['source_sha256'], row['output_sha256'], identity, json.dumps(m)))
            completed += 1
            if len(batch) >= 64:
                with db: db.executemany('INSERT INTO category_features VALUES(?,?,?,?,?)', batch)
                batch = []
                progress(audit, db, 'measuring_remaining_pairs', phase_done=completed, phase_total=len(rows), elapsed_seconds=time.time()-started)
        if batch:
            with db: db.executemany('INSERT INTO category_features VALUES(?,?,?,?,?)', batch)


def feature(db, row):
    record = db.execute('SELECT * FROM category_features WHERE file=?', (row['file'],)).fetchone()
    if record is None:
        return None
    if (record['source_sha256'] != row['source_sha256'] or record['output_sha256'] != row.get('output_sha256') or
            record['native_identity'] != NATIVE_IDENTITY):
        raise ValueError('Native features belong to different image bytes')
    return json.loads(record['features'])


def expanded_feature(db, row):
    record = db.execute('SELECT * FROM expanded_features WHERE file=?', (row['file'],)).fetchone()
    if record is None:
        return None
    if (record['source_sha256'] != row['source_sha256'] or record['output_sha256'] != row.get('output_sha256') or
            record['identity'] != expanded.measurement_identity()):
        raise ValueError('Source-material measurements belong to different bytes or protocol')
    return json.loads(record['features'])


def save(db, row, decision, reason, method, metrics=None, review=None, details=None):
    if decision not in ('white', 'original'):
        raise ValueError('Only terminal decisions may be saved')
    if human.directive(db,row['file']) is not None:
        return
    feature_hash = hashlib.sha256(json.dumps(metrics, sort_keys=True).encode()).hexdigest()
    with db:
        db.execute('INSERT INTO category_evidence VALUES(?,?,?,?,?,?,?,?,?)', (row['file'], policy.identity(), method,
            row['source_sha256'], row.get('output_sha256'), feature_hash, json.dumps(review), json.dumps(details or {}), time.time()))
        db.execute('UPDATE images SET decision=?,reason=? WHERE file=?', (decision, reason, row['file']))


def prior_positive(db, row, metrics, checks):
    old = db.execute("SELECT * FROM calibrated_reviews WHERE file=? AND kind='pair'", (row['file'],)).fetchone()
    if not old or old['source_sha256'] != row['source_sha256'] or old['output_sha256'] != row.get('output_sha256') or old['identity'] != NATIVE_IDENTITY:
        return None
    review, details = json.loads(old['review']), json.loads(old['details'])
    if details.get('model') != checks.MODEL or details.get('review_identity') != checks.review_identity(checks.MODEL):
        raise ValueError('Prior review protocol changed')
    if checks.choose(row, metrics, review, details.get('focus'))[0] == 'white':
        return {'review': review, 'details': details}
    return None


def fast_pass(audit, db):
    meta = json.loads((audit / 'image-categories.json').read_text()); checks = native(audit)
    use_expanded = json.loads((audit/'config.json').read_text()).get('expanded_fast_checks', False)
    rows = [json.loads(r[0]) for r in db.execute('SELECT row_json FROM images WHERE decision IS NULL ORDER BY n')]
    for i, row in enumerate(rows, 1):
        m = feature(db, row); decision, reason = policy.route(row, m, meta[row['file']])
        method, details = 'fast', None
        if use_expanded and decision == 'review':
            extra = expanded_feature(db, row)
            decision, reason = expanded.route(row, m, meta[row['file']], extra)
            if decision == 'white':
                method = 'fast_expanded'
                details = {'expanded_policy_identity': expanded.identity(),
                           'supplemental_sha256': hashlib.sha256(json.dumps(extra, sort_keys=True).encode()).hexdigest()}
        if decision == 'measure':
            raise ValueError('Missing candidate measurements after native pass')
        if decision == 'review':
            previous = prior_positive(db, row, m, checks)
            if previous:
                save(db, row, 'white', 'previous_stricter_individual_review_passed', 'prior_verified', m, details=previous)
            else:
                with db: db.execute('UPDATE images SET reason=? WHERE file=?', (reason, row['file']))
        else:
            save(db, row, decision, reason, method if decision == 'white' else 'category_or_native_original', m, details=details)
        if i % 2000 == 0:
            progress(audit, db, 'applying_category_fast_checks', phase_done=i, phase_total=len(rows))
    progress(audit, db, 'fast_checks_complete', phase_done=len(rows), phase_total=len(rows))


def primary_request(job, audit, row, metrics, meta):
    from PIL import Image
    checks = native(audit)
    from image_review import api_key, request_vision
    original, candidate = checks.load_pair(job, row)
    content = [{'type': 'text', 'text': json.dumps({'file': row['file'], 'source_sha256': row['source_sha256'],
        'candidate_sha256': row['output_sha256'], 'classes': meta['classes'], 'categories': meta['categories']})}]
    paths = [checks.original_root(job) / row['file'], Path(row.get('output_path') or job / 'media/wands-expanded' / row['output_file'])]
    for label, path in zip(('Original', 'White candidate'), paths):
        data = path.read_bytes()
        expected = row['source_sha256'] if label == 'Original' else row['output_sha256']
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Review bytes changed')
        content.extend([{'type': 'text', 'text': label}, {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(data).decode()}}])
    # Include the two largest measured changes in the same individual request.
    crops = []
    for region in sorted(metrics['risk_regions'], key=lambda x: -x['pixels'])[:2]:
        box = region['crop']; crops.append(box)
        for label, image in (('Original crop', original.crop(box)), ('Candidate crop', candidate.crop(box))):
            if max(image.size) < 512:
                image = image.resize((round(image.width * 512 / max(image.size)), round(image.height * 512 / max(image.size))), Image.Resampling.NEAREST)
            stream = io.BytesIO(); image.save(stream, 'PNG')
            content.extend([{'type': 'text', 'text': label + ' ' + region['kind']}, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()}}])
    payload = {'model': policy.MODEL, 'temperature': 0, 'chat_template_kwargs': {'enable_thinking': False},
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'background_first_review', 'strict': True, 'schema': policy.SCHEMA}},
        'messages': [{'role': 'system', 'content': policy.SYSTEM}, {'role': 'user', 'content': content}]}
    start = time.time(); review, attempts = request_vision(payload, api_key('/Users/matt/.omlx/settings.json'), policy.parse)
    return review, {'model': policy.MODEL, 'policy': policy.identity(), 'payload_sha256': hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
                    'crops': crops, 'attempts': attempts, 'seconds': time.time()-start}


def major_regions(metrics, meta):
    pixels = math.prod(metrics['dimensions'])
    limits = {'enclosed_whitened_area': policy.POLICY['enclosed_component_fraction_max'],
              'erased_dark_area': policy.POLICY['dark_component_fraction_max'],
              'new_cutout_edge': policy.POLICY['new_edge_component_fraction_max'],
              'missing_source_edge': policy.POLICY['missing_edge_component_fraction_max']}
    enclosed_total = sum(r['pixels'] for r in metrics['risk_regions'] if r['kind'] == 'enclosed_whitened_area') / pixels
    reflective = any('mirror' in c.casefold() for c in meta['classes'])
    result = []
    for region in metrics['risk_regions']:
        kind = region['kind']
        if (region['pixels']/pixels > limits[kind] or
                (kind == 'enclosed_whitened_area' and enclosed_total > policy.POLICY['enclosed_total_fraction_max']) or
                (reflective and kind in ('enclosed_whitened_area', 'missing_source_edge', 'erased_dark_area'))):
            result.append(region)
    return result


def context_identity(audit):
    checks = native(audit)
    value = {'policy_identity': policy.identity(), 'region_protocol': checks.regions.identity(policy.MODEL),
             'implementation': ''.join(inspect.getsource(f) for f in (primary_request, major_regions, complete_review, context_decision)),
             'max_major_regions': 8}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def complete_review(job, audit, row, metrics, meta, review, details):
    checks = native(audit)
    details = {**details, 'context_identity': context_identity(audit), 'strategy': 'tolerant_primary_with_major_region_veto'}
    if policy.choose_review(review)[0] != 'white':
        return review, details
    regions = major_regions(metrics, meta)
    if len(regions) > 8:
        details['unresolved_native_risk'] = 'more_than_eight_major_changes'
    elif not regions and (metrics['retained_pixel_agreement'] < policy.POLICY['retained_pixel_agreement_min'] or
                          metrics['native_edge_retention'] < policy.POLICY['native_edge_retention_min']):
        details['unresolved_native_risk'] = 'diffuse_product_change_without_a_verifiable_region'
    elif regions:
        from image_review import api_key
        original, candidate = checks.load_pair(job, row)
        details['focus'] = checks.regions.request(original, candidate, row, regions,
            api_key('/Users/matt/.omlx/settings.json'), policy.MODEL, audit/'region-cache')
    return review, details


def context_decision(audit, row, metrics, meta, review, details):
    decision, reason = policy.choose_review(review)
    if decision != 'white':
        return decision, reason
    if details.get('context_identity') != context_identity(audit):
        raise ValueError('Context-review protocol changed')
    if details.get('unresolved_native_risk'):
        return 'original', 'substantial_or_uncertain_native_changes_keep_original'
    regions = major_regions(metrics, meta)
    verified = native(audit).regions.approval(row, regions, details.get('focus'), policy.MODEL)
    if verified is not True:
        return 'original', 'substantial_or_uncertain_changed_region_keep_original'
    return decision, reason


def request_pair(job, audit, row, metrics, meta):
    review, details = primary_request(job, audit, row, metrics, meta)
    return complete_review(job, audit, row, metrics, meta, review, details)


def speedup_qualification(db, kind, identity):
    if not human.table_exists(db, 'speedup_qualifications'):
        raise ValueError('Faster review is missing its qualification')
    record = db.execute('SELECT validation_json,validation_sha256 FROM speedup_qualifications WHERE identity=? AND kind=?', (identity, kind)).fetchone()
    if not record or hashlib.sha256(record[0].encode()).hexdigest() != record[1]:
        raise ValueError('Faster review qualification changed')
    value = json.loads(record[0])
    expected = value.get('dark_identity') if kind == 'dark' else None
    count=value.get('total_cases',value.get('cases',0))
    if not value.get('passed') or expected != identity or value.get('unsafe_approvals') or count<537 or value.get('known_bad',0)<37:
        raise ValueError('Faster review failed its safety pilot')
    return record[1]


def native_original_reason(metrics, meta):
    """Cases rejected by the existing reviewer for every valid primary verdict."""
    if policy.room_bundle(meta):
        return 'room_bundle_preserve_scene'
    regions = major_regions(metrics, meta)
    if len(regions) > 8:
        return 'more_than_eight_major_changes_keep_original'
    if not regions and (metrics['retained_pixel_agreement'] < policy.POLICY['retained_pixel_agreement_min'] or
                        metrics['native_edge_retention'] < policy.POLICY['native_edge_retention_min']):
        return 'diffuse_product_change_without_a_verifiable_region_keep_original'
    return None


def register_speedup(db, audit):
    """Called after a backup while holding export.lock; old evidence is immutable."""
    config = json.loads((audit/'config.json').read_text())
    if config.get('combined_reviews'):
        raise ValueError('Combined vision review failed its pilot and cannot be enabled')
    db.executescript('''CREATE TABLE IF NOT EXISTS speedup_qualifications(
      identity TEXT PRIMARY KEY,kind TEXT,validation_json TEXT,validation_sha256 TEXT);
      CREATE TRIGGER IF NOT EXISTS speedup_qualification_immutable_update BEFORE UPDATE ON speedup_qualifications
      BEGIN SELECT RAISE(ABORT,'Review qualifications are immutable'); END;
      CREATE TRIGGER IF NOT EXISTS speedup_qualification_immutable_delete BEFORE DELETE ON speedup_qualifications
      BEGIN SELECT RAISE(ABORT,'Review qualifications are immutable'); END;''')
    with db:
        for kind, enabled, filename, identity in [('dark', config.get('dark_fast_checks'), 'dark-validation.json', dark.identity())]:
            if not enabled:
                continue
            path = Path(config['speedup_validation_root'])/filename
            text = path.read_text();value = json.loads(text)
            if not value.get('passed') or value.get('unsafe_approvals') or value['metadata_sha256'] != sha(audit/'image-categories.json'):
                raise ValueError('Missing or invalid faster-review pilot')
            if (value['manifest_sha256'] != sha(path.parent/'manifest.json') or
                    value['results_sha256'] != sha(path.parent/'dark-pilot-results.json')):
                raise ValueError('Faster-review pilot artifacts changed')
            db.execute('INSERT OR IGNORE INTO speedup_qualifications VALUES(?,?,?,?)', (identity, kind, text, hashlib.sha256(text.encode()).hexdigest()))
            speedup_qualification(db, kind, identity)


def speedup_fast_pass(job, audit, db):
    config = json.loads((audit/'config.json').read_text())
    if not config.get('dark_fast_checks') and not config.get('native_fast_holds'):
        return
    meta = json.loads((audit/'image-categories.json').read_text())
    glass = set(json.loads((audit/'glass-outline-audit/scope.json').read_text())['images'])
    excluded_path = job/'catalog-exclusions.json';excluded = set()
    if excluded_path.exists():
        exclusion_config = json.loads(excluded_path.read_text());policy_path = Path(exclusion_config['policy'])
        if sha(policy_path) != exclusion_config['policy_sha256']:
            raise ValueError('Catalog exclusion scope changed')
        excluded = {i['sku']for i in json.loads(policy_path.read_text())['products']}
    dark_proof = speedup_qualification(db, 'dark', dark.identity()) if config.get('dark_fast_checks') else None
    source_root = native(audit).original_root(job) if dark_proof else None
    changed = []
    rows = [json.loads(r[0])for r in db.execute('SELECT row_json FROM images WHERE decision IS NULL ORDER BY n')]
    for row in rows:
        m = feature(db,row);metadata = meta[row['file']]
        if metadata.get('skus') and set(metadata['skus']) <= excluded:
            save(db,row,'original','removed_product_no_image_review_needed','speedup_native_original',m)
            changed.append({'file':row['file'],'decision':'original','reason':'removed_product'})
            continue
        if dark_proof and dark.gate(row,m,metadata,row['file']in glass):
            source = source_root/row['file']
            candidate = Path(row.get('output_path') or job/'media/wands-expanded'/row['output_file'])
            from PIL import Image
            images=[]
            for path,expected in ((source,row['source_sha256']),(candidate,row['output_sha256'])):
                data=path.read_bytes()
                if hashlib.sha256(data).hexdigest()!=expected:
                    raise ValueError('Dark-product input hash changed')
                with Image.open(io.BytesIO(data))as image:images.append(image.convert('RGB'))
            values = dark.features(*images,m)
            if dark.passes(values):
                save(db,row,'white','dark_product_preserved_no_new_internal_white_holes','fast_dark',m,
                     details={'identity':dark.identity(),'validation_sha256':dark_proof,'measurements':values,
                              'original_path':str(source),'candidate_path':str(candidate)})
                changed.append({'file':row['file'],'decision':'white','reason':'fast_dark'})
                continue
        # These cases are original under every possible outcome of the old reviewer.
        if config.get('native_fast_holds'):
            hold = native_original_reason(m,metadata)
            if hold:
                save(db,row,'original',hold,'speedup_native_original',m)
                changed.append({'file':row['file'],'decision':'original','reason':hold})
    write(audit/'speedup-fast-pass.json',{'changed':changed,'counts':{decision:sum(i['decision']==decision for i in changed)for decision in ('white','original')},'at':time.time()})


def review_pending(job, audit, db):
    meta = json.loads((audit / 'image-categories.json').read_text())
    records = db.execute('SELECT row_json,reason FROM images WHERE decision IS NULL').fetchall()
    priority = {'bedding_set_needs_context_review': 0, 'flagged_original_background': 1, 'flagged_output_background': 2, 'reflective_glass_cutout_risk': 3}
    rows = [json.loads(r[0]) for r in sorted(records, key=lambda r: (priority.get(r[1], 4), json.loads(r[0])['n']))]
    iterator = iter(rows); started = time.time(); done = 0; errors = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {}
        def submit():
            row = next(iterator, None)
            while row is not None and db.execute('SELECT decision FROM images WHERE file=?',(row['file'],)).fetchone()[0] is not None:
                row = next(iterator, None)
            if row is not None:
                m = feature(db, row)
                pending[pool.submit(request_pair, job, audit, row, m, meta[row['file']])] = (row, m)
        for _ in range(4): submit()
        while pending:
            finished, _ = wait(pending, timeout=30, return_when=FIRST_COMPLETED)
            for future in finished:
                row, m = pending.pop(future)
                try:
                    review, details = future.result()
                    decision, reason = context_decision(audit, row, m, meta[row['file']], review, details)
                    save(db, row, decision, reason, 'context_review', m, review, details); done += 1
                except Exception as error:
                    errors.append(error)
            if not errors:
                for _ in finished: submit()
            progress(audit, db, 'reviewing_bedding_and_flagged_cutouts', phase_done=done, phase_total=len(rows),
                     individual_reviews_per_hour=3600*done/max(time.time()-started, 1))
    if errors:
        raise errors[0]


def validate_white(db, row, meta, checks):
    if human.validate_white(db,row,meta):
        return
    evidence = db.execute('SELECT * FROM category_evidence WHERE file=?', (row['file'],)).fetchone()
    if not evidence or evidence['policy'] != policy.identity() or evidence['source_sha256'] != row['source_sha256'] or evidence['output_sha256'] != row.get('output_sha256'):
        raise ValueError('Selected JPG lacks matching category-policy evidence')
    m = feature(db, row)
    if evidence['feature_sha256'] != hashlib.sha256(json.dumps(m, sort_keys=True).encode()).hexdigest():
        raise ValueError('Selected JPG native evidence changed')
    if policy.room_bundle(meta):
        raise ValueError('Room Bundle cannot select processed media')
    method = evidence['method']
    if method == 'fast':
        passed = policy.route(row, m, meta)[0] == 'white'
    elif method == 'fast_dark':
        details=json.loads(evidence['details'])
        proof=speedup_qualification(db,'dark',dark.identity())
        if details.get('identity')!=dark.identity() or details.get('validation_sha256')!=proof:
            raise ValueError('Dark-product approval protocol changed')
        original=Path(details['original_path']);candidate=Path(details['candidate_path'])
        if sha(original)!=row['source_sha256'] or sha(candidate)!=row.get('output_sha256'):
            raise ValueError('Dark-product approval bytes changed')
        from PIL import Image
        with Image.open(original)as a,Image.open(candidate)as b:
            values=dark.features(a.convert('RGB'),b.convert('RGB'),m)
        scoped=human.table_exists(db,'glass_outline_checks') and db.execute('SELECT 1 FROM glass_outline_checks WHERE file=?',(row['file'],)).fetchone()is not None
        passed=(dark.gate(row,m,meta,scoped) and dark.passes(values) and values==details.get('measurements'))
    elif method == 'fast_expanded':
        extra = expanded_feature(db, row)
        details = json.loads(evidence['details'])
        passed = (details.get('expanded_policy_identity') == expanded.identity() and
                  details.get('supplemental_sha256') == hashlib.sha256(json.dumps(extra, sort_keys=True).encode()).hexdigest() and
                  expanded.route(row, m, meta, extra)[0] == 'white')
    elif method == 'context_review':
        details = json.loads(evidence['details'])
        passed = context_decision(Path(db.execute('PRAGMA database_list').fetchone()[2]).parent, row, m, meta,
            json.loads(evidence['review']), details)[0] == 'white'
        passed = passed and details['policy'] == policy.identity() and details['model'] == policy.MODEL
    elif method == 'prior_verified':
        passed = prior_positive(db, row, m, checks) is not None
    else:
        passed = False
    if not passed:
        raise ValueError('Selected white JPG does not pass its recorded method')


def export_selection(job, audit, slot):
    config = json.loads((audit / 'config.json').read_text()); checks = native(audit)
    import white_jpeg_audit_run as exporter
    with (audit / 'export.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        destination = audit / 'selections' / slot
        destination.mkdir(parents=True, exist_ok=True)
        if (destination / 'verification.json').exists():
            existing = json.loads((destination / 'verification.json').read_text())
            if existing.get('category_policy_verified'):
                return existing
        if not (destination / 'snapshot.json').exists():
            with sqlite3.connect((audit / 'audit.sqlite3').as_uri() + '?mode=ro', uri=True) as source:
                with sqlite3.connect(destination / 'audit.sqlite3') as target: source.backup(target)
            db = connect(destination); meta = json.loads((audit / 'image-categories.json').read_text())
            pending = db.execute('SELECT count(*) FROM images WHERE decision IS NULL').fetchone()[0]
            for record in db.execute("SELECT row_json FROM images WHERE decision='white'").fetchall():
                row = json.loads(record[0]); validate_white(db, row, meta[row['file']], checks)
            methods = human.methods(db)
            with db: db.execute("UPDATE images SET decision='original',reason='awaiting_context_review_keep_original' WHERE decision IS NULL")
            db.close()
            identity = {'kind': 'category_background_selection', 'slot': slot, 'created_at': time.time(),
                'policy_identity': policy.identity(), 'metadata_sha256': sha(audit / 'image-categories.json'),
                'pilot_validation_sha256': sha(audit / 'pilot-validation.json'), 'methods': methods, 'pending_at_snapshot': pending}
            if config.get('expanded_fast_checks'):
                identity.update(expanded_policy_identity=expanded.identity(),
                                expanded_validation_sha256=sha(audit/'expanded-validation.json'))
            write(destination / 'identity.json', identity); write(destination / 'snapshot.json', identity)
        identity = json.loads((destination / 'snapshot.json').read_text())
        if identity['policy_identity'] != policy.identity(): raise ValueError('Snapshot policy changed')
        if config.get('expanded_fast_checks') and identity.get('expanded_policy_identity') != expanded.identity():
            raise ValueError('Expanded snapshot policy changed')
        write(audit / 'export-status.json', {'state': 'building', 'slot': slot, 'pid': os.getpid(), 'updated_at': time.time()})
        report = exporter.select(job, destination, review_method='Category exclusions, native fast checks accepting minor changes, individual review of bedding and flagged candidates.',
            expected_original_csv_sha256=json.loads((audit / 'identity.json').read_text())['source_csv_sha256'],
            progress_callback=lambda done: write(audit / 'export-status.json', {'state': 'building', 'slot': slot, 'pid': os.getpid(), 'done': done, 'total': 95401, 'updated_at': time.time()}))
        report.update(category_policy_verified=True, policy_identity=policy.identity(), methods=identity['methods'],
            pending_reviews_kept_original=identity['pending_at_snapshot'], individual_visual_audit_complete=False,
            images_audited=95401-identity['pending_at_snapshot'], pilot_validation_sha256=identity['pilot_validation_sha256'])
        if config.get('expanded_fast_checks'):
            report.update(expanded_policy_identity=expanded.identity(),
                          expanded_validation_sha256=identity['expanded_validation_sha256'])
        write(destination / 'verification.json', report)
        latest = {'slot': slot, 'verified_at': time.time(), 'verification': str(destination / 'verification.json'),
            'verification_sha256': sha(destination / 'verification.json'), 'counts': report['counts'], 'methods': identity['methods'],
            'pending_reviews_kept_original': identity['pending_at_snapshot'], 'media': report['selected_media'],
            'media_csv': str(destination / 'selected-data/4-media.csv'), 'selection_csv': str(destination / 'selection.csv')}
        write(audit / 'latest.json', latest); write(audit / 'export-status.json', {'state': 'verified', **latest})
        return report


def run(job, audit):
    from image_review import ReviewServiceUnavailable
    config = json.loads((audit / 'config.json').read_text())
    with (audit / 'controller.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        db = initialize(job, audit)
        try:
            qualification = json.loads((audit / 'pilot-validation.json').read_text())
            if (not qualification['passed'] or qualification['policy_identity'] != policy.identity() or
                    qualification['native_identity'] != NATIVE_IDENTITY or
                    qualification['metadata_sha256'] != sha(audit/'image-categories.json') or
                    qualification['pilot_results_sha256'] != sha(audit/'pilot-results.json')):
                raise ValueError('Category pilot is missing or outdated')
            if config.get('expanded_fast_checks'):
                expanded_validation = json.loads((audit/'expanded-validation.json').read_text())
                if (not expanded_validation.get('passed') or
                        expanded_validation['expanded_policy_identity'] != expanded.identity() or
                        expanded_validation['metadata_sha256'] != sha(audit/'image-categories.json')):
                    raise ValueError('Expanded fast checks are missing validation or changed')
            measure_missing(job, audit, db)
            fast_pass(audit, db)
            if config.get('dark_fast_checks') or config.get('native_fast_holds') or config.get('combined_reviews'):
                with (audit/'export.lock').open('a') as export_lock:
                    fcntl.flock(export_lock,fcntl.LOCK_EX)
                    register_speedup(db,audit)
                    speedup_fast_pass(job,audit,db)
            if not (audit / 'selections/early/verification.json').exists():
                progress(audit, db, 'verifying_majority_white_selection')
                export_selection(job, audit, 'early')
            reviewer_validation = audit / 'reviewer-validation.json'
            while not reviewer_validation.exists():
                progress(audit, db, 'waiting_for_context_review_validation')
                time.sleep(30)
            reviewed = json.loads(reviewer_validation.read_text())
            if (not reviewed.get('passed') or reviewed['policy_identity'] != policy.identity() or
                    reviewed['context_identity'] != context_identity(audit)):
                raise ValueError('Context reviewer validation failed or changed')
            while db.execute('SELECT 1 FROM images WHERE decision IS NULL LIMIT 1').fetchone():
                try: review_pending(job, audit, db)
                except ReviewServiceUnavailable:
                    progress(audit, db, 'waiting_for_review_service', error='Local review service unavailable; verified selection remains available.')
                    time.sleep(60)
            export_selection(job, audit, 'final')
            progress(audit, db, 'complete')
        except BaseException as error:
            progress(audit, db, 'needs_attention', error=str(error)); raise
        finally: db.close()


def alive(pid):
    if not pid: return False
    try: os.kill(pid, 0); return True
    except ProcessLookupError: return False
    except PermissionError: return True


def spawn(audit, arguments, log_name):
    config = json.loads((audit / 'config.json').read_text())
    command = ['/usr/bin/caffeinate', '-i', config['python'], '-B', str(Path(__file__).resolve()), *arguments,
               '--job', config['job'], '--audit', str(audit)]
    with (audit / log_name).open('a') as stream:
        proc = subprocess.Popen(command, cwd=config['job'], stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
            start_new_session=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'VECLIB_MAXIMUM_THREADS': '1'})
    return {'pid': proc.pid, 'arguments': command, 'started_at': time.time()}


def guard(job, audit):
    with (audit / 'guard.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        state = json.loads((audit / 'status.json').read_text()) if (audit / 'status.json').exists() else {}
        if state.get('phase') in ('complete', 'needs_attention'): return
        qualification = audit / 'pilot-validation.json'
        if not qualification.exists() or not json.loads(qualification.read_text()).get('passed'):
            print('Waiting for category pilot qualification.'); return
        process = json.loads((audit / 'controller-process.json').read_text()) if (audit / 'controller-process.json').exists() else {}
        if alive(process.get('pid')):
            print('Category controller is running.'); return
        write(audit / 'controller-process.json', spawn(audit, ['run'], 'controller.log'))


def maybe_deadline_export(audit):
    config = json.loads((audit / 'config.json').read_text())
    if time.time() < config['freeze_at']: return
    report = audit / 'selections/deadline/verification.json'
    if report.exists() and json.loads(report.read_text()).get('category_policy_verified'): return
    status = audit / 'export-status.json'
    if status.exists() and json.loads(status.read_text()).get('state') == 'needs_attention': return
    with (audit / 'export-schedule.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        receipt = audit / 'export-process.json'
        old = json.loads(receipt.read_text()) if receipt.exists() else {}
        if alive(old.get('pid')): return
        write(receipt, spawn(audit, ['export', '--slot', 'deadline'], 'export.log'))


def notify(message):
    script = 'display notification ' + json.dumps(message) + ' with title "Catalog white JPGs"'
    result = subprocess.run(['/usr/bin/osascript', '-e', script], capture_output=True, text=True, timeout=15)
    return {'returncode': result.returncode}


def monitor(job, audit, do_notify=True):
    maybe_deadline_export(audit)
    config = json.loads((audit / 'config.json').read_text())
    state = json.loads((audit / 'status.json').read_text()) if (audit / 'status.json').exists() else {}
    export_state = json.loads((audit / 'export-status.json').read_text()) if (audit / 'export-status.json').exists() else {}
    if export_state.get('state') == 'needs_attention':
        state['error'] = 'Export: ' + export_state['error']
    latest = json.loads((audit / 'latest.json').read_text()) if (audit / 'latest.json').exists() else None
    counts = state.get('decisions', {}); white = counts.get('white', 0) + 2
    date = lambda v: datetime.fromtimestamp(v, ZoneInfo('America/Indiana/Indianapolis')).strftime('%b %d, %I:%M %p %Z')
    h = lambda v: escape(str(v), quote=True)
    html = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="60"><title>Catalog white backgrounds</title><style>body{font:17px/1.6 system-ui;max-width:1100px;margin:32px auto;padding:0 24px;color:#18202b;background:#f4f6f7}section{background:white;border-radius:12px;padding:24px;margin:20px 0}img{width:46%;object-fit:contain;max-height:500px}pre{white-space:pre-wrap}a{color:#165baf}</style><h1>Catalog white backgrounds</h1>'
    html += '<section><h2>White backgrounds for tonight</h2><p><strong>' + h(f'{white:,} / 95,401 ({white/95401:.1%})') + '</strong> approved white images, including two mirror replacements. ' + h(f'{95401-white:,}') + ' would use originals at the current checkpoint.</p>'
    html += '<p>Keep all <strong>50 Room Bundle images</strong> original. Review Bedding Sets, non-uniform backgrounds and substantial cutout risks. Other images use fast native pixel checks. Minor cutout changes are accepted.</p>'
    if config.get('expanded_fast_checks'):
        html += '<p><strong>Expanded fast checks active:</strong> local edge and surface changes may pass after extra source-material loss checks. Likely scenes, large erased surfaces and major structure changes remain in slow review.</p>'
    html += '<p>Current phase: <strong>' + h(state.get('phase', 'starting').replace('_', ' ')) + '</strong>. Review cutoff: ' + h(date(config['freeze_at'])) + '; delivery deadline: ' + h(date(config['deadline_at'])) + '.</p><pre>' + h(json.dumps({'decisions': counts, 'methods': state.get('methods', {}), 'individual_reviews': state.get('individual_reviews', 0)}, indent=2)) + '</pre>'
    if state.get('error'): html += '<p><strong>Needs attention:</strong> ' + h(state['error']) + '</p>'
    html += '<p>Updated ' + h(date(state.get('updated_at', time.time()))) + '. Automated checks run every five minutes; this page reloads every minute.</p></section>'
    html += '<section><h2>Verified launch selection</h2>'
    if latest:
        html += '<p>Verified ' + h(date(latest['verified_at'])) + ' (' + h(latest['slot']) + '). Every original and selected image hash and all media CSV references were checked.</p><pre>' + h(json.dumps(latest['counts'], indent=2)) + '</pre>'
        for key, label in [('media_csv', 'Media import CSV'), ('media', 'Selected image folder'), ('verification', 'Verification report'), ('selection_csv', 'Image selection CSV')]:
            html += '<a href="' + h(Path(latest[key]).as_uri()) + '">' + label + '</a> | '
        html += '<p>' + h(latest['pending_reviews_kept_original']) + ' pending reviews used originals in this snapshot. The deadline refresh includes subsequent approvals.</p>'
    else: html += '<p>Applying fast checks and verifying the first selection.</p>'
    html += '<p>Originals remain intact. Import and publication have not been performed.</p></section>'
    if (audit / 'pilot-validation.json').exists(): html += '<section><h2>Validation</h2><p><a href="' + h((audit/'pilot-validation.json').as_uri()) + '">Category pilot results</a> | <a href="' + h((audit/'authorization.json').as_uri()) + '">Approved rules</a></p></section>'
    try:
        db = sqlite3.connect((audit / 'audit.sqlite3').as_uri() + '?mode=ro', uri=True)
        samples = []
        for decision in ('white', 'original'):
            samples += db.execute('SELECT i.row_json,i.decision,i.reason,e.method,e.review FROM images i JOIN category_evidence e ON i.file=e.file WHERE i.decision=? ORDER BY e.decided_at DESC LIMIT 4', (decision,)).fetchall()
        db.close()
        if samples:
            original_root = Path(json.loads((job/'manifest.json').read_text())['originals'])
            html += '<section><h2>Latest comparisons</h2><p>Original left; white candidate right.</p>'
            for encoded, decision, reason, method, encoded_review in samples:
                row = json.loads(encoded)
                if not row.get('output_file'): continue
                candidate = Path(row.get('output_path') or job/'media/wands-expanded'/row['output_file'])
                review = json.loads(encoded_review) if encoded_review else None
                text = review['reason'] if review else reason.replace('_', ' ')
                html += '<article><p><strong>' + ('Use white JPG' if decision == 'white' else 'Keep original') + '</strong>: ' + h(text) + ' (' + h(method) + ')</p><img src="' + h((original_root/row['file']).as_uri()) + '" alt="Original"><img src="' + h(candidate.as_uri()) + '" alt="White candidate"><p><small>' + h(row['file']) + '</small></p></article>'
            html += '</section>'
    except sqlite3.OperationalError: pass
    html += '</html>'
    temp = job / 'status.category.tmp'; temp.write_text(html); os.replace(temp, job/'status.html')
    event = 'needs_attention' if state.get('phase') == 'needs_attention' or export_state.get('state') == 'needs_attention' else ('verified_' + latest['slot']) if latest else None
    marker = audit / 'notification.json'; previous = json.loads(marker.read_text()) if marker.exists() else {}
    if do_notify and event and event != previous.get('event'):
        message = 'Catalog selection needs attention: ' + str(state.get('error', ''))[:150] if event == 'needs_attention' else f"Verified launch images ready: {latest['counts']['white_reused']+latest['counts']['white_new']+2:,} white backgrounds."
        write(marker, {'event': event, 'at': time.time(), 'notification': notify(message)})
    print(json.dumps({'phase': state.get('phase'), 'approved_white': white, 'original_if_launched_now': 95401-white, 'decisions': counts, 'verified_selection': latest['counts'] if latest else None, 'error': state.get('error')}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run', 'export', 'monitor', 'guard'])
    parser.add_argument('--job', required=True, type=Path); parser.add_argument('--audit', required=True, type=Path)
    parser.add_argument('--slot', choices=['early', 'deadline', 'final']); parser.add_argument('--no-notify', action='store_true')
    args = parser.parse_args(); job, audit = args.job.resolve(), args.audit.resolve()
    if not audit.is_relative_to(job): raise ValueError('Audit must be within its job')
    if args.command == 'run':
        native(audit)
        run(job, audit)
    elif args.command == 'export':
        if not args.slot: parser.error('export requires --slot')
        try: export_selection(job, audit, args.slot)
        except BaseException as error:
            write(audit/'export-status.json', {'state': 'needs_attention', 'error': str(error), 'slot': args.slot, 'updated_at': time.time()}); raise
    elif args.command == 'guard': guard(job, audit)
    else: monitor(job, audit, not args.no_notify)


if __name__ == '__main__': main()
