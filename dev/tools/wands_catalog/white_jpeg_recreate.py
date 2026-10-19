"""Track built-in imagegen replacements without changing catalog selections."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
from html import escape
import json
from pathlib import Path
import shutil
import time

from PIL import Image, ImageStat


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def write(path, value):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');temp.replace(path)


def jobs(queue):
    status=read(queue/'status.json')
    if sha(queue/'jobs.jsonl')!=status['jobs_sha256']:
        raise ValueError('Recreation queue hash changed')
    result=[json.loads(line)for line in(queue/'jobs.jsonl').read_text().splitlines()]
    if len(result)!=87 or len({x['id']for x in result})!=87:
        raise ValueError('Expected the 87 distinct authorized originals')
    return result


def render(queue):
    source=jobs(queue);records={j['id']:read(queue/'generation-records'/(j['id']+'.json'),{})for j in source}
    state=read(queue/'status.json');done=[x for x in records.values()if x.get('state')=='awaiting_review']
    active=[x for x in records.values()if x.get('state')=='generating'];errors=[x for x in records.values()if x.get('state')=='needs_attention']
    terminal=len(done)+len(errors)==len(source) and not active
    state.update(total=87,completed=len(done),awaiting_review=len(done),running=len(active),
        queued=87-len(done)-len(active)-len(errors),failed=len(errors),updated_at=time.time(),
        generation_mode='built-in imagegen',review_gallery=str(queue/'review.html'),
        state=('ready_for_review_with_exceptions' if errors else 'ready_for_review') if terminal else 'generating' if active or done else 'queued')
    write(queue/'status.json',state)
    items=[]
    for n,j in enumerate(source,1):
        r=records[j['id']]
        items.append({'id':f'RE{n:03d}','batch':f'R{(n-1)//24+1:02d}','previous_review_id':j['review_item_id'],
            'name':j['name'],'skus':j['skus'],'original_url':Path(j['original_reference']).as_uri(),
            'original_path':j['original_reference'],'source_sha256':j['original_sha256'],
            'rejected_url':Path(j['rejected_candidate']).as_uri(),'state':r.get('state','queued'),
            'replacement_url':Path(r['jpeg_path']).as_uri() if r.get('jpeg_path') else None,
            'replacement_path':r.get('jpeg_path'),'replacement_sha256':r.get('jpeg_sha256'),
            'native_generated_path':r.get('native_path'),'prompt_file':r.get('prompt_file'),
            'format_checks':r.get('format_checks')})
    manifest={'schema':1,'run_id':'white-recreation-20261019-A','queue_sha256':state['jobs_sha256'],
        'generation_mode':'built-in imagegen','state':state['state'],'items':items,
        'review_required_before_selection':True,'selection_changed':False,'deployment_changed':False}
    write(queue/'review-manifest.json',manifest)
    payload=json.dumps({**manifest,'manifest_sha256':sha(queue/'review-manifest.json'),
        'completed':len(done),'running':len(active),'queued':state['queued'],'failed':len(errors)},separators=(',',':')).replace('<','\\u003c')
    template=r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Recreated furniture review</title>
<style>*{box-sizing:border-box}body{font:16px system-ui;background:#eef1f5;color:#172538;margin:0}header,main{max-width:1680px;margin:auto;padding:24px}h1{margin:0 0 12px}p{line-height:1.5}a{color:#1150a0}.bar{position:sticky;top:0;background:#eef1f5f5;z-index:2;padding:12px 24px;border-bottom:1px solid #ccd4df;display:flex;gap:12px;align-items:center;flex-wrap:wrap}button,select{font:inherit;border:1px solid #aeb9c8;background:white;border-radius:7px;padding:10px;cursor:pointer}button:disabled{opacity:.5;cursor:default}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}article,.approval{background:white;border:1px solid #d7dfe9;border-radius:10px;padding:16px;margin-bottom:18px}article h2{font-size:17px;margin:0 0 8px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:8px}figure{margin:8px 0}figcaption{text-align:center;font-size:14px;margin-bottom:6px}.pair img{width:100%;aspect-ratio:1;object-fit:contain;background:white;border:1px solid #e0e5ec}.placeholder{aspect-ratio:1;display:grid;place-items:center;background:#f6f7fa;color:#556479;border:1px dashed #c0cad6}.muted,small{font-size:13px;color:#526176}label{display:flex;gap:9px;align-items:center;margin:10px 0}input{width:19px;height:19px}textarea{width:100%;min-height:150px;margin-top:12px;font:13px ui-monospace,monospace;padding:10px}details{margin-top:12px}details img{max-width:350px;width:100%}.except{border:3px solid #b14227;padding:14px}.status{padding:12px;background:#fff8db;border-left:4px solid #bb8b12}button:focus-visible,a:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid #e29414;outline-offset:3px}@media(max-width:900px){.grid{grid-template-columns:1fr}.bar{position:static}header,main{padding:16px}}</style>
<header><h1>Recreated furniture: review replacements</h1><p><strong>Original left, newly recreated white-background JPG right.</strong> Each product was recreated with built-in imagegen using its own original reference. Inspect geometry, shelves, panels, materials and transparent outlines. Minor differences can occur in a recreation.</p><p id="progress" class="status"></p><p>All 87 catalog selections remain original during this review. Replacements are separate files. <strong>No deployment has occurred.</strong></p><p><a href="index.html">Original recreation queue and rejected cutouts</a> | <a href="review-manifest.json">Replacement manifest</a></p></header>
<nav class="bar" aria-label="Review batches"><button id="prev">← Previous</button><select id="batch" aria-label="Choose review batch"></select><button id="next">Next →</button><button onclick="location.reload()">Refresh progress</button><span id="marks" class="muted"></span></nav>
<main><section class="approval"><h2 id="batch-title"></h2><p>Spot check the batch and mark any exceptions Keep original. Images without a replacement automatically keep their originals. Approval controls unlock when generation finishes, with a frozen manifest identifying the exact replacement files.</p><label><input type="checkbox" id="approve">Approve this review batch except marked originals</label><button id="copy">Copy review approval request</button><span id="copy-state" class="muted" role="status"></span><textarea id="request" readonly aria-label="Review approval request"></textarea></section><div id="grid" class="grid"></div></main>
<script id="payload" type="application/json">__DATA__</script><script>
const data=JSON.parse(document.querySelector('#payload').textContent),batches=[...new Set(data.items.map(x=>x.batch))],key='recreated-review:'+data.run_id+':'+data.manifest_sha256,ready=['ready_for_review','ready_for_review_with_exceptions'].includes(data.state);let saved={approved:[],exceptions:[]},current;
try{saved=JSON.parse(localStorage.getItem(key))||saved}catch(e){}
const isException=x=>!x.replacement_sha256||saved.exceptions.includes(x.id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
document.querySelector('#progress').textContent=`${data.completed} of 87 recreated and awaiting review · ${data.running} generating · ${data.queued} queued · ${data.failed} blocked or failed. ${ready?'Generation finished. Available replacements are ready for review; unavailable images keep originals.':'Refresh this page for new results.'}`;
document.querySelector('#batch').innerHTML=batches.map(b=>`<option value="${b}">${b} · ${data.items.filter(x=>x.batch===b).length} pairs</option>`).join('');
function request(){const approved=data.items.filter(x=>saved.approved.includes(x.batch)&&!isException(x));document.querySelector('#marks').textContent=`${approved.length} replacements marked approved · ${data.items.filter(isException).length} exceptions`;document.querySelector('#request').value=!ready?'Generation is still running. Approval requests unlock when the final manifest is ready.':!saved.approved.length?'Choose the review batches you approve, then copy the request into chat.':`Approve local recreated-image selection for ${data.run_id} (manifest ${data.manifest_sha256}).\n`+batches.filter(b=>saved.approved.includes(b)).map(b=>{const exceptions=data.items.filter(x=>x.batch===b&&isException(x)).map(x=>x.id);return `Approve ${b}${exceptions.length?' except '+exceptions.join(', '):' with no exceptions'}.`}).join('\n')+'\nKeep exceptions original. Do not deploy yet.'}
function persist(){try{localStorage.setItem(key,JSON.stringify(saved))}catch(e){}request()}
function render(){current=batches.includes(location.hash.slice(1))?location.hash.slice(1):batches[0];const rows=data.items.filter(x=>x.batch===current);document.querySelector('#batch').value=current;document.querySelector('#batch-title').textContent=`${current}: ${rows.length} original/replacement pairs`;document.querySelector('#approve').disabled=!ready;document.querySelector('#approve').checked=saved.approved.includes(current);document.querySelector('#copy').disabled=!ready;document.querySelector('#grid').innerHTML=rows.map(x=>`<article id="${x.id}" class="${isException(x)?'except':''}"><h2>${x.id} · ${esc(x.name)}</h2><p class="muted">Previous review ${x.previous_review_id} · ${esc(x.skus.slice(0,3).join(' · '))}</p><div class="pair"><figure><figcaption>Original</figcaption><a href="${esc(x.original_url)}" target="_blank"><img src="${esc(x.original_url)}" alt="Original ${esc(x.name)}" loading="lazy"></a></figure><figure><figcaption>Recreated on white</figcaption>${x.replacement_url?`<a href="${esc(x.replacement_url)}" target="_blank"><img src="${esc(x.replacement_url)}" alt="Recreated ${esc(x.name)}" loading="lazy"></a>`:`<div class="placeholder">${x.state==='needs_attention'?'Generation blocked; original retained':esc(x.state.replaceAll('_',' '))}</div>`}</figure></div><label><input type="checkbox" data-exception="${x.id}" ${isException(x)?'checked':''} ${!x.replacement_sha256?'disabled':''}>Keep original</label><details><summary>Previously rejected cutout</summary><a href="${esc(x.rejected_url)}" target="_blank"><img src="${esc(x.rejected_url)}" alt="Previously rejected cutout" loading="lazy"></a></details></article>`).join('');document.querySelectorAll('[data-exception]').forEach(el=>el.onchange=()=>{saved.exceptions=saved.exceptions.filter(x=>x!==el.dataset.exception);if(el.checked)saved.exceptions.push(el.dataset.exception);el.closest('article').classList.toggle('except',el.checked);persist()});document.querySelector('#prev').disabled=current===batches[0];document.querySelector('#next').disabled=current===batches.at(-1);request()}
document.querySelector('#approve').onchange=e=>{saved.approved=saved.approved.filter(x=>x!==current);if(e.target.checked)saved.approved.push(current);persist()};document.querySelector('#batch').onchange=e=>location.hash=e.target.value;
for(const[id,step]of[['prev',-1],['next',1]])document.querySelector('#'+id).onclick=()=>{location.hash=batches[batches.indexOf(current)+step];scrollTo(0,0)};
document.querySelector('#copy').onclick=async()=>{const el=document.querySelector('#request');try{await navigator.clipboard.writeText(el.value);document.querySelector('#copy-state').textContent=' Copied. Paste into chat.'}catch(e){el.focus();el.select();document.querySelector('#copy-state').textContent=' Press Command-C, then paste into chat.'}};window.addEventListener('hashchange',render);render();
</script></html>'''
    text=template.replace('__DATA__',payload)
    if state.get('reviewed_approved'):
        text=text.replace('All 87 catalog selections remain original during this review. Replacements are separate files. <strong>No deployment has occurred.</strong>',
            '<strong>Review approved: '+str(state['reviewed_approved'])+' recreated JPGs selected locally.</strong> RE066 retains its original in the image audit and its product is excluded from the cleaned catalog. Original files are intact. <strong>No deployment has occurred.</strong>')
    temp=queue/'review.tmp.html';temp.write_text(text);temp.replace(queue/'review.html')
    return {k:state[k]for k in ('state','completed','running','queued','failed')}


def record(queue, job_id, generated, prompt_file):
    job=next(x for x in jobs(queue)if x['id']==job_id)
    target=queue/'generation-records'/(job_id+'.json')
    if read(target,{}).get('state')=='awaiting_review':
        raise ValueError('Replacement already exists; create a new version explicitly')
    if sha(job['original_reference'])!=job['original_sha256']:
        raise ValueError('Original image changed')
    native=queue/'outputs'/(job_id+'-native-v1'+generated.suffix)
    jpeg=queue/'outputs'/(job_id+'-v1.jpg')
    if native.exists() or jpeg.exists():raise FileExistsError('Refusing to overwrite output')
    shutil.copy2(generated,native)
    with Image.open(job['original_reference'])as original:dimensions=original.size
    with Image.open(native)as original_generated:
        native_dimensions=original_generated.size
        image=original_generated.convert('RGB')
        if image.size!=dimensions:image=image.resize(dimensions,Image.Resampling.LANCZOS)
        # Encoding only. The background and product are generated by imagegen.
        image.save(jpeg,format='JPEG',quality=90,subsampling=0)
    with Image.open(jpeg)as check:
        check.load();assert check.mode=='RGB'and check.size==dimensions and check.format=='JPEG'
        w,h=check.size
        corners=[list(ImageStat.Stat(check.crop(box)).mean)for box in ((0,0,8,8),(w-8,0,w,8),(0,h-8,8,h),(w-8,h-8,w,h))]
    result={'id':job_id,'state':'awaiting_review','completed_at':time.time(),
        'native_path':str(native),'native_sha256':sha(native),'native_dimensions':native_dimensions,
        'jpeg_path':str(jpeg),'jpeg_sha256':sha(jpeg),'source_sha256':job['original_sha256'],
        'original_hash_verified':True,'generation_mode':'built-in imagegen','generated_source_path':str(generated),
        'prompt_file':str(prompt_file),'prompt_sha256':sha(prompt_file),
        'format_checks':{'mode':'RGB','format':'JPEG','quality':90,'dimensions':dimensions,'corner_rgb_means':corners},
        'selection_changed':False,'deployment_changed':False,'user_review_required':True}
    write(target,result)
    return render(queue)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['refresh','start','record','fail'])
    parser.add_argument('--queue',type=Path,required=True)
    parser.add_argument('--id');parser.add_argument('--generated',type=Path);parser.add_argument('--prompt-file',type=Path);parser.add_argument('--error')
    args=parser.parse_args();queue=args.queue.resolve()
    (queue/'outputs').mkdir(exist_ok=True);(queue/'generation-records').mkdir(exist_ok=True)
    with (queue/'generation.lock').open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if args.command=='record':
            result=record(queue,args.id,args.generated.resolve(),args.prompt_file.resolve())
        elif args.command in ('start','fail'):
            if args.id not in {x['id']for x in jobs(queue)}:raise ValueError('Unknown recreation job')
            path=queue/'generation-records'/(args.id+'.json');old=read(path,{})
            if old.get('state')=='awaiting_review':raise ValueError('Replacement is already complete')
            write(path,{**old,'id':args.id,'state':'generating'if args.command=='start'else'needs_attention',
                'started_at':time.time(),'error':args.error})
            result=render(queue)
        else:result=render(queue)
    print(json.dumps(result))
