"""Hash-bound human selections, kept separate from automatic review evidence."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import time


WHITE_REASON = 'human_spotcheck_batch_approved'
ORIGINAL_REASON = 'human_spotcheck_exception_keep_original'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def table_exists(db, table):
    return bool(db.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?', ('table', table)).fetchone())


def install(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS human_approval_requests(
        plan_sha256 TEXT PRIMARY KEY, plan_json TEXT NOT NULL, applied_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS human_selections(
        file TEXT PRIMARY KEY, decision TEXT NOT NULL CHECK(decision IN ('white','original')),
        source_sha256 TEXT NOT NULL, output_sha256 TEXT NOT NULL,
        item_id TEXT NOT NULL, batch TEXT NOT NULL, plan_sha256 TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS human_request_immutable_update BEFORE UPDATE ON human_approval_requests
        BEGIN SELECT RAISE(ABORT,'Human approval requests are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS human_request_immutable_delete BEFORE DELETE ON human_approval_requests
        BEGIN SELECT RAISE(ABORT,'Human approval requests are immutable'); END;
    ''')
    # The automatic workers may have queued these rows before human approval.
    # Their evidence may finish, but the human directive owns the selection.
    db.executescript('''CREATE TRIGGER IF NOT EXISTS preserve_human_selection
        AFTER UPDATE OF decision,reason,row_json ON images
        WHEN EXISTS(SELECT 1 FROM human_selections h WHERE h.file=NEW.file)
        BEGIN
            UPDATE images SET
                decision=CASE
                    WHEN json_extract(row_json,'$.source_sha256')!=(SELECT source_sha256 FROM human_selections WHERE file=NEW.file)
                      OR json_extract(row_json,'$.output_sha256')!=(SELECT output_sha256 FROM human_selections WHERE file=NEW.file)
                      OR EXISTS(SELECT 1 FROM glass_outline_checks g WHERE g.file=NEW.file AND g.verdict!='preserved')
                    THEN 'original' ELSE (SELECT decision FROM human_selections WHERE file=NEW.file) END,
                reason=CASE
                    WHEN json_extract(row_json,'$.source_sha256')!=(SELECT source_sha256 FROM human_selections WHERE file=NEW.file)
                      OR json_extract(row_json,'$.output_sha256')!=(SELECT output_sha256 FROM human_selections WHERE file=NEW.file)
                    THEN 'human_approval_bytes_changed_keep_original'
                    WHEN EXISTS(SELECT 1 FROM glass_outline_checks g WHERE g.file=NEW.file AND g.verdict!='preserved')
                    THEN 'glass_outline_missing_or_uncertain_keep_original'
                    WHEN (SELECT decision FROM human_selections WHERE file=NEW.file)='white'
                    THEN 'human_spotcheck_batch_approved' ELSE 'human_spotcheck_exception_keep_original' END
                WHERE file=NEW.file;
        END;''')


def directive(db, filename):
    if not table_exists(db, 'human_selections'):
        return None
    row = db.execute('SELECT file,decision,source_sha256,output_sha256,item_id,batch,plan_sha256 '
                     'FROM human_selections WHERE file=?', (filename,)).fetchone()
    return dict(zip(('file','decision','source_sha256','output_sha256','item_id','batch','plan_sha256'), row)) if row else None


def methods(db):
    if not table_exists(db,'human_selections'):
        return dict(db.execute('SELECT method,count(*) FROM category_evidence GROUP BY method'))
    counts=dict(db.execute('SELECT e.method,count(*) FROM category_evidence e LEFT JOIN human_selections h '
                          'USING(file) WHERE h.file IS NULL GROUP BY e.method'))
    counts.update({'human_spotcheck_'+decision:count for decision,count in
                   db.execute('SELECT decision,count(*) FROM human_selections GROUP BY decision')})
    return counts


def make_plan(manifest_path, expected_manifest_sha, scope):
    manifest_path = Path(manifest_path)
    if sha(manifest_path) != expected_manifest_sha or scope['manifest_sha256'] != expected_manifest_sha:
        raise ValueError('Review manifest hash mismatch')
    manifest = json.loads(manifest_path.read_text())
    if scope['run_id'] != manifest['run_id'] or scope.get('deploy') is not False:
        raise ValueError('Approval run or deployment scope mismatch')
    approved = scope['approved_batches_with_exceptions']
    batches = {b['id']: b for b in manifest['batches']}
    by_id = {i['id']: i for i in manifest['items']}
    if len(by_id) != len(manifest['items']) or set(approved) - set(batches):
        raise ValueError('Unknown or duplicated approval IDs')
    items = []
    for batch_id, exceptions in approved.items():
        if len(set(exceptions)) != len(exceptions) or set(exceptions) - set(batches[batch_id]['items']):
            raise ValueError('Exception is not in its approved batch')
        for item_id in batches[batch_id]['items']:
            item = by_id[item_id]
            if item['batch'] != batch_id:
                raise ValueError('Batch membership mismatch')
            if sha(item['original_path']) != item['source_sha256'] or sha(item['candidate_path']) != item['output_sha256']:
                raise ValueError('Reviewed image bytes changed: '+item_id)
            items.append({k:item[k] for k in ('id','batch','file','source_sha256','output_sha256','original_path','candidate_path','name','skus')}
                         | {'decision':'original' if item_id in exceptions else 'white'})
    if len({i['file'] for i in items}) != len(items):
        raise ValueError('Same source appears more than once')
    return {'schema':1,'kind':'explicit_human_furniture_approval','manifest_sha256':expected_manifest_sha,
            'manifest_path':str(manifest_path.resolve()),'scope':scope,'items':items,
            'omitted_batches':sorted(set(batches)-set(approved)),
            'omitted_images':len(manifest['items'])-len(items),'created_at':time.time()}


def encode_plan(plan):
    text = json.dumps(plan, sort_keys=True, separators=(',',':'))
    return text, hashlib.sha256(text.encode()).hexdigest()


@lru_cache(maxsize=16)
def checked_plan(text, expected_sha):
    if hashlib.sha256(text.encode()).hexdigest() != expected_sha:
        raise ValueError('Human approval request hash mismatch')
    plan = json.loads(text)
    if plan['kind'] != 'explicit_human_furniture_approval' or plan['scope']['deploy'] is not False:
        raise ValueError('Invalid human approval request')
    return {i['file']:i for i in plan['items']}


def validate_white(db, row, meta):
    """Return False for automatic rows; raise on any invalid human selection."""
    h = directive(db,row['file'])
    if h is None:
        return False
    request = db.execute('SELECT plan_json FROM human_approval_requests WHERE plan_sha256=?', (h['plan_sha256'],)).fetchone()
    if request is None:
        raise ValueError('Human selection has no approval request')
    item = checked_plan(request[0],h['plan_sha256']).get(row['file'])
    if item is None or any(h[k] != item[k] for k in ('decision','source_sha256','output_sha256','batch')) or h['item_id'] != item['id']:
        raise ValueError('Human selection differs from the approved request')
    if h['decision'] != 'white':
        raise ValueError('Human exception must stay original')
    if (row['source_sha256'],row.get('output_sha256')) != (h['source_sha256'],h['output_sha256']):
        raise ValueError('Human approval belongs to different image bytes')
    if 'Room Bundle' in meta.get('classes',[]) or any('/Room Bundles/' in c for c in meta.get('categories',[])):
        raise ValueError('Room Bundle cannot select processed media')
    if table_exists(db,'glass_outline_checks') and db.execute("SELECT 1 FROM glass_outline_checks WHERE file=? AND verdict!='preserved'", (row['file'],)).fetchone():
        raise ValueError('Human selection cannot bypass a held glass outline')
    return True


def apply(db, plan, metadata):
    """Caller holds export.lock and retains a SQLite backup before calling."""
    text, plan_sha = encode_plan(plan)
    install(db)
    before = []
    db.execute('BEGIN IMMEDIATE')
    try:
        prior = db.execute('SELECT plan_json FROM human_approval_requests WHERE plan_sha256=?',(plan_sha,)).fetchone()
        if prior:
            if prior[0] != text:
                raise ValueError('Human approval identity collision')
            verify(db,plan)
            db.rollback()
            return {'plan_sha256':plan_sha,'idempotent':True,'before':[]}
        for item in plan['items']:
            record = db.execute('SELECT row_json,decision,reason FROM images WHERE file=?',(item['file'],)).fetchone()
            if record is None or directive(db,item['file']) is not None:
                raise ValueError('Missing source or existing human directive: '+item['id'])
            row=json.loads(record[0])
            if (row['source_sha256'],row.get('output_sha256')) != (item['source_sha256'],item['output_sha256']):
                raise ValueError('Audit image identity changed: '+item['id'])
            if sha(item['original_path']) != item['source_sha256'] or sha(item['candidate_path']) != item['output_sha256']:
                raise ValueError('Reviewed image bytes changed: '+item['id'])
            meta=metadata[item['file']]
            if item['decision']=='white':
                if 'Room Bundle' in meta.get('classes',[]) or any('/Room Bundles/' in c for c in meta.get('categories',[])):
                    raise ValueError('Room Bundle excluded')
                if db.execute("SELECT 1 FROM glass_outline_checks WHERE file=? AND verdict!='preserved'",(item['file'],)).fetchone():
                    raise ValueError('Held glass outline excluded')
            before.append({'file':item['file'],'decision':record[1],'reason':record[2]})
        db.execute('INSERT INTO human_approval_requests VALUES(?,?,?)',(plan_sha,text,time.time()))
        for item in plan['items']:
            db.execute('INSERT INTO human_selections VALUES(?,?,?,?,?,?,?)',(item['file'],item['decision'],item['source_sha256'],item['output_sha256'],item['id'],item['batch'],plan_sha))
            db.execute('UPDATE images SET decision=?,reason=? WHERE file=?',(item['decision'],WHITE_REASON if item['decision']=='white' else ORIGINAL_REASON,item['file']))
        verify(db,plan)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return {'plan_sha256':plan_sha,'idempotent':False,'before':before}


def verify(db, plan):
    _,plan_sha=encode_plan(plan)
    for item in plan['items']:
        h=directive(db,item['file'])
        selected=db.execute('SELECT decision FROM images WHERE file=?',(item['file'],)).fetchone()
        if h is None or h['plan_sha256']!=plan_sha or h['decision']!=item['decision'] or selected[0]!=item['decision']:
            raise ValueError('Human selection verification failed: '+item['id'])
    return {'white':sum(i['decision']=='white'for i in plan['items']),
            'original':sum(i['decision']=='original'for i in plan['items'])}


def rollback(db, plan, before):
    """Guarded inverse for this approval only. Immutable request stays as history."""
    _,plan_sha=encode_plan(plan)
    db.execute('BEGIN IMMEDIATE')
    try:
        verify(db,plan)
        if {r['file']for r in before}!={i['file']for i in plan['items']}:
            raise ValueError('Incomplete rollback inventory')
        db.execute('DELETE FROM human_selections WHERE plan_sha256=?',(plan_sha,))
        for row in before:
            db.execute('UPDATE images SET decision=?,reason=? WHERE file=?',(row['decision'],row['reason'],row['file']))
        db.commit()
    except BaseException:
        db.rollback()
        raise
