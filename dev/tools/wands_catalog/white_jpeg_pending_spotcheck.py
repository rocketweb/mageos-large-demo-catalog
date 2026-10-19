"""Freeze pending-at-checkpoint images into exact, hash-bound review batches."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from html import escape
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image, ImageOps

import white_jpeg_category_policy as policy
import white_jpeg_spotcheck as furniture


def review_html(manifest, manifest_sha):
    html=furniture.HTML
    changes=[
        ('Furniture background spot checks','Remaining-image spot checks'),
        ('Check that the furniture, legs, shelves and solid panels remain intact.',
         'Check that the product, printed surfaces, pale panels and thin edges remain intact.'),
        ('These are proposals grouped by image checks, not newly approved images. Scenes, Room Bundles, known major damage and held glass outlines are excluded.',
         'This is the frozen remaining-image list from the stated checkpoint. It includes risky cutouts for your review. Existing glass-outline holds are shown and kept original.'),
        ('the exact 24 or fewer images','the exact 100 or fewer images'),
        ("key='furniture-review:'","key='remaining-review:'"),
        ('for furniture review ','for remaining-image review '),
        ('Keep marked exceptions original. Shadows may be dropped.',
         'Keep marked exceptions original. Minor cutout changes and lost shadows are acceptable.'),
        ('Dark furniture comes first.','Dark products come first.'),
    ]
    for old,new in changes:
        html=html.replace(old,new)
    marker='const byId=new Map(data.batches.map(x=>[x.id,x]));let current;'
    assert marker in html
    html=html.replace(marker,marker+'''
const itemIds=new Set(data.items.map(x=>x.id)), batchIds=new Set(data.batches.map(x=>x.id));
saved.approved=(Array.isArray(saved.approved)?saved.approved:[]).filter(id=>batchIds.has(id));
saved.exceptions=[...new Set([...(Array.isArray(saved.exceptions)?saved.exceptions:[]).filter(id=>itemIds.has(id)),...data.items.filter(x=>x.lock_original).map(x=>x.id)])];
''')
    old='${data.counts.previously_original} were previously rejected; ${data.counts.pending} were awaiting review; ${data.counts.newly_white} cleared automatic review after the deployed snapshot.'
    assert old in html
    html=html.replace(old,'All were pending at ${data.checkpoint_local}. At gallery creation: ${data.counts.pending} pending, ${data.counts.newly_white} automatically approved white, ${data.counts.previously_original} kept original. ${data.counts.locked_original} existing outline or scene holds are pre-marked Keep original.')
    html=html.replace('data-exception="${x.id}" ${saved.exceptions.includes(x.id)',
        'data-exception="${x.id}" ${x.lock_original?\'disabled\':\'\'} ${saved.exceptions.includes(x.id)')
    html=html.replace('>Keep original</label><details>',
        '>${x.lock_original?\'Keep original: \'+esc(x.lock_reason):\'Keep original\'}</label><details>')
    html=html.replace('<button id="export">Download review marks</button>',
        '<label><input id="approve-sticky" type="checkbox">Approve batch except originals</label><button id="copy-sticky" class="primary">Copy approval request</button><button id="export">Download review marks</button>')
    html=html.replace("document.querySelector('#approve').checked=saved.approved.includes(b.id);",
        "document.querySelector('#approve').checked=saved.approved.includes(b.id);document.querySelector('#approve-sticky').checked=saved.approved.includes(b.id);")
    old="if(e.target.checked)saved.approved.push(current.id);persist()};"
    assert old in html
    html=html.replace(old,"if(e.target.checked)saved.approved.push(current.id);document.querySelector('#approve-sticky').checked=e.target.checked;persist()};")
    html=html.replace("window.addEventListener('hashchange',render);render();",'''
document.querySelector('#approve-sticky').onchange=e=>{document.querySelector('#approve').checked=e.target.checked;document.querySelector('#approve').dispatchEvent(new Event('change'))};
document.querySelector('#copy-sticky').onclick=()=>document.querySelector('#copy').click();
window.addEventListener('hashchange',render);render();''')
    html=html.replace('<p id="scope"></p>', '<p><a href="'+escape(manifest['dashboard_url'],quote=True)+'">Back to image dashboard</a></p><p id="scope"></p>')
    payload=json.dumps({**manifest,'manifest_sha256':manifest_sha},separators=(',',':')).replace('<','\\u003c')
    return html.replace('__PAYLOAD__',payload)


def freeze(job, cutoff, expected):
    """Read one consistent snapshot; reconstruct the previously reported queue."""
    audit=job/'audit-expanded-fast-20261018'
    metadata=json.loads((audit/'image-categories.json').read_text())
    source_root=Path(json.loads((job/'manifest.json').read_text())['originals'])
    with sqlite3.connect((audit/'audit.sqlite3').as_uri()+'?mode=ro',uri=True)as db:
        db.execute('BEGIN')
        rows=db.execute('''SELECT i.file,i.row_json,i.decision,i.reason,f.source_sha256,
            f.output_sha256,f.features,e.review,e.method,e.decided_at,g.verdict
            FROM images i LEFT JOIN category_features f USING(file)
            LEFT JOIN category_evidence e USING(file) LEFT JOIN glass_outline_checks g USING(file)
            WHERE i.decision IS NULL OR (e.method='context_review' AND e.decided_at>?)
            ORDER BY i.file''',(cutoff.timestamp(),)).fetchall()
        directives={r[0]for r in db.execute('SELECT file FROM human_selections')}
    if len(rows)!=expected:
        raise ValueError(f'Checkpoint scope changed: expected {expected}, found {len(rows)}')
    items=[]
    for filename,encoded,decision,reason,src,out,features,review,method,decided_at,glass in rows:
        row=json.loads(encoded);m=json.loads(features);meta=metadata[filename]
        if filename in directives or (src,out)!=(row['source_sha256'],row.get('output_sha256')):
            raise ValueError('Review scope has a human directive or mismatched measurements: '+filename)
        if not row.get('output_file'):
            raise ValueError('Missing white candidate: '+filename)
        original=source_root/filename
        candidate=Path(row.get('output_path')or job/'media/wands-expanded'/row['output_file'])
        if furniture.digest(original)!=row['source_sha256']or furniture.digest(candidate)!=row['output_sha256']:
            raise ValueError('Image hash drift: '+filename)
        lock_reason=''
        if policy.room_bundle(meta):lock_reason='Room Bundle scene'
        elif glass and glass!='preserved':lock_reason='existing glass-outline hold ('+glass+')'
        vote=json.loads(review or'null')or{}
        with Image.open(original)as image:
            pixels=np.asarray(image.convert('RGB').resize((128,128)),dtype=float)
        foreground=np.max(abs(pixels-np.asarray(m['border_median_rgb'])),axis=2)>35
        dark_fraction=float(np.mean(pixels.mean(axis=2)[foreground]<145))if foreground.any()else 0
        items.append({'file':filename,'name':meta.get('name',filename),'skus':meta.get('skus',[]),
            'classes':meta.get('classes',[]),'categories':meta.get('categories',[]),
            'original_path':str(original),'candidate_path':str(candidate),
            'original_url':original.as_uri(),'candidate_url':candidate.as_uri(),
            'source_sha256':row['source_sha256'],'output_sha256':row['output_sha256'],
            'decision_at_checkpoint':None,'decision_at_freeze':decision,
            'reason':reason or'awaiting_context_review','review_note':vote.get('reason'),
            'metrics':{k:m[k]for k in ('backdrop_fit_p90','retained_pixel_agreement','native_edge_retention')},
            'lock_original':bool(lock_reason),'lock_reason':lock_reason,
            'dark_fraction':dark_fraction,'family':(meta.get('classes')or['Uncategorized'])[0]})
    return sorted(items,key=lambda x:(x['dark_fraction']<.5,x['family'],x['name'],x['file']))


def build(job, output, checkpoint, expected=983, batch_size=100):
    cutoff=datetime.fromisoformat(checkpoint)
    if cutoff.tzinfo is None or batch_size!=100:
        raise ValueError('Use a timezone-bound checkpoint and batches of 100')
    items=freeze(job,cutoff,expected)
    output.mkdir(exist_ok=False);(output/'thumbs').mkdir();(output/'sheets').mkdir()
    batches=[]
    for start in range(0,len(items),batch_size):
        chunk=items[start:start+batch_size];batch=f'P{len(batches)+1:03d}'
        for position,item in enumerate(chunk,1):
            item['batch']=batch;item['id']=f'{batch}-{position:03d}'
            for key in ('original','candidate'):
                path=Path('thumbs')/(item['id']+'-'+key+'.jpg')
                with Image.open(item[key+'_path'])as image:
                    thumb=ImageOps.contain(image.convert('RGB'),(440,440))
                    thumb.save(output/path,quality=88)
                item[key+'_thumb']=str(path)
        counts=Counter(i['decision_at_freeze']or'pending'for i in chunk)
        families=list(dict.fromkeys(i['family']for i in chunk))
        label=', '.join(families[:3])+(' and more'if len(families)>3 else'')
        contact=f'sheets/{batch}.jpg'
        furniture.sheet(chunk,output/contact,f'{batch} | {len(chunk)} pairs',columns=4,tile=140)
        batches.append({'id':batch,'label':label,'items':[i['id']for i in chunk],
            'sheet':contact,'previously_original':counts['original'],'pending':counts['pending'],
            'newly_white':counts['white'],'locked_original':[i['id']for i in chunk if i['lock_original']]})
    now=datetime.now(ZoneInfo('America/Indiana/Indianapolis'));counts=Counter(i['decision_at_freeze']or'pending'for i in items)
    manifest={'schema':1,'state':'awaiting_human_approval','run_id':output.name,
        'created_at':now.isoformat(),'created_at_local':now.strftime('%b %d, %Y %I:%M %p %Z'),
        'checkpoint':cutoff.isoformat(),'checkpoint_local':cutoff.strftime('%b %d, %Y %I:%M %p %Z'),
        'batch_size':batch_size,'dashboard_url':(job/'status.html').as_uri(),
        'selection_policy':'Proposals only. Minor cutout changes and lost shadows accepted. Exact human batch approval required. Existing outline and Room Bundle holds stay original. No deployment.',
        'counts':{'previously_original':counts['original'],'pending':counts['pending'],
            'newly_white':counts['white'],'locked_original':sum(i['lock_original']for i in items)},
        'batches':batches,'items':items}
    furniture.write_json(output/'manifest.json',manifest)
    manifest_sha=furniture.digest(output/'manifest.json')
    (output/'index.html').write_text(review_html(manifest,manifest_sha))
    furniture.sheet(items[:6],output/'preview.jpg','First six of the 983-image review'if len(items)==983 else'First six review pairs',columns=2,tile=220)
    receipt={'state':'ready_for_spotcheck','run_id':output.name,'gallery':str(output/'index.html'),
        'manifest':str(output/'manifest.json'),'manifest_sha256':manifest_sha,'pairs':len(items),
        'batches':len(batches),'batch_sizes':[len(b['items'])for b in batches],
        'counts':manifest['counts'],'checkpoint':manifest['checkpoint'],
        'all_pair_hashes_verified':True,'audit_decisions_changed':False,'storefronts_changed':False}
    furniture.write_json(output/'verification.json',receipt)
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--checkpoint',required=True);parser.add_argument('--expected',type=int,default=983)
    args=parser.parse_args()
    print(json.dumps(build(args.job.resolve(),args.output.resolve(),args.checkpoint,args.expected),indent=2))
