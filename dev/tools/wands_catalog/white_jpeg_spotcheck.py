"""Prepare immutable, hash-bound furniture comparison batches for human approval.

Reads the active audit through one SQLite snapshot. Creates review assets only;
never changes image decisions, source files, export pointers, or storefronts.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def font(size):
    return ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', size)


def sheet(items, output, title, columns=3, tile=160):
    width = columns * (tile * 2 + 24)
    row_height = tile + 66
    canvas = Image.new('RGB', (width, math.ceil(len(items) / columns) * row_height + 62), '#eef1f5')
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 8), title, fill='#132238', font=font(22))
    draw.text((12, 36), 'Each pair: ORIGINAL LEFT  |  WHITE CANDIDATE RIGHT', fill='#34455c', font=font(14))
    for n, item in enumerate(items):
        x = (n % columns) * (tile * 2 + 24) + 8
        y = 62 + (n // columns) * row_height
        draw.text((x, y), item['id'], fill='#132238', font=font(16))
        name = item['name']
        while draw.textlength(name, font=font(12)) > tile * 2 + 4:
            name = name[:-2]
        draw.text((x, y + 24), name, fill='#34455c', font=font(12))
        for offset, key in ((0, 'original_path'), (tile + 6, 'candidate_path')):
            with Image.open(item[key]) as source:
                img = ImageOps.contain(source.convert('RGB'), (tile, tile))
            canvas.paste('white', (x + offset, y + 46, x + offset + tile, y + 46 + tile))
            canvas.paste(img, (x + offset + (tile - img.width) // 2, y + 46 + (tile - img.height) // 2))
    canvas.save(output, quality=91, subsampling=0)


HTML = r'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Furniture background spot checks</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#eef1f5;color:#172538;font:16px system-ui,sans-serif}
header,main{max-width:1680px;margin:auto;padding:24px}header{padding-bottom:10px}h1{margin:0 0 10px;font-size:30px}h2{margin:0 0 8px}
p{line-height:1.5;margin:8px 0}a{color:#1150a0}button,select{font:inherit;padding:10px 14px;border:1px solid #b4bdcc;border-radius:7px;background:white;color:#172538;cursor:pointer}button.primary{background:#174f88;color:white}
.bar{position:sticky;top:0;background:#eef1f5f5;z-index:3;border-bottom:1px solid #ccd4df;padding:12px 24px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}.bar select{max-width:450px}.muted{color:#526176;font-size:14px}
.notice{background:#fff8db;border-left:4px solid #bb8b12;padding:12px;margin:14px 0}.batch,.approval{background:white;border-radius:10px;padding:20px;margin-bottom:20px}.approval{border:1px solid #ccd4df}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
article{background:white;border:1px solid #d7dfe9;border-radius:10px;padding:14px;overflow:hidden}article.except{border:3px solid #b14227;padding:12px}article h3{font-size:17px;margin:0 0 5px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:8px}figure{margin:12px 0}figcaption{text-align:center;font-size:13px;font-weight:650;margin-bottom:7px}.pair img{display:block;width:100%;aspect-ratio:1;object-fit:contain;background:white;border:1px solid #e0e5ec}.sku{font-size:12px;overflow-wrap:anywhere;color:#526176}label{cursor:pointer;display:inline-flex;gap:9px;align-items:center}input{width:19px;height:19px}details{margin-top:12px;font-size:13px}summary{cursor:pointer;color:#526176}pre{white-space:pre-wrap;overflow-wrap:anywhere}.crops{display:flex;gap:8px;flex-wrap:wrap}.crops img{max-width:300px;max-height:190px}textarea{width:100%;min-height:110px;font:14px ui-monospace,monospace;padding:10px;margin:12px 0}.actions{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.checks{display:flex;gap:16px;flex-wrap:wrap;margin:12px 0}.good{color:#126239}#storage-warning{color:#9b2c1a}.tiny{font-size:12px}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #e29414;outline-offset:3px}@media(max-width:900px){.grid{grid-template-columns:1fr}.bar{position:static}header,main{padding:16px}h1{font-size:25px}}
</style>
<header><h1>Furniture background spot checks</h1>
<p><strong>Original on the left, proposed white JPG on the right.</strong> Dropped backdrop shadows and minor edge changes are acceptable. Check that the furniture, legs, shelves and solid panels remain intact.</p>
<p id="scope"></p><p class="muted">These are proposals grouped by image checks, not newly approved images. Scenes, Room Bundles, known major damage and held glass outlines are excluded. Click either image for the full-resolution file.</p>
<div class="notice">Approve a batch after spot checking it, and mark any exceptions <strong>Keep original</strong>. This approves only the exact 24 or fewer images listed in that batch, not unseen images. A bad sample means inspect that batch more closely. Your marks stay in this browser; copy the approval request into chat to apply them.</div>
<p id="storage-warning" role="status"></p></header>
<nav class="bar" aria-label="Batch navigation"><button id="prev">← Previous</button><select id="batch" aria-label="Choose a batch"></select><button id="next">Next →</button><span id="progress" class="muted" role="status"></span><button id="export">Download review marks</button></nav>
<main><section id="intro" class="batch"></section><section class="approval"><div class="checks"><label><input id="approve" type="checkbox">Approve this batch, except marked originals</label></div><div class="actions"><button id="copy" class="primary">Copy approval request</button><span id="copy-state" class="muted" role="status"></span></div><textarea id="request" readonly aria-label="Approval request to paste in chat"></textarea><p class="muted">Approval prepares the local image selection. Storefront deployment remains a separate action.</p></section><div id="grid" class="grid"></div></main>
<script id="payload" type="application/json">__PAYLOAD__</script><script>
const data=JSON.parse(document.querySelector('#payload').textContent), key='furniture-review:'+data.manifest_sha256;
let saved={approved:[],exceptions:[]}, storage=true;
try{saved=JSON.parse(localStorage.getItem(key))||saved}catch(e){storage=false;document.querySelector('#storage-warning').textContent='Browser storage is unavailable. Download your review marks before closing this page.'}
const byId=new Map(data.batches.map(x=>[x.id,x]));let current;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
document.querySelector('#scope').textContent=`${data.items.length.toLocaleString()} comparison pairs in ${data.batches.length} batches, frozen ${data.created_at_local}. Dark furniture comes first. ${data.counts.previously_original} were previously rejected; ${data.counts.pending} were awaiting review; ${data.counts.newly_white} cleared automatic review after the deployed snapshot.`;
document.querySelector('#batch').innerHTML=data.batches.map(b=>`<option value="${b.id}">${b.id} · ${esc(b.label)} · ${b.items.length} pairs</option>`).join('');
function persist(){if(storage){try{localStorage.setItem(key,JSON.stringify(saved))}catch(e){storage=false;document.querySelector('#storage-warning').textContent='Could not save browser marks. Download review marks before closing.'}}requestText()}
function approvalText(){const approved=data.batches.filter(b=>saved.approved.includes(b.id));if(!approved.length)return 'Select “Approve this batch” for each batch you approve. Then copy this request.';let lines=['Approve local white-JPG selection for furniture review '+data.run_id+' (manifest '+data.manifest_sha256+').'];for(const b of approved){const exceptions=b.items.filter(id=>saved.exceptions.includes(id));lines.push('Approve '+b.id+(exceptions.length?' except '+exceptions.join(', '):' with no exceptions')+'.')}lines.push('Keep marked exceptions original. Shadows may be dropped. Do not deploy these new approvals yet.');return lines.join('\n')}
function requestText(){document.querySelector('#request').value=approvalText();const n=data.items.filter(x=>saved.approved.includes(x.batch)&&!saved.exceptions.includes(x.id)).length;document.querySelector('#progress').textContent=`${saved.approved.length} batches marked approved · ${n} proposed white · ${saved.exceptions.length} exceptions`}
function render(){const b=byId.get(location.hash.slice(1))||data.batches[0];if(!b)return;current=b;document.querySelector('#batch').value=b.id;document.querySelector('#approve').checked=saved.approved.includes(b.id);document.querySelector('#intro').innerHTML=`<h2>${b.id}: ${esc(b.label)}</h2><p>${b.items.length} exact pairs. Original left, candidate right. <a href="${esc(b.sheet)}" target="_blank">Open full batch contact sheet</a></p><p class="muted">${b.previously_original} previously rejected · ${b.pending} pending · ${b.newly_white} now automatically cleared. Suggested spot check: first, middle and last, plus any pair that catches your eye.</p>`;
const members=data.items.filter(x=>x.batch===b.id);document.querySelector('#grid').innerHTML=members.map(x=>`<article id="${x.id}" class="${saved.exceptions.includes(x.id)?'except':''}"><h3>${x.id} · ${esc(x.name)}</h3><div class="sku">${esc(x.skus.slice(0,3).join(' · '))}${x.skus.length>3?' · +'+(x.skus.length-3)+' more':''}</div><div class="pair"><figure><figcaption>Original</figcaption><a href="${esc(x.original_url)}" target="_blank"><img src="${x.original_thumb}" alt="Original ${esc(x.name)}" loading="lazy"></a></figure><figure><figcaption>White candidate</figcaption><a href="${esc(x.candidate_url)}" target="_blank"><img src="${x.candidate_thumb}" alt="White candidate ${esc(x.name)}" loading="lazy"></a></figure></div><label><input type="checkbox" data-exception="${x.id}" ${saved.exceptions.includes(x.id)?'checked':''}>Keep original</label><details><summary>Why this was held / image checks</summary><p>${esc(x.reason.replaceAll('_',' '))}</p><p>${esc(x.review_note||'No completed context review at batch creation.')}</p><p>Backdrop fit ${x.metrics.backdrop_fit_p90.toFixed(1)} · retained pixel agreement ${(x.metrics.retained_pixel_agreement*100).toFixed(1)}% · edge retention ${(x.metrics.native_edge_retention*100).toFixed(1)}%. These scores do not prove intact product structure.</p><p class="tiny">Source SHA-256: ${x.source_sha256}<br>Candidate SHA-256: ${x.output_sha256}</p></details></article>`).join('');document.querySelectorAll('[data-exception]').forEach(el=>el.onchange=()=>{saved.exceptions=saved.exceptions.filter(id=>id!==el.dataset.exception);if(el.checked)saved.exceptions.push(el.dataset.exception);el.closest('article').classList.toggle('except',el.checked);persist()});document.querySelector('#prev').disabled=b===data.batches[0];document.querySelector('#next').disabled=b===data.batches.at(-1);requestText()}
document.querySelector('#approve').onchange=e=>{saved.approved=saved.approved.filter(x=>x!==current.id);if(e.target.checked)saved.approved.push(current.id);persist()};
document.querySelector('#batch').onchange=e=>location.hash=e.target.value;
for(const [id,step]of [['prev',-1],['next',1]])document.querySelector('#'+id).onclick=()=>{location.hash=data.batches[data.batches.indexOf(current)+step].id;window.scrollTo(0,0)};
document.querySelector('#copy').onclick=async()=>{const el=document.querySelector('#request');try{await navigator.clipboard.writeText(el.value);document.querySelector('#copy-state').textContent='Copied. Paste into chat to apply.'}catch(e){el.focus();el.select();document.querySelector('#copy-state').textContent='Request selected. Press Command-C, then paste into chat.'}};
document.querySelector('#export').onclick=()=>{const blob=new Blob([JSON.stringify({schema:1,run_id:data.run_id,manifest_sha256:data.manifest_sha256,...saved},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=data.run_id+'-review-marks.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
window.addEventListener('hashchange',render);render();
</script></html>'''


def build(job, output, deployed_selection):
    audit = job / 'audit-expanded-fast-20261018'
    originals = job.parent / 'accepted-export-completion-20261003/media/wands-expanded'
    output.mkdir(parents=True, exist_ok=False)
    (output / 'thumbs').mkdir(); (output / 'sheets').mkdir()
    meta = json.loads((audit / 'image-categories.json').read_text())
    with deployed_selection.open() as stream:
        live_originals = {r['original_file'] for r in csv.DictReader(stream) if r['action'] == 'original'}
    db = sqlite3.connect((audit / 'audit.sqlite3').as_uri() + '?mode=ro', uri=True)
    db.execute('BEGIN')
    rows = db.execute('''SELECT i.file,i.row_json,i.decision,i.reason,f.features,e.review,
        g.verdict FROM images i LEFT JOIN category_features f USING(file)
        LEFT JOIN category_evidence e USING(file) LEFT JOIN glass_outline_checks g USING(file)
        ORDER BY i.file''').fetchall()
    db.close()
    skipped = collections.Counter(); candidates = []; scope = collections.Counter()
    excluded = []
    for filename, raw, decision, reason, features, review, glass in rows:
        product = meta.get(filename, {})
        if filename not in live_originals or not any('/Furniture/' in x for x in product.get('categories', [])):
            continue
        scope[decision or 'pending'] += 1
        row = json.loads(raw); metrics = json.loads(features or '{}'); vote = json.loads(review or 'null') or {}
        text = ' '.join([product.get('name','')] + product.get('classes', [])).casefold()
        reject = None
        if glass and glass != 'preserved': reject = 'held_glass_outline'
        elif re.search(r'glass|mirror|transparent|acrylic|chair\s?mat|\bclear\b', text): reject = 'reflective_or_transparent_product'
        elif re.search(r'\bsets?\b|\b[2-9]\s*-?\s*piece\b|room bundle|bedding', text): reject = 'multiple_objects_or_set'
        elif not row.get('output_file') or row.get('warning'): reject = 'missing_or_flagged_candidate'
        elif vote.get('major_product_damage') is True: reject = 'existing_major_damage_review'
        elif vote.get('background') in ('scene','uncertain'): reject = 'scene_or_uncertain_background'
        elif not metrics or any(not isinstance(metrics.get(k), (int,float)) or not math.isfinite(metrics[k]) for k in ('backdrop_fit_p90','border_edge_fraction','white_border','retained_pixel_agreement','native_edge_retention','visible_fraction')): reject = 'incomplete_measurements'
        elif metrics['backdrop_fit_p90'] > 16 or metrics['border_edge_fraction'] > .04: reject = 'nonuniform_backdrop_checks'
        elif metrics['white_border'] < .98 or metrics['visible_fraction'] < .025: reject = 'weak_candidate_visibility_or_background'
        elif metrics['retained_pixel_agreement'] < .95 or metrics['native_edge_retention'] < .60: reject = 'larger_product_change_needs_close_review'
        elif sum(255-v for v in metrics.get('border_median_rgb', [255,255,255])) < 18: reject = 'already_near_white_background'
        if reject:
            skipped[reject] += 1; excluded.append({'file':filename,'reason':reject,'name':product.get('name'), 'decision':decision})
            continue
        source = originals / filename
        candidate = Path(row.get('output_path') or job / 'media/wands-expanded' / row['output_file'])
        if not source.is_file() or not candidate.is_file():
            raise FileNotFoundError((source,candidate))
        if digest(source) != row['source_sha256'] or digest(candidate) != row['output_sha256']:
            raise ValueError('Image hash drift: '+filename)
        with Image.open(candidate) as image:
            pixels = np.asarray(image.convert('RGB').resize((128,128)),dtype=float)
            foreground = pixels.min(axis=2) < 225
            luma = pixels.mean(axis=2)
            dark_fraction = float(np.mean(luma[foreground] < 145)) if foreground.any() else 0
        dark = dark_fraction >= .5
        family = (product.get('classes') or ['Furniture'])[0]
        candidates.append({'file':filename,'name':product.get('name',filename),'skus':product.get('skus',[]),
            'classes':product.get('classes',[]),'categories':product.get('categories',[]),
            'original_path':str(source),'candidate_path':str(candidate),
            'original_url':source.as_uri(),'candidate_url':candidate.as_uri(),
            'source_sha256':row['source_sha256'],'output_sha256':row['output_sha256'],
            'decision_at_freeze':decision,'reason':reason or 'awaiting_context_review',
            'review_note':vote.get('reason'),'metrics':{k:metrics[k] for k in ('backdrop_fit_p90','retained_pixel_agreement','native_edge_retention')},
            'dark_fraction':dark_fraction,'group':'Dark furniture' if dark else 'Other furniture',
            'family':family})
    # Similar classes stay together; class boundaries start new review batches.
    candidates.sort(key=lambda x:(0 if x['group']=='Dark furniture' else 1,x['family'],x['name'],x['file']))
    batches=[]; items=[]
    for (group,family), members in __import__('itertools').groupby(candidates,key=lambda x:(x['group'],x['family'])):
        members=list(members)
        for start in range(0,len(members),24):
            batch_id=f'F{len(batches)+1:03d}'; chunk=members[start:start+24]
            for position,item in enumerate(chunk,1):
                item['batch']=batch_id; item['id']=f'{batch_id}-{position:02d}'
                for key,pathkey in (('original','original_path'),('candidate','candidate_path')):
                    thumb=Path('thumbs')/(item['id']+'-'+key+'.jpg')
                    with Image.open(item[pathkey]) as image:
                        image=ImageOps.contain(image.convert('RGB'),(440,440))
                        image.save(output/thumb,quality=88)
                    item[key+'_thumb']=str(thumb)
                items.append(item)
            counts=collections.Counter(x['decision_at_freeze'] or 'pending' for x in chunk)
            image_path=f'sheets/{batch_id}.jpg'
            sheet(chunk,output/image_path,f'{batch_id} | {group} | {family}')
            batches.append({'id':batch_id,'label':f'{group} / {family}','items':[x['id'] for x in chunk],
                'sheet':image_path,'previously_original':counts['original'],'pending':counts['pending'],'newly_white':counts['white']})
    now=datetime.now(timezone.utc)
    counts=collections.Counter(x['decision_at_freeze'] or 'pending' for x in items)
    manifest={'schema':1,'state':'awaiting_human_approval','run_id':output.name,
        'created_at':now.isoformat(),'created_at_local':now.astimezone().strftime('%b %d, %Y %I:%M %p %Z'),
        'deployed_selection':str(deployed_selection),'deployed_selection_sha256':digest(deployed_selection),
        'selection_policy':'Proposals only. User accepts dropped cast shadows and minor cutout changes. Human batch approval required.',
        'counts':{'scope':dict(scope),'excluded':dict(skipped),'previously_original':counts['original'],
            'pending':counts['pending'],'newly_white':counts['white']},'batches':batches,'items':items}
    write_json(output/'manifest.json',manifest)
    write_json(output/'excluded.json',excluded)
    manifest_hash=digest(output/'manifest.json')
    payload=json.dumps({**manifest,'manifest_sha256':manifest_hash},separators=(',',':')).replace('<','\\u003c')
    (output/'index.html').write_text(HTML.replace('__PAYLOAD__',payload))
    for batch in batches[:3]:
        members=[i for i in items if i['batch']==batch['id']]
        sheet(members[:6],output/f"{batch['id']}-preview.jpg",f"{batch['id']} | first 6 of {len(members)} pairs",columns=2,tile=220)
    receipt={'state':'ready_for_spotcheck','run_id':output.name,'gallery':str(output/'index.html'),
        'manifest':str(output/'manifest.json'),'manifest_sha256':manifest_hash,'pairs':len(items),'batches':len(batches),
        'first_batches':[{k:b[k] for k in ('id','label','previously_original','pending','newly_white')} for b in batches[:5]],
        'counts':manifest['counts'],'all_pair_hashes_verified':True,'audit_decisions_changed':False,'storefronts_changed':False}
    write_json(output/'verification.json',receipt)
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--deployed-selection',type=Path,required=True)
    args=parser.parse_args()
    build(args.job.resolve(),args.output.resolve(),args.deployed_selection.resolve())
