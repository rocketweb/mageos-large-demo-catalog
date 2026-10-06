"""Bounded recovery recipes for diagnosed construction failures, with unchanged QA."""
from collections import Counter
from contextlib import closing
import copy
import json
from pathlib import Path
import re
import sqlite3
import time

from build_expanded_catalog import canonical,digest
from image_policy import product_prompt,visual_text
from prepare_catalog import sha256


def recipe(design):
    profile=design.get('profile',design.get('product_class',''))
    subject=design.get('subject','');construction=design.get('construction','')
    text='';pattern=None
    if profile=='monitor-riser':
        pattern='empty-desktop-platform'
        text=('A low, wide desktop shelf platform. Its broad rectangular top lies horizontally, supported by two short side legs. '
              'The width is much greater than the height. The flat top is visibly empty. '
              'Only this small furniture platform is present. No computer, screen, monitor, display panel, upright board or electronics. ')
        if 'drawer' in construction:text+='One slim drawer beneath the horizontal top, one visible drawer front and one pull. '
        else:text+='One open unobstructed rectangular space beneath the top, no drawer. '
    elif profile=='floor-lamp':
        pattern='tall-floor-lamp'
        text=('A very tall slender freestanding floor lamp with a small plain fabric drum shade, a long upright stem and a weighted base. '
              'The exposed stem is several times taller than the shade. The entire lamp nearly fills a tall vertical composition. '
              'It stands directly on the floor, with no table or furniture. ')
    elif profile=='work-cart' and 'two open shelves' in construction:
        pattern='two-level-work-cart'
        text=('An empty rolling workshop trolley with exactly two broad useful horizontal shelf surfaces: one top work surface '
              'and one bottom storage shelf near the wheels. Four corner posts connect them. '
              'One large empty gap between the two shelves. Four small caster wheels, one at each bottom corner. '
              'No middle shelves, drawers, boxes or tools. ')
    elif profile=='laundry-sorter' and 'three separate fabric bags' in construction:
        pattern='three-side-by-side-bags'
        text=('One laundry sorting frame supporting exactly three separate removable plain fabric bags side by side in a single row. '
              'All three bag openings and the three distinct bag bodies are visible. The frame has no upper storage bin, '
              'shelf, lid, extra basket or additional bag. ')
    elif profile=='canister-rack' and 'three stepped shelves' in construction:
        pattern='three-step-countertop-rack'
        text=('One small empty countertop organizer shaped like a staircase with exactly three broad horizontal treads. '
              'The front tread is low, the middle tread is higher and farther back, the rear tread is highest. '
              'Show all three empty step surfaces from an elevated front angle. '
              'It is a compact stepped platform, no tall vertical bookcase, posts, containers or stacked flat shelves. ')
    elif profile=='cooking-spoon' and design.get('material')=='Metal':
        pattern='reflective-metal-spoon'
        text=('One cooking spoon with a continuous metal handle and bowl, coated in the specified colored enamel. '
              'The colored enamel covers the broad handle and bowl surfaces; subtle crisp metallic highlights occur along the edges. '
              'No wood grain or molded plastic surface. '+construction+'. ')
    elif re.search(r'\b[1-9]\s*[- ]\s*Lights?\b',subject,re.I) and any(k in profile for k in ('Chandelier','Sconce','Pendant','Lighting')):
        count=int(re.search(r'\b([1-9])\s*[- ]\s*Lights?\b',subject,re.I)[1])
        pattern='explicit-light-count'
        words=('zero','one','two','three','four','five','six','seven','eight','nine')
        if 'Vanity' in profile or 'bath bar' in subject.lower():
            text=('One wall-mounted bathroom vanity light with a horizontal backplate and '+words[count]+' distinct light sockets in one straight horizontal row. '
                  'The fixture mounts above a bathroom mirror, with no hanging cord, chain or ceiling canopy. ')
        elif 'Flush Mount' in profile:
            text='One compact ceiling-mounted light fixture with '+words[count]+' distinct light sockets on one flush ceiling base. '
        elif 'Sconce' in profile:
            text='One wall-mounted lighting fixture with a single backplate and '+words[count]+' distinct light sockets. '
        elif 'Chandelier' in profile:
            text=('One decorative hanging chandelier suspended from a long chain and a ceiling canopy, with '+words[count]+' distinct light sockets. ')
            if re.search('empire',subject,re.I):text+='A large tiered tapered decorative metal cage surrounds the bulb area. '
            elif re.search('wagon wheel',subject,re.I):text+='A broad decorative horizontal metal wheel surrounds the central light area, suspended by balanced chains. '
            else:text+='A broad ornate open metal framework surrounds the lighting elements. '
        else:
            text='One pendant light suspended on a long cord from a ceiling canopy, with '+words[count]+' distinct light sockets. '
        text+=('Exactly '+words[count]+' visible bulbs in total, each mounted in its own socket. '
               'The whole fixture and every bulb are visible and separated clearly. ')
        if count==1:text+='One central bulb only, no side arms, repeated candle holders or additional bulbs. '
        else:text+='Arrange the bulb sockets symmetrically with clear spacing and plausible connected supports. '
    elif re.search(r'\b[2-9]\s*[- ]\s*Drawer\b',subject,re.I) and any(k in profile for k in ('Dresser','Chest','Cabinet','Nightstand')):
        count=int(re.search(r'\b([2-9])\s*[- ]\s*Drawer\b',subject,re.I)[1])
        # Mixed door/drawer units need their own recipe, not an inferred redesign.
        if re.search(r'\bdoor\b',subject,re.I):return None
        pattern='explicit-drawer-layout'
        layouts={2:'two full-width drawers stacked vertically',3:'three full-width drawers stacked vertically',
                 4:'four full-width drawers stacked vertically',5:'five full-width drawers stacked vertically',
                 6:'two columns of three drawers',7:'three small drawers across the top and two rows of two wide drawers below',
                 8:'two columns of four drawers',9:'three columns of three drawers'}
        text=('One chest of drawers with '+layouts[count]+'. Exactly '+str(count)+' separate rectangular drawer fronts in total. '
              'Every front has one centered pull and its own clear complete outline. '
              'View the front almost straight on so every drawer can be counted. No extra narrow trim resembling drawers. ')
    if not pattern:return None
    material=visual_text(design.get('material',''));color=visual_text(design.get('color',''))
    finish='Finish: '+color+'. '
    if material in {'Solid Wood','Engineered Wood','Bamboo','Metal'} and color in {'White','Black','Green','Navy','Blue','Red','Cream','Gray'}:
        finish='The entire main structure is opaque '+color+' painted '+material+'. No unpainted natural brown surfaces. '
    elif material=='Metal' and color=='Natural':finish='Unpainted silvery natural metal, with metallic highlights and no wood surfaces. '
    # Prompt descriptions omit ambiguous marketing names; the reviewer still gets
    # the complete unchanged intended product brief.
    prompt=product_prompt('Studio catalog photograph. '+finish+text+'Material: '+material+'. '+finish+
        'Retain appropriate material texture beneath the finish. '
        'Plain warm white background, whole product inside the image, coherent construction, no extra props.')
    return {'pattern':pattern,'prompt':prompt,'mode':'generate'}


def prepare_jobs(run,allowed_patterns):
    """Use the existing immutable correction admission and scoped rollback."""
    from bulk_expansion_images import connect
    from feedback_reprocessing import VERSION,feedback_rows,has_table
    from human_keep_acceptance import is_kept
    run=Path(run).resolve();db=connect(run);entries=[]
    feedback=run.parent/'human-image-review/feedback.sqlite'
    decisions={r['item']['job_id']:r for r in feedback_rows(feedback)}
    try:
        for row in db.execute("SELECT * FROM jobs WHERE state IN ('rejected','review_required') AND pilot=0 ORDER BY ordinal"):
            job=json.loads(row['request'])
            if job.get('reference') or is_kept(run,row):continue
            if has_table(db) and db.execute('SELECT 1 FROM feedback_reprocessing WHERE job_id=?',(row['job_id'],)).fetchone():continue
            strategy=recipe(job['design'])
            if not strategy or strategy['pattern'] not in allowed_patterns:continue
            if sha256(Path(row['image_path']))!=row['image_sha256']:raise ValueError('Rejected bytes changed')
            after=copy.deepcopy(job);after['prompt']=strategy['prompt']
            entries.append({'job_id':row['job_id'],'sku':job['design']['sku'],'pattern':strategy['pattern'],
                'baseline_state':row['state'],'baseline_attempts':row['attempts'],'max_attempts':row['attempts']+1,
                'baseline_image_path':row['image_path'],'baseline_image_sha256':row['image_sha256'],
                'request_before':job,'before_request_sha256':digest(job),'request_after':after,'after_request_sha256':digest(after),
                'prompt':strategy['prompt'],'mode':'generate','source_kind':'none','source_path':None,'source_sha256':None,
                'direct_feedback':decisions.get(row['job_id']),'catalog_patches':{},
                'diagnosis':json.loads(row['review']).get('vision',{}).get('issues',[]),
                'strategy_change':'Fresh rendering with explicit construction; do not edit the disproved silhouette.'})
        return {'schema':1,'version':VERSION,'run_sha256':sha256(run/'run.json'),'feedback_path':str(feedback),
                'prepared_at':time.time(),'patterns':dict(Counter(e['pattern'] for e in entries)),
                'feedback_counts':dict(Counter(r['choice'] for r in decisions.values())),'jobs':entries}
    finally:db.close()


def reference_plan(run,db,row,attempts):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='reference_completion_recovery'").fetchone():return None
    record=db.execute('SELECT entry,entry_sha256 FROM reference_completion_recovery WHERE original_sha256=? AND design_sha256=?',
                      (row['image_sha256'],row['design_sha256'])).fetchone()
    if record is None:return None
    entry=json.loads(record['entry'])
    if digest(entry)!=record['entry_sha256']:raise ValueError('Reference correction receipt changed')
    baseline=entry['baseline_attempts']
    if len(attempts)!=baseline:return None  # One new attempt, never reset the history.
    if (sha256(Path(row['path']))!=row['image_sha256'] or digest(json.loads(row['design']))!=row['design_sha256']
            or sha256(Path(attempts[-1]['image_path']))!=entry['baseline_image_sha256']
            or attempts[-1]['image_sha256']!=entry['baseline_image_sha256']):
        raise ValueError('Reference correction baseline changed')
    return entry


def prepare_references(run,allowed_patterns):
    from bulk_expansion_images import connect,descriptor
    from export_expanded_catalog import accepted_retained
    run=Path(run).resolve();db=connect(run);desc=descriptor(run);entries=[]
    try:
        for row in db.execute('SELECT * FROM references_to_review WHERE review IS NOT NULL'):
            strategy=recipe(json.loads(row['design']))
            if not strategy or strategy['pattern'] not in allowed_patterns:continue
            if accepted_retained(db,row,desc['review_identity']):continue
            attempts=list(db.execute('SELECT * FROM reference_repairs WHERE original_sha256=? AND design_sha256=? ORDER BY attempt',
                (row['image_sha256'],row['design_sha256'])))
            if len(attempts)<3 or not attempts[-1]['review']:continue
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='reference_completion_recovery'").fetchone():
                if db.execute('SELECT 1 FROM reference_completion_recovery WHERE original_sha256=? AND design_sha256=?',
                    (row['image_sha256'],row['design_sha256'])).fetchone():continue
            entries.append({**strategy,'original_sha256':row['image_sha256'],'design_sha256':row['design_sha256'],
                'baseline_attempts':len(attempts),'baseline_image_sha256':attempts[-1]['image_sha256'],
                'baseline_review_sha256':digest(json.loads(attempts[-1]['review']))})
        return {'run_sha256':sha256(run/'run.json'),'entries':entries,
                'patterns':dict(Counter(e['pattern'] for e in entries)),'max_extra_attempts':1}
    finally:db.close()


def activate_references(run,manifest):
    from contextlib import ExitStack
    from bulk_expansion_images import atomic_json,connect,descriptor,lock
    from export_expanded_catalog import accepted_retained
    from image_policy import validate_prompt
    run=Path(run).resolve();manifest=Path(manifest).resolve();plan=json.loads(manifest.read_text());desc=descriptor(run)
    if plan['run_sha256']!=sha256(run/'run.json') or plan['max_extra_attempts']!=1:raise ValueError('Wrong reference recovery run or budget')
    destination=run/'reference-completion-recovery'/sha256(manifest)[:16]
    with ExitStack() as locks:
        for name in ('supervisor','generation','review','reference-review','reference-repair-review'):locks.enter_context(lock(run,name))
        db=connect(run)
        try:
            if destination.exists():raise ValueError('Reference recovery already activated')
            for entry in plan['entries']:
                row=db.execute('SELECT * FROM references_to_review WHERE image_sha256=? AND design_sha256=?',
                    (entry['original_sha256'],entry['design_sha256'])).fetchone()
                if row is None or accepted_retained(db,row,desc['review_identity']):raise ValueError('Reference is missing or already accepted')
                attempts=list(db.execute('SELECT * FROM reference_repairs WHERE original_sha256=? AND design_sha256=? ORDER BY attempt',
                    (row['image_sha256'],row['design_sha256'])))
                if (len(attempts)!=entry['baseline_attempts'] or len(attempts)<3
                        or sha256(Path(attempts[-1]['image_path']))!=entry['baseline_image_sha256']
                        or digest(json.loads(attempts[-1]['review']))!=entry['baseline_review_sha256']
                        or digest(json.loads(row['design']))!=row['design_sha256']):
                    raise ValueError('Reference recovery preview is stale')
                validate_prompt(entry['prompt'])
                if entry['mode']!='generate':raise ValueError('Construction recovery requires a fresh render')
            destination.mkdir(parents=True)
            with closing(sqlite3.connect(destination/'ledger-before.sqlite')) as backup:db.backup(backup)
            atomic_json(destination/'manifest.json',plan)
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS reference_completion_recovery(original_sha256,design_sha256,entry,entry_sha256,PRIMARY KEY(original_sha256,design_sha256))')
                for entry in plan['entries']:
                    db.execute('INSERT INTO reference_completion_recovery VALUES(?,?,?,?)',
                        (entry['original_sha256'],entry['design_sha256'],canonical(entry),digest(entry)))
            result={'queued':len(plan['entries']),'patterns':plan['patterns'],'extra_attempts_per_reference':1,
                    'original_images_changed':0,'backup':str(destination/'ledger-before.sqlite')}
            atomic_json(destination/'receipt.json',result);return result
        finally:db.close()
