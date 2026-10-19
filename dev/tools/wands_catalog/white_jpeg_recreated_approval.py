"""Supersede exact original directives with explicitly approved recreated JPGs."""
import json
from pathlib import Path
import time

import white_jpeg_human_approval as human


def make_plan(manifest_path, expected_sha, scope, db):
    manifest_path = Path(manifest_path)
    if human.sha(manifest_path) != expected_sha or scope['manifest_sha256'] != expected_sha:
        raise ValueError('Review manifest hash mismatch')
    manifest = json.loads(manifest_path.read_text())
    if manifest['run_id'] != scope['run_id'] or scope.get('deploy') is not False:
        raise ValueError('Approval run or deployment scope mismatch')
    if manifest['state'] not in ('ready_for_review', 'ready_for_review_with_exceptions'):
        raise ValueError('Generation must finish before approval')
    by_id = {i['id']: i for i in manifest['items']}
    batches = {i['batch'] for i in manifest['items']}
    approved = scope['approved_batches_with_exceptions']
    if len(by_id) != len(manifest['items']) or set(approved) - batches:
        raise ValueError('Unknown or duplicated review IDs')
    for batch, exceptions in approved.items():
        if len(exceptions) != len(set(exceptions)) or any(
            i not in by_id or by_id[i]['batch'] != batch for i in exceptions
        ):
            raise ValueError('Exception is not in its approved batch')
    items = []
    for image in manifest['items']:
        if image['batch'] not in approved:
            continue
        original = Path(image['original_path'])
        prior = human.directive(db, original.name)
        record = db.execute('SELECT row_json,decision,reason FROM images WHERE file=?', (original.name,)).fetchone()
        if prior is None or record is None or prior['decision'] != 'original' or record[1] != 'original':
            raise ValueError('Recreation must supersede an existing original directive')
        if prior['item_id'] != image['previous_review_id'] or prior['source_sha256'] != image['source_sha256']:
            raise ValueError('Prior review identity changed')
        row = json.loads(record[0])
        if (row['source_sha256'], row.get('output_sha256')) != (prior['source_sha256'], prior['output_sha256']):
            raise ValueError('Prior audit image identity changed')
        keep = image['id'] in approved[image['batch']]
        if keep:
            candidate = Path(row.get('output_path') or image['rejected_url'].removeprefix('file://'))
            output_sha = prior['output_sha256']
        else:
            if image['state'] != 'awaiting_review' or not image['replacement_path'] or not image['replacement_sha256']:
                raise ValueError('Unavailable replacement must remain an exception')
            candidate = Path(image['replacement_path'])
            output_sha = image['replacement_sha256']
        if human.sha(original) != image['source_sha256'] or human.sha(candidate) != output_sha:
            raise ValueError('Reviewed image bytes changed')
        items.append({'id': image['id'], 'batch': image['batch'], 'file': original.name,
                      'source_sha256': image['source_sha256'], 'output_sha256': output_sha,
                      'original_path': str(original), 'candidate_path': str(candidate),
                      'name': image['name'], 'skus': image['skus'],
                      'decision': 'original' if keep else 'white',
                      'prior_directive': prior,
                      'before': {'row_json': record[0], 'decision': record[1], 'reason': record[2]}})
    if len({i['file'] for i in items}) != len(items):
        raise ValueError('Same source appears more than once')
    return {'schema': 1, 'kind': 'explicit_human_furniture_approval',
            'approval_type': 'recreated_images_superseding_originals',
            'manifest_sha256': expected_sha, 'manifest_path': str(manifest_path.resolve()),
            'scope': scope, 'items': items, 'created_at': time.time()}


def selected_row(item):
    row = json.loads(item['before']['row_json'])
    if item['decision'] == 'white':
        row.update(output_file=item['output_sha256'] + '.jpg', output_sha256=item['output_sha256'],
                   output_path=item['candidate_path'], output_bytes=Path(item['candidate_path']).stat().st_size,
                   warning=None, state='done', audit_new_conversion=True,
                   human_recreated_review_id=item['id'])
    return json.dumps(row) if item['decision'] == 'white' else item['before']['row_json']


def verify(db, plan):
    counts = human.verify(db, plan)
    for item in plan['items']:
        directive = human.directive(db, item['file'])
        row = db.execute('SELECT row_json FROM images WHERE file=?', (item['file'],)).fetchone()[0]
        if row != selected_row(item) or any(directive[k] != item[k] for k in ('source_sha256', 'output_sha256', 'batch')) or directive['item_id'] != item['id']:
            raise ValueError('Recreated selection identity changed')
    return counts


def apply(db, plan, metadata):
    """Caller holds export.lock and keeps a current SQLite backup."""
    if plan.get('approval_type') != 'recreated_images_superseding_originals' or plan['scope'].get('deploy') is not False:
        raise ValueError('Invalid recreation approval scope')
    text, plan_sha = human.encode_plan(plan)
    if human.sha(plan['manifest_path']) != plan['manifest_sha256']:
        raise ValueError('Review manifest hash mismatch')
    db.execute('BEGIN IMMEDIATE')
    try:
        prior_request = db.execute('SELECT plan_json FROM human_approval_requests WHERE plan_sha256=?', (plan_sha,)).fetchone()
        if prior_request:
            if prior_request[0] != text:
                raise ValueError('Approval identity collision')
            verify(db, plan)
            db.rollback()
            return {'plan_sha256': plan_sha, 'idempotent': True}
        for item in plan['items']:
            old = db.execute('SELECT row_json,decision,reason FROM images WHERE file=?', (item['file'],)).fetchone()
            if human.directive(db, item['file']) != item['prior_directive'] or tuple(old or ()) != tuple(item['before'][k] for k in ('row_json', 'decision', 'reason')):
                raise ValueError('Prior selection changed before supersession')
            if human.sha(item['original_path']) != item['source_sha256'] or human.sha(item['candidate_path']) != item['output_sha256']:
                raise ValueError('Reviewed image bytes changed')
            meta = metadata[item['file']]
            if item['decision'] == 'white':
                if 'Room Bundle' in meta.get('classes', []) or any('/Room Bundles/' in c for c in meta.get('categories', [])):
                    raise ValueError('Room Bundle excluded')
                if db.execute("SELECT 1 FROM glass_outline_checks WHERE file=? AND verdict!='preserved'", (item['file'],)).fetchone():
                    raise ValueError('Held glass outline excluded')
        db.execute('INSERT INTO human_approval_requests VALUES(?,?,?)', (plan_sha, text, time.time()))
        for item in plan['items']:
            db.execute('UPDATE human_selections SET decision=?,source_sha256=?,output_sha256=?,item_id=?,batch=?,plan_sha256=? WHERE file=?',
                       (item['decision'], item['source_sha256'], item['output_sha256'], item['id'], item['batch'], plan_sha, item['file']))
            db.execute('UPDATE images SET row_json=?,decision=?,reason=? WHERE file=?',
                       (selected_row(item), item['decision'], human.WHITE_REASON if item['decision'] == 'white' else human.ORIGINAL_REASON, item['file']))
        verify(db, plan)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return {'plan_sha256': plan_sha, 'idempotent': False}


def rollback(db, plan):
    """Restore only these prior directives and image rows; preserve request history."""
    db.execute('BEGIN IMMEDIATE')
    try:
        verify(db, plan)
        for item in plan['items']:
            p = item['prior_directive'];old = item['before']
            db.execute('UPDATE human_selections SET decision=?,source_sha256=?,output_sha256=?,item_id=?,batch=?,plan_sha256=? WHERE file=?',
                       (p['decision'], p['source_sha256'], p['output_sha256'], p['item_id'], p['batch'], p['plan_sha256'], p['file']))
            db.execute('UPDATE images SET row_json=?,decision=?,reason=? WHERE file=?',
                       (old['row_json'], old['decision'], old['reason'], item['file']))
        db.commit()
    except BaseException:
        db.rollback()
        raise
