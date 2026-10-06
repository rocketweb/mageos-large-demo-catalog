"""Finite, exact-job reprocessing from human review patterns, with reversible intent edits."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack, closing
import copy
import json
from pathlib import Path
import re
import shutil
import sqlite3
import time

from build_expanded_catalog import canonical, csv_rows, digest, variations
from image_policy import product_prompt, validate_prompt, visual_text
from prepare_catalog import sha256

VERSION = 'human-pattern-corrections-v1'
TABLE = 'feedback_reprocessing'


def feedback_rows(path):
    with closing(sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro', uri=True)) as db:
        rows = db.execute('SELECT i.id,i.payload,d.choice,d.note,d.revision,d.updated FROM decisions d JOIN items i ON i.id=d.item_id WHERE d.choice IS NOT NULL ORDER BY d.updated').fetchall()
    return [{'id': key, 'item': json.loads(payload), 'choice': choice, 'note': note,
             'revision': revision, 'updated': updated} for key, payload, choice, note, revision, updated in rows]


def pattern(job, direct=None):
    design = job['design']; profile = job.get('profile', design.get('profile', ''))
    material = design.get('material', '')
    options = design.get('options', {})
    if profile == 'candle-holder': return 'empty-candle-holder'
    if profile == 'mirror': return 'reflective-mirror-interior'
    if profile == 'vase': return 'colored-decorative-vase'
    if profile == 'Beds':
        if re.search(r'\btwin\b', options.get('wands_size', '') + ' ' + design.get('subject', ''), re.I):
            return 'twin-bed-proportions'
        if direct and 'width' in direct['note'].lower(): return 'reviewed-bed-proportions'
    if profile == 'Dining Chairs' and material == 'Metal': return 'visible-metal-chair-frame'
    if profile == 'Dining Tables':
        seats = ' '.join(str(value) for key, value in options.items() if 'seat' in key)
        if not seats: seats = design.get('subject', '')
        match = re.search(r'(?:Seats?\s*)?\b(2|6)\b', seats, re.I)
        if match: return 'table-seating-' + match[1]
    if profile == 'Office Chairs':
        if material in {'Solid Wood', 'Engineered Wood', 'Bamboo'}: return 'chair-upholstery-only'
        if material == 'Velvet': return 'preserve-velvet-pile'
    if profile == 'cable-tray': return 'functional-underdesk-mounts'
    if (profile == 'desk-drawer' and direct and
            'single drawer' in direct['note'].lower() and
            'underneath a desk' in direct['note'].lower()):
        return 'single-underdesk-drawer'
    if profile == 'cubby-tower' and material == 'Bamboo': return 'smooth-painted-cubby'
    return None


INSTRUCTIONS = {
    'empty-candle-holder': 'One empty candle holder with an open recessed candle well, a level flat interior support and a stable flat base. The cavity is visibly empty. No candle, wax, wick, flame, liquid, drinking-glass bowl or wine-glass stem.',
    'reflective-mirror-interior': 'A functioning framed wall mirror. Apply the target color only to the entire outer frame. Preserve the reflective silver mirror glass inside the frame and its subtle natural reflections. Never paint, fill or cover the mirror interior.',
    'colored-decorative-vase': 'One empty decorative vase in the specified opaque color, with an obvious subtle sculpted ribbed or relief surface motif. The vase has an open empty mouth. Preserve the specified material; no clear uncolored glass, liquid, flowers or lettering.',
    'twin-bed-proportions': 'A narrow single-person twin bed: a long narrow mattress platform approximately twice as long as it is wide, a correspondingly narrow headboard and one centered presentation pillow. Preserve recognizable bed styling and realistic support. Do not depict a wide double or queen bed.',
    'reviewed-bed-proportions': 'Correct the oversized width to a compact full-size bed with a rectangular sleeping platform visibly longer than it is wide. Preserve the stated Full size and recognizable bed construction; do not depict an oversized queen or king bed.',
    'visible-metal-chair-frame': 'An upholstered dining chair with a clearly visible coherent metal support frame and metal legs. The exposed structural supports must look like metal rather than natural wood. Preserve the requested upholstery color and physically plausible joints.',
    'table-seating-6': 'A stable rectangular dining table with a visibly elongated tabletop accommodating two dining places along each long side and one at each end. Make it proportionately longer than a compact four-person table. Show the complete table and its structurally plausible supports; do not add chairs or place settings.',
    'table-seating-2': 'A compact dining table for two people, with a small tabletop and exactly four connected, evenly spaced sturdy legs supporting its corners. Show the entire stable structure. No missing legs, unstable two-leg base, chairs or place settings.',
    'chair-upholstery-only': 'Change only the existing colored padded seat and back upholstery to the target color. Preserve exposed wooden arms, legs and frame in their original natural wood or brown finish. Preserve wheel bases, casters, hardware, seams, shape and upholstery texture. Do not paint the wooden structure.',
    'preserve-velvet-pile': 'Change only the upholstery color while preserving obvious soft velvet pile, subtle directional nap, fabric detail and restrained velvet sheen. Keep the existing frame, hardware, silhouette and construction. Do not replace velvet with smooth leather, plastic or a flat color mask.',
    'functional-underdesk-mounts': 'One empty elongated rectangular under-desk cable-management tray, with a shallow straight channel and clearly visible integrated right-angle mounting flanges with screw holes for fastening beneath a desktop. Depict a functional rigid structure in the specified material. No rounded basket, plant pot, planter saucer, ceramic vessel, cables or desk props. The color describes only its finish, never its material or function.',
    'single-underdesk-drawer': 'A single shallow drawer in one compact metal housing designed to attach to the underside of a desk. Show visible flat mounting flanges with screw holes along the top outer edges, facing up toward the underside of a desktop. One drawer front, one drawer cavity and realistic side slides; no second or third drawer, no freestanding cabinet, pedestal or desk. The separate sale product is the under-desk drawer assembly.',
    'smooth-painted-cubby': 'Preserve the source cubby tower exactly: its straight structure, shelf count, open compartments, smooth painted finish and color. Preserve the original level of subtle surface texture. Do not invent wood grain, streaks, decorative patterns, extra shelves or changed openings.',
}


def corrected_request(job, kind, direct=None):
    revised = copy.deepcopy(job)
    design = revised['design']
    before_material = design.get('material', '')
    # Repeated explicit notes establish ceramic as the intended opaque holder material.
    if kind == 'empty-candle-holder' and before_material == 'Glass': design['material'] = 'Ceramic'
    if (kind == 'reflective-mirror-interior' and direct and
            'frame should be black' in direct['note'].lower()):
        design['color'] = 'Black'
        if revised.get('reference'): revised['reference']['value'] = 'Black'
        if 'color' in design.get('options', {}): design['options']['color'] = 'Black'
    semantic = kind in {'empty-candle-holder', 'colored-decorative-vase', 'twin-bed-proportions',
                       'reviewed-bed-proportions', 'visible-metal-chair-frame', 'table-seating-2',
                       'table-seating-6', 'functional-underdesk-mounts', 'single-underdesk-drawer'}
    if semantic:
        # This correction intentionally revises construction or material. Validate the
        # corrected sale unit independently rather than requiring the flawed source shape.
        revised['reference'] = None
        design['reference_required'] = False
    design['construction'] = INSTRUCTIONS[kind]
    for key, old, new in (('material', before_material, design.get('material', '')),
                          ('color', job['design'].get('color', ''), design.get('color', ''))):
        if old and old != new:
            design['subject'] = re.sub(r'\b' + re.escape(old) + r'\b', new, design.get('subject', ''))
    color = design.get('color', '')
    color_words = 'warm muted orange-brown, used only as a color' if color == 'Terracotta' else color
    subject = visual_text(design.get('subject') or job['profile'])
    if color == 'Terracotta': subject = subject.replace('Terracotta', 'warm orange-brown')
    intro = ('Create a new unannotated studio product photograph of ' if semantic else
             'Carefully edit the source photograph of ')
    body = (intro + subject + '. Product class: ' + design.get('product_class', job['profile']) +
            '. Material: ' + design.get('material', '') + '. Target color or finish: ' + color_words + '. ' +
            INSTRUCTIONS[kind] + ' Whole product in frame, realistic lighting and natural photographic detail on a plain background. No additional products.')
    revised['prompt'] = product_prompt(body)
    revised['design_sha256'] = digest(design)
    return revised, semantic


def product_patches(before, after, products):
    changes = {}
    substitutions = [(before['design'].get(key, ''), after['design'].get(key, '')) for key in ('material', 'color')]
    if (before['design'].get('profile')=='desk-drawer' and
            before['design'].get('construction')=='two stacked shallow drawers' and
            after['design'].get('construction')==INSTRUCTIONS['single-underdesk-drawer']):
        substitutions.append(('two stacked shallow drawers','one mountable shallow drawer'))
    substitutions = [(old, new) for old, new in substitutions if old and old != new]
    for sku in before.get('skus', [before['sku']]):
        row = products[sku]; fields = {}
        for key in ('name', 'description', 'short_description', 'meta_title', 'meta_description',
                    'color', 'wands_finish', 'wands_material', 'lab_spec_material', 'lab_spec_frame_material', 'lab_spec_color'):
            old = row.get(key, ''); new = old
            for source, target in substitutions:
                new = re.sub(r'\b' + re.escape(source) + r'\b', target, new)
            if new != old: fields[key] = {'before': old, 'after': new}
        if fields: changes[sku] = fields
    return changes


def prepare(run, feedback_path):
    from bulk_expansion_images import connect, descriptor, accepted_reference
    run = Path(run).resolve(); desc = descriptor(run)
    feedback = feedback_rows(feedback_path)
    latest = {row['item']['job_id']: row for row in feedback}
    evidence = {}
    for row in feedback:
        if row['choice'] == 'redo':
            kind = pattern(row['item']['request'], row)
            if kind: evidence.setdefault(kind, []).append({key: row[key] for key in ('id', 'note', 'revision')})
    db = connect(run)
    try:
        rows = list(db.execute("SELECT * FROM jobs WHERE state IN ('pending','rejected','review_required','interrupted') ORDER BY ordinal"))
        provisional = []; skipped = Counter()
        for row in rows:
            job = json.loads(row['request']); direct = latest.get(row['job_id'])
            if row['pilot']:
                skipped['pilot'] += 1; continue
            if direct and direct['item']['image_sha256'] == row['image_sha256'] and direct['choice'] == 'keep':
                skipped['human_keep'] += 1; continue
            if direct and direct['item']['image_sha256'] != row['image_sha256']: direct = None
            kind = pattern(job, direct)
            if kind not in evidence: continue
            if row['image_path'] and sha256(Path(row['image_path'])) != row['image_sha256']:
                raise ValueError('Candidate bytes changed')
            after, semantic = corrected_request(job, kind, direct)
            source = None; source_kind = 'none'; mode = 'generate'
            if not semantic:
                if job.get('reference'):
                    source = accepted_reference(db, job, desc['review_identity'])
                    source_kind = 'current_accepted'; mode = 'edit'
                    if source is False: source = None
                elif row['image_path']:
                    previous = Path(row['image_path']).with_name(f"attempt-{row['attempts']-1:02d}.jpg")
                    source = previous if previous.exists() else Path(row['image_path'])
                    source_kind = 'fixed'; mode = 'edit'
                if kind == 'smooth-painted-cubby' and direct and direct['item'].get('source_path'):
                    source = Path(direct['item']['source_path'])
                    if sha256(source) != direct['item']['source_sha256']: raise ValueError('Human-reviewed source changed')
                    source_kind = 'fixed'; mode = 'reuse'
            entry = {'job_id': row['job_id'], 'sku': job['sku'], 'pattern': kind,
                     'request_before': job, 'request_after': after, 'before_request_sha256': digest(job),
                     'after_request_sha256': digest(after), 'baseline_attempts': row['attempts'],
                     'max_attempts': row['attempts'] + (1 if mode == 'reuse' else 2),
                     'baseline_image_sha256': row['image_sha256'], 'baseline_image_path': row['image_path'],
                     'baseline_state': row['state'], 'prompt': after['prompt'], 'mode': mode,
                     'source_kind': source_kind, 'source_path': str(source.resolve()) if source else None,
                     'source_sha256': sha256(source) if source else None,
                     'direct_feedback': {key: direct[key] for key in ('id','choice','note','revision')} if direct else None,
                     'pattern_evidence': evidence[kind]}
            provisional.append(entry)
        wanted = {sku for entry in provisional for sku in entry['request_before'].get('skus', [entry['sku']])}
        products = {}
        for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv'):
            for row in csv_rows(Path(desc['candidate'])/'data'/name):
                if row['sku'] in wanted: products[row['sku']] = row
        for entry in provisional:
            entry['catalog_patches'] = product_patches(entry['request_before'], entry['request_after'], products)
        return {'schema': 1, 'version': VERSION, 'run_sha256': sha256(run/'run.json'),
                'feedback_path': str(Path(feedback_path).resolve()), 'prepared_at': time.time(),
                'feedback_counts': dict(Counter(row['choice'] for row in feedback)),
                'skipped': dict(skipped), 'patterns': dict(Counter(entry['pattern'] for entry in provisional)),
                'jobs': provisional}
    finally: db.close()


def has_table(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone())


def plan_generation(run, db, record, desc):
    """Return (handled, plan); exhausted corrections cannot fall back to old retry budgets."""
    if not has_table(db): return False, None
    row = db.execute('SELECT * FROM feedback_reprocessing WHERE job_id=?', (record['job_id'],)).fetchone()
    if row is None or not row['active']: return False, None
    entry = json.loads(row['entry'])
    job = json.loads(record['request'])
    if digest(entry) != row['entry_sha256'] or digest(job) != entry['after_request_sha256']:
        raise ValueError('Human correction intent changed')
    if record['state'] not in {'pending','rejected','review_required','interrupted'}: return True, None
    baseline = entry['baseline_attempts']; attempts = record['attempts']
    if not baseline <= attempts < entry['max_attempts']: return True, None
    if attempts == baseline and record['image_sha256'] != entry['baseline_image_sha256']:
        raise ValueError('Human correction baseline changed')
    if entry['baseline_image_path'] and sha256(Path(entry['baseline_image_path'])) != entry['baseline_image_sha256']:
        raise ValueError('Original failed image changed')
    for number in range(baseline + 1, attempts + 1):
        path = run/'candidates'/record['job_id']/f'attempt-{number:02d}.jpg'
        data = json.loads(path.with_suffix('.json').read_text())
        if (sha256(path) != data['image_sha256'] or data.get('request_sha256') != entry['after_request_sha256']
                or data.get('actual_prompt') != entry['prompt']):
            raise ValueError('Correction attempt history changed')
    reference = None
    if entry['source_kind'] == 'current_accepted':
        from bulk_expansion_images import accepted_reference
        reference = accepted_reference(db, job, desc['review_identity'])
        if not reference: return True, None
    elif entry['source_kind'] == 'fixed':
        reference = Path(entry['source_path'])
        if sha256(reference) != entry['source_sha256']: raise ValueError('Correction reference changed')
    if entry['mode'] == 'reuse': return True, None  # Exact source reuse is atomically staged at activation.
    validate_prompt(entry['prompt'])
    return True, {'prompt': entry['prompt'], 'reference': reference, 'attempt': attempts + 1,
                  'seed': (job['seed'] + attempts * 104729) % (2**32)}


def apply_catalog_patches(db, rows):
    """Reconcile changed material/color fields in the final export, never mutate frozen inputs."""
    if not has_table(db): return rows
    changed = {}
    for record in db.execute('SELECT * FROM feedback_reprocessing WHERE active=1'):
        entry = json.loads(record['entry'])
        if digest(entry) != record['entry_sha256']: raise ValueError('Correction receipt changed')
        for sku, patches in entry['catalog_patches'].items():
            for field, patch in patches.items():
                if rows[sku].get(field, '') != patch['before']: raise ValueError('Product patch baseline changed: ' + sku)
                rows[sku][field] = patch['after']
            changed[sku] = patches
    for parent in rows.values():
        if parent.get('product_type') != 'configurable': continue
        groups = variations(parent); altered = False
        for group in groups:
            sku = group['sku']
            for field in set(group) & set(changed.get(sku, {})):
                if field != 'sku': group[field] = rows[sku][field]; altered = True
        if altered:
            signatures = [canonical({key:value for key,value in group.items() if key!='sku'}) for group in groups]
            if len(signatures) != len(set(signatures)): raise ValueError('Corrected variant duplicates sibling options')
            parent['configurable_variations'] = '|'.join(','.join(key+'='+str(value) for key,value in group.items()) for group in groups)
    return rows


def activate(run, manifest):
    from bulk_expansion_images import atomic_json, connect, descriptor, lock
    run = Path(run).resolve(); manifest = Path(manifest).resolve(); plan = json.loads(manifest.read_text())
    desc = descriptor(run)
    if plan['version'] != VERSION or plan['run_sha256'] != sha256(run/'run.json'): raise ValueError('Wrong correction run')
    directory = run/'feedback-reprocessing'/sha256(manifest)[:16]
    with ExitStack() as locks:
        for name in ('supervisor','generation','review','reference-review','reference-repair-review'):
            locks.enter_context(lock(run,name))
        db = connect(run)
        try:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='remote_batches'").fetchone():
                if db.execute("SELECT 1 FROM remote_batches WHERE state='reserved'").fetchone(): raise ValueError('Drain remote batches first')
            if directory.exists(): raise ValueError('Correction activation already exists')
            latest = {row['item']['job_id']: row for row in feedback_rows(plan['feedback_path'])}
            before = []
            for entry in plan['jobs']:
                if (entry['mode'] not in {'generate','edit','reuse'}
                        or entry['max_attempts']-entry['baseline_attempts'] not in {1,2}
                        or digest(entry['request_before'])!=entry['before_request_sha256']
                        or digest(entry['request_after'])!=entry['after_request_sha256']
                        or entry['prompt']!=entry['request_after']['prompt']):
                    raise ValueError('Malformed correction admission')
                row = db.execute('SELECT * FROM jobs WHERE job_id=?', (entry['job_id'],)).fetchone()
                if (row is None or row['pilot'] or row['state'] != entry['baseline_state'] or row['state']=='accepted'
                        or row['attempts'] != entry['baseline_attempts'] or row['image_sha256'] != entry['baseline_image_sha256']
                        or digest(json.loads(row['request'])) != entry['before_request_sha256']):
                    raise ValueError('Job changed before activation: '+entry['sku'])
                if row['image_path'] and sha256(Path(row['image_path'])) != row['image_sha256']: raise ValueError('Changed image bytes')
                human = latest.get(entry['job_id'])
                if human and human['choice']=='keep' and human['item']['image_sha256']==row['image_sha256']:
                    raise ValueError('Human Keep must not be reprocessed')
                if entry['direct_feedback'] and (not human or any(human[key] != entry['direct_feedback'][key] for key in ('id','choice','note','revision'))):
                    raise ValueError('Human correction changed; rebuild preview')
                if has_table(db) and db.execute('SELECT 1 FROM feedback_reprocessing WHERE job_id=?',(entry['job_id'],)).fetchone():
                    raise ValueError('Existing correction budgets cannot be reset')
                validate_prompt(entry['prompt'])
                before.append(dict(row))
            # Exercise all product and configurable-option changes before writing anything.
            candidate=Path(desc['candidate'])
            product_rows={row['sku']:row for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv')
                          for row in csv_rows(candidate/'data'/name)}
            with closing(sqlite3.connect(':memory:')) as preview:
                preview.row_factory=sqlite3.Row
                preview.execute('CREATE TABLE feedback_reprocessing(entry,entry_sha256,active)')
                preview.executemany('INSERT INTO feedback_reprocessing VALUES(?,?,1)',
                                    [(canonical(entry),digest(entry)) for entry in plan['jobs']])
                apply_catalog_patches(preview,product_rows)
            del product_rows
            directory.mkdir(parents=True)
            with closing(sqlite3.connect(directory/'ledger-before.sqlite')) as backup: db.backup(backup)
            shutil.copyfile(manifest,directory/'manifest.json')
            atomic_json(directory/'rollback-before.json',{'jobs':before,'instruction':'Restore only untouched queued rows with matching effective request and baseline attempt. Never restore this ledger over later work.'})
            # Stage exact source reuse as a new immutable attempt, then ordinary QA.
            reused = {}
            for entry in plan['jobs']:
                if entry['mode'] != 'reuse': continue
                source = Path(entry['source_path'])
                if sha256(source) != entry['source_sha256']: raise ValueError('Reuse source changed')
                attempt = entry['baseline_attempts'] + 1
                target = run/'candidates'/entry['job_id']/f'attempt-{attempt:02d}.jpg'
                if target.exists(): raise ValueError('Attempt already exists')
                with source.open('rb') as incoming, target.open('xb') as outgoing: shutil.copyfileobj(incoming,outgoing)
                metadata = {'status':'generated','job_id':entry['job_id'],'attempt':attempt,'image_sha256':sha256(target),
                            'request_sha256':entry['after_request_sha256'],'actual_prompt':entry['prompt'],
                            'reference_sha256':entry['source_sha256'],'source_reuse':True,
                            'correction_manifest_sha256':sha256(manifest)}
                atomic_json(target.with_suffix('.json'),metadata); reused[entry['job_id']] = (attempt,str(target),metadata['image_sha256'])
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS feedback_reprocessing(job_id TEXT PRIMARY KEY,entry TEXT NOT NULL,entry_sha256 TEXT NOT NULL,manifest_sha256 TEXT NOT NULL,active INTEGER NOT NULL)')
                for entry in plan['jobs']:
                    db.execute('INSERT INTO feedback_reprocessing VALUES(?,?,?,?,1)', (entry['job_id'],canonical(entry),digest(entry),sha256(manifest)))
                    db.execute("UPDATE jobs SET request=?,state='pending',review=NULL,error=NULL,updated=? WHERE job_id=?",(canonical(entry['request_after']),time.time(),entry['job_id']))
                    if entry['job_id'] in reused:
                        attempt,path,pin = reused[entry['job_id']]
                        db.execute("UPDATE jobs SET state='generated',attempts=?,image_path=?,image_sha256=? WHERE job_id=?",(attempt,path,pin,entry['job_id']))
                    db.execute("DELETE FROM review_failures WHERE scope='job' AND item=?",(entry['job_id'],))
            receipt = {'queued':len(plan['jobs'])-len(reused),'source_reuse_awaiting_qa':len(reused),
                       'patterns':plan['patterns'],'accepted_images_changed':0,'manifest_sha256':sha256(manifest),
                       'backup':str(directory/'ledger-before.sqlite'),'activated_at':time.time()}
            atomic_json(directory/'activation.json',receipt)
            return receipt
        finally: db.close()


def rollback_unstarted(run, manifest):
    """Restore untouched queued rows only; retain every attempted correction and file."""
    from bulk_expansion_images import atomic_json, connect, lock
    run=Path(run).resolve();manifest=Path(manifest).resolve()
    directory=run/'feedback-reprocessing'/sha256(manifest)[:16]
    before=json.loads((directory/'rollback-before.json').read_text())['jobs']
    restored=[];advanced=[]
    with ExitStack() as locks:
        for name in ('supervisor','generation','review','reference-review','reference-repair-review'):
            locks.enter_context(lock(run,name))
        db=connect(run)
        try:
            if db.execute("SELECT 1 FROM remote_batches WHERE state='reserved'").fetchone():
                raise ValueError('Drain remote batches first')
            with db:
                for original in before:
                    record=db.execute('SELECT * FROM feedback_reprocessing WHERE job_id=?',(original['job_id'],)).fetchone()
                    current=db.execute('SELECT * FROM jobs WHERE job_id=?',(original['job_id'],)).fetchone()
                    entry=json.loads(record['entry'])
                    if (current['state']!='pending' or current['attempts']!=original['attempts']
                            or current['image_sha256']!=original['image_sha256']
                            or digest(json.loads(current['request']))!=entry['after_request_sha256']):
                        advanced.append(original['job_id']);continue
                    columns=('request','state','review','error','updated')
                    db.execute('UPDATE jobs SET '+','.join(name+'=?' for name in columns)+' WHERE job_id=?',
                               tuple(original[name] for name in columns)+(original['job_id'],))
                    db.execute('UPDATE feedback_reprocessing SET active=0 WHERE job_id=?',(original['job_id'],))
                    restored.append(original['job_id'])
            result={'restored_unstarted':restored,'preserved_advanced':advanced,'time':time.time()}
            atomic_json(directory/'rollback-receipt.json',result);return result
        finally:db.close()


def main():
    from bulk_expansion_images import atomic_json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','activate','rollback-unstarted'])
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--feedback',type=Path)
    parser.add_argument('--manifest',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='prepare':
        if args.manifest.exists(): raise ValueError('Choose a new immutable preview')
        plan=prepare(args.run,args.feedback or args.run.parent/'human-image-review/feedback.sqlite')
        args.manifest.parent.mkdir(parents=True,exist_ok=True);atomic_json(args.manifest,plan)
        print(json.dumps({key:plan[key] for key in ('patterns','skipped','feedback_counts')}))
    elif args.command=='activate': print(json.dumps(activate(args.run,args.manifest)))
    else:print(json.dumps(rollback_unstarted(args.run,args.manifest)))


if __name__=='__main__': main()
