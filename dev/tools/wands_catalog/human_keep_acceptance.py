"""Reconcile exact human Keeps without changing images or weakening annotation gates."""
from contextlib import closing, ExitStack
import json
from pathlib import Path
import re
import sqlite3
import shutil
import time

from build_expanded_catalog import canonical, digest
from prepare_catalog import sha256


def is_kept(run, row):
    """Protect the exact image in the current live Keep, even before reconciliation."""
    row=dict(row)
    if not row.get('image_sha256'):return False
    path=Path(run).parent/'human-image-review/feedback.sqlite'
    if not path.is_file():return False
    receipt=json.loads(row.get('review') or '{}').get('human_keep',{})
    pin=receipt.get('annotation_cleanup',{}).get('original_sha256',row['image_sha256'])
    with closing(sqlite3.connect(f'file:{path.resolve()}?mode=ro',uri=True)) as db:
        return bool(db.execute("SELECT 1 FROM items i JOIN decisions d ON d.item_id=i.id "
            "WHERE d.choice='keep' AND json_extract(i.payload,'$.job_id')=? "
            "AND json_extract(i.payload,'$.image_sha256')=? LIMIT 1",
            (row['job_id'],pin)).fetchone())


def annotation_clear(review, resolution=None):
    if resolution:
        return bool(resolution.get('image_sha256')==review.get('image_sha256')
                    and resolution.get('decision')=='no_visible_annotations'
                    and resolution.get('reviewer')=='direct_visual_inspection'
                    and resolution.get('observations','').strip())
    vision=review.get('vision',{});ocr=review.get('ocr',{})
    return (ocr.get('status')=='ok' and not review.get('ocr_flags')
            and not any(o.get('confidence',1)>=.3 and re.search('[A-Za-z0-9]',o.get('text','')) for o in ocr.get('observations',[]))
            and vision.get('visible_text') is False and vision.get('visible_measurements') is False)


def valid(row, review, identity):
    receipt=review.get('human_keep')
    if not receipt or digest(receipt)!=review.get('human_keep_sha256'):return False
    original=receipt.get('original_review',{})
    annotations=original;feedback_pin=row['image_sha256']
    cleanup=receipt.get('annotation_cleanup')
    if cleanup:
        comparison=cleanup.get('comparison',{});annotations=cleanup.get('review',{})
        feedback_pin=cleanup.get('original_sha256')
        if (original.get('image_sha256')!=feedback_pin or cleanup.get('image_sha256')!=row['image_sha256']
                or annotations.get('image_sha256')!=row['image_sha256']
                or annotations.get('design_sha256')!=original.get('design_sha256')
                or annotations.get('review_identity')!=identity
                or comparison.get('original_sha256')!=feedback_pin or comparison.get('image_sha256')!=row['image_sha256']
                or comparison.get('reviewer')!='direct_visual_inspection'
                or comparison.get('decision')!='only_annotations_removed' or not comparison.get('observations','').strip()):return False
        try:
            if sha256(Path(cleanup['original_path']))!=feedback_pin:return False
        except (OSError,KeyError):return False
    if (receipt.get('job_id')!=row['job_id'] or receipt.get('image_sha256')!=row['image_sha256']
            or receipt.get('request_sha256')!=digest(json.loads(row['request']))
            or receipt.get('review_identity')!=identity or original.get('review_identity')!=identity
            or original.get('image_sha256')!=feedback_pin
            or original.get('design_sha256')!=review.get('design_sha256')
            or not annotation_clear(annotations,receipt.get('annotation_resolution'))):return False
    try:
        with closing(sqlite3.connect(f"file:{Path(receipt['feedback_path']).resolve()}?mode=ro",uri=True)) as db:
            decision=db.execute('SELECT i.payload,d.choice,d.revision FROM items i JOIN decisions d ON d.item_id=i.id WHERE i.id=?',(receipt['item_id'],)).fetchone()
        if not decision:return False
        item=json.loads(decision[0])
        return (decision[1]=='keep' and decision[2]==receipt['revision']
                and item.get('job_id')==row['job_id'] and item.get('image_sha256')==feedback_pin)
    except (sqlite3.Error,KeyError,ValueError,TypeError):return False


def prepare(run, resolutions=None):
    from bulk_expansion_images import connect, descriptor, accepted_reference
    from feedback_reprocessing import feedback_rows
    run=Path(run).resolve();desc=descriptor(run);db=connect(run)
    feedback=run.parent/'human-image-review/feedback.sqlite';entries=[];held=[]
    resolutions=resolutions or {}
    try:
        for decision in feedback_rows(feedback):
            if decision['choice']!='keep':continue
            item=decision['item'];row=db.execute('SELECT * FROM jobs WHERE job_id=?',(item['job_id'],)).fetchone()
            if row is None or row['state']=='accepted':continue
            if (row['state'] not in {'rejected','review_required'} or row['image_sha256']!=item['image_sha256']
                    or sha256(Path(row['image_path']))!=row['image_sha256']):
                held.append({'job_id':item['job_id'],'reason':'stale image or state'});continue
            review=json.loads(row['review']);job=json.loads(row['request']);resolution=resolutions.get(row['job_id'])
            if not annotation_clear(review,resolution):
                held.append({'job_id':row['job_id'],'reason':'annotation review required'});continue
            source=accepted_reference(db,job,desc['review_identity'])
            if source is False or (source and sha256(source)!=review.get('reference_sha256')):
                held.append({'job_id':row['job_id'],'reason':'source changed or unavailable'});continue
            receipt={'feedback_path':str(feedback),'item_id':decision['id'],'revision':decision['revision'],
                     'job_id':row['job_id'],'image_sha256':row['image_sha256'],'request_sha256':digest(job),
                     'review_identity':desc['review_identity'],'original_review':review,'annotation_resolution':resolution}
            after={**review,'decision':'accepted','acceptance_basis':'human_keep',
                   'human_keep':receipt,'human_keep_sha256':digest(receipt)}
            if not valid(row,after,desc['review_identity']):raise ValueError('Stale human Keep evidence')
            entries.append({'job_id':row['job_id'],'before_state':row['state'],'before_review':row['review'],
                            'image_sha256':row['image_sha256'],'request_sha256':digest(job),'after_review':after})
        return {'run_sha256':sha256(run/'run.json'),'prepared_at':time.time(),'entries':entries,'held':held}
    finally:db.close()


def apply(run, manifest):
    from bulk_expansion_images import connect, descriptor, lock, atomic_json, accepted_reference
    run=Path(run).resolve();manifest=Path(manifest).resolve();plan=json.loads(manifest.read_text());desc=descriptor(run)
    if plan['run_sha256']!=sha256(run/'run.json'):raise ValueError('Wrong run')
    destination=run/'human-keep-acceptance'/sha256(manifest)[:16]
    with ExitStack() as locks:
        for name in ('supervisor','generation','review','reference-review','reference-repair-review'):locks.enter_context(lock(run,name))
        db=connect(run)
        try:
            if destination.exists():raise ValueError('Keep reconciliation already applied')
            for entry in plan['entries']:
                row=db.execute('SELECT * FROM jobs WHERE job_id=?',(entry['job_id'],)).fetchone()
                if (row['state']!=entry['before_state'] or row['review']!=entry['before_review']
                        or sha256(Path(row['image_path']))!=entry['image_sha256']
                        or digest(json.loads(row['request']))!=entry['request_sha256']
                        or not valid(row,entry['after_review'],desc['review_identity'])):
                    raise ValueError('Keep reconciliation changed before apply')
                source=accepted_reference(db,json.loads(row['request']),desc['review_identity'])
                if source is False or (source and sha256(source)!=entry['after_review'].get('reference_sha256')):
                    raise ValueError('Keep source changed before apply')
            destination.mkdir(parents=True)
            with closing(sqlite3.connect(destination/'ledger-before.sqlite')) as backup:db.backup(backup)
            atomic_json(destination/'manifest.json',plan)
            with db:
                for entry in plan['entries']:
                    db.execute("UPDATE jobs SET state='accepted',review=?,error=NULL,updated=? WHERE job_id=?",
                               (canonical(entry['after_review']),time.time(),entry['job_id']))
            receipt={'accepted':len(plan['entries']),'held':len(plan['held']),'image_bytes_changed':0,
                     'manifest_sha256':sha256(manifest),'backup':str(destination/'ledger-before.sqlite')}
            atomic_json(destination/'receipt.json',receipt);return receipt
        finally:db.close()


def prepare_cleanups(run, comparisons):
    """Bind annotation-only derivatives to the original live Keep and paired review."""
    from bulk_expansion_images import connect,descriptor
    from feedback_reprocessing import feedback_rows
    run=Path(run).resolve();desc=descriptor(run);db=connect(run)
    feedback=run.parent/'human-image-review/feedback.sqlite'
    decisions={r['item']['job_id']:r for r in feedback_rows(feedback)};entries=[]
    try:
        for metadata_path,comparison in comparisons:
            metadata_path=Path(metadata_path);metadata=json.loads(metadata_path.read_text())
            staged=Path(metadata['image_path']);review=json.loads(staged.with_suffix('.review.json').read_text())
            row=db.execute('SELECT * FROM jobs WHERE job_id=?',(metadata['job_id'],)).fetchone();human=decisions.get(metadata['job_id'])
            if (row is None or row['state'] not in {'rejected','review_required'} or not human or human['choice']!='keep'
                    or human['item']['image_sha256']!=row['image_sha256']
                    or metadata['original_sha256']!=row['image_sha256']
                    or sha256(Path(row['image_path']))!=row['image_sha256']
                    or sha256(staged)!=metadata['image_sha256'] or not annotation_clear(review)):
                raise ValueError('Cleanup lacks current Keep or clear annotation review')
            receipt={'feedback_path':str(feedback),'item_id':human['id'],'revision':human['revision'],
                'job_id':row['job_id'],'image_sha256':metadata['image_sha256'],
                'request_sha256':digest(json.loads(row['request'])),'review_identity':desc['review_identity'],
                'original_review':json.loads(row['review']),'annotation_resolution':None,
                'annotation_cleanup':{'original_path':row['image_path'],'original_sha256':row['image_sha256'],
                    'image_sha256':metadata['image_sha256'],'review':review,'comparison':comparison}}
            after_review={**review,'decision':'accepted','acceptance_basis':'human_keep_with_annotation_cleanup',
                          'human_keep':receipt,'human_keep_sha256':digest(receipt)}
            after={**dict(row),'image_path':str(staged),'image_sha256':metadata['image_sha256'],'review':canonical(after_review)}
            if not valid(after,after_review,desc['review_identity']):raise ValueError('Cleanup comparison is incomplete or stale')
            entries.append({'before':dict(row),'staged':metadata,'after_review':after_review})
        return {'run_sha256':sha256(run/'run.json'),'entries':entries,'original_images_changed':0}
    finally:db.close()


def apply_cleanups(run,manifest):
    from bulk_expansion_images import connect,descriptor,lock,atomic_json,accepted_reference
    run=Path(run).resolve();manifest=Path(manifest).resolve();plan=json.loads(manifest.read_text());desc=descriptor(run)
    if plan['run_sha256']!=sha256(run/'run.json'):raise ValueError('Wrong cleanup run')
    destination=run/'human-keep-cleanups'/sha256(manifest)[:16]
    with ExitStack() as locks:
        for name in ('supervisor','generation','review','reference-review','reference-repair-review'):locks.enter_context(lock(run,name))
        db=connect(run)
        try:
            if destination.exists():raise ValueError('Cleanup application already exists')
            prepared=[]
            for entry in plan['entries']:
                before=entry['before'];metadata=entry['staged'];review=entry['after_review']
                row=db.execute('SELECT * FROM jobs WHERE job_id=?',(before['job_id'],)).fetchone()
                after={**dict(row),'image_path':metadata['image_path'],'image_sha256':metadata['image_sha256']}
                source=accepted_reference(db,json.loads(row['request']),desc['review_identity'])
                if (dict(row)!=before or sha256(Path(metadata['image_path']))!=metadata['image_sha256']
                        or not valid(after,review,desc['review_identity']) or source is False
                        or (source and sha256(source)!=review.get('reference_sha256'))):raise ValueError('Cleanup changed before apply')
                attempt=row['attempts']+1;path=run/'candidates'/row['job_id']/f'attempt-{attempt:02d}.jpg'
                if path.exists():raise ValueError('Cleanup would overwrite an attempt')
                prepared.append((entry,attempt,path))
            destination.mkdir(parents=True)
            with closing(sqlite3.connect(destination/'ledger-before.sqlite')) as backup:db.backup(backup)
            atomic_json(destination/'manifest.json',plan)
            for entry,attempt,path in prepared:
                metadata=entry['staged'];shutil.copyfile(metadata['image_path'],path)
                if sha256(path)!=metadata['image_sha256']:raise ValueError('Cleanup copy changed')
                atomic_json(path.with_suffix('.json'),{**metadata,'image_path':str(path),'attempt':attempt,
                    'request_sha256':digest(json.loads(entry['before']['request'])),'actual_prompt':metadata['prompt'],
                    'annotation_cleanup_manifest_sha256':sha256(manifest)})
            with db:
                for entry,attempt,path in prepared:
                    db.execute("UPDATE jobs SET state='accepted',attempts=?,image_path=?,image_sha256=?,review=?,error=NULL,updated=? WHERE job_id=?",
                        (attempt,str(path),entry['staged']['image_sha256'],canonical(entry['after_review']),time.time(),entry['before']['job_id']))
            result={'accepted_cleanups':len(prepared),'original_images_changed':0,'backup':str(destination/'ledger-before.sqlite')}
            atomic_json(destination/'receipt.json',result);return result
        finally:db.close()
