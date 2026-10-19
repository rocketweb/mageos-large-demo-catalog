"""Track new, text-only product images; never decode or reference source photos."""
import argparse
from collections import Counter
import csv
import fcntl
import hashlib
from html import unescape
import json
from pathlib import Path
import re
import shutil
import sqlite3
import time

from PIL import Image,ImageStat


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,data):
    path=Path(path);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n');temp.replace(path)
def jobs(queue):
    state=read(queue/'status.json')
    if sha(queue/'jobs.json')!=state['jobs_sha256']:raise ValueError('Text-only recreation queue changed')
    return read(queue/'jobs.json')
def plain(value):return re.sub(r'\s+',' ',unescape(re.sub('<[^>]+>',' ',value or''))).strip()

def prompt(item):
    attrs='; '.join(k.replace('lab_spec_','').replace('wands_','').replace('_',' ')+': '+v for k,v in item['visual_attributes'].items())
    return f'''Use case: product-mockup
Asset type: one new ecommerce catalog product photograph.
Primary request: Generate a NEW product image from scratch using ONLY this written catalog specification. Do not use or reference any earlier conversation images, original photos, or rejected cutouts. This is not a background edit.
Subject: {item['name']}
Catalog description: {item['description']}
Visual attributes: {attrs or 'Use the product name and description.'}
Style: photorealistic studio product photography, believable construction and surface texture.
Background: perfectly pure white RGB 255 255 255 across the entire canvas, corners and open spaces around the product. No beige, yellow, cream, gray backdrop, gradients, rooms, scenery or environment. Neutral white balance.
Composition: square canvas, the complete named product centered, all parts inside the frame with clear white margins, large enough to inspect. Show a practical three-quarter view for furniture and a front view for flat printed or wall-mounted products. Include only components explicitly belonging to the named product or product set; no decorative staging props.
Product details: retain visible solid panels, upholstery, artwork and pale materials as real product surfaces. Do not turn product material into white holes. All legs, rails, rims and outlines must be complete and clearly defined. If transparent PVC, acrylic or glass is named, make its complete outer silhouette visible through subtle neutral edge reflections against white. Do not erase the transparent product.
Shadows: none or very faint neutral contact shadow; no warm cast or large floor shadows.
Text: no added captions, names, SKU, brand logos, watermarks, measurements, units, rulers, annotations, arrows or diagrams. Dimensions in the specification describe physical proportions only. Printed imagery intrinsic to the named product may be illustrated; do not add unrelated text.
Output: ONE product photo, not a comparison, collage, contact sheet or multi-panel image.'''

def prepare(job,queue):
    receipt=read(job/'human-approvals/remaining-spotcheck-20261019-A/applied.json')
    plan=read(job/'human-approvals/remaining-spotcheck-20261019-A/plan.json')
    assert receipt['white']==869 and receipt['original_exceptions']==114
    exceptions=[i for i in plan['items']if i['decision']=='original'];wanted={s for i in exceptions for s in i['skus']}
    current=read(job/'local-catalog.json');products={};sources={}
    for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv','6-qa.csv'):
        path=Path(current['data'])/name;sources[str(path)]=sha(path)
        with path.open(newline='')as f:
            for row in csv.DictReader(f):
                if row['sku']in wanted:products[row['sku']]=row
    queue.mkdir(exist_ok=False)
    for sub in ('prompts','outputs','records'): (queue/sub).mkdir()
    visual=('color','wands_material','wands_finish','wands_size','wands_piece_count','wands_pack_size',
        'lab_spec_color','lab_spec_finish','lab_spec_material','lab_spec_frame_material','lab_spec_upholstery',
        'lab_spec_pattern','lab_spec_shape','lab_spec_style','lab_spec_width_cm','lab_spec_height_cm','lab_spec_depth_cm','lab_spec_length_cm')
    result=[]
    with sqlite3.connect((job/'audit-expanded-fast-20261018/audit.sqlite3').as_uri()+'?mode=ro',uri=True)as db:
        for n,item in enumerate(exceptions,1):
            product=next((products[s]for s in item['skus']if s in products),None)
            if not product:raise ValueError('Missing product metadata: '+item['id'])
            feature=json.loads(db.execute('SELECT features FROM category_features WHERE file=?',(item['file'],)).fetchone()[0])
            glass=db.execute('SELECT verdict FROM glass_outline_checks WHERE file=?',(item['file'],)).fetchone()
            original_sha=sha(item['original_path'])
            if original_sha!=item['source_sha256']:raise ValueError('Source hash changed')
            entry={'id':f'NR{n:03d}','previous_review_id':item['id'],'batch':f'N{(n-1)//24+1:02d}',
                'name':product['name'],'skus':item['skus'],'file':item['file'],
                'description':plain(product.get('description','').split('<section')[0])[:1200],
                'visual_attributes':{k:plain(product[k])for k in visual if product.get(k)},
                'source_sha256':original_sha,'original_path':item['original_path'],
                'rejected_candidate_path':item['candidate_path'],'rejected_candidate_sha256':item['output_sha256'],
                'dimensions':feature['dimensions'],'generation_mode':'built-in imagegen, text only',
                'reference_images':[],'source_image_decoded':False,'original_outline_hold':glass[0]if glass else None}
            text=prompt(entry);path=queue/'prompts'/(entry['id']+'.txt');path.write_text(text+'\n')
            entry['prompt_file']=str(path);entry['prompt_sha256']=sha(path);result.append(entry)
    write(queue/'jobs.json',result)
    write(queue/'status.json',{'state':'queued','run_id':'text-recreation-remaining-20261019-A','total':len(result),
        'jobs_sha256':sha(queue/'jobs.json'),'metadata_sources':sources,'created_at':time.time(),
        'original_images_viewed':False,'reference_images_used':False,'selection_changed':False,'deployed':False})
    render(queue)

def render(queue):
    source=jobs(queue);records={j['id']:read(queue/'records'/(j['id']+'.json'))if(queue/'records'/(j['id']+'.json')).exists()else{'state':'queued'}for j in source}
    counts=Counter(r['state']for r in records.values());status=read(queue/'status.json')
    complete=counts['awaiting_review']+counts['needs_attention']==len(source)
    status.update(completed=counts['awaiting_review'],running=counts['generating'],queued=counts['queued'],
        failed=counts['needs_attention'],updated_at=time.time(),state=('ready_for_review_with_exceptions'if counts['needs_attention']else'ready_for_review')if complete else'generating'if counts['generating']or counts['awaiting_review']else'queued',
        review_gallery=str(queue/'review.html'))
    write(queue/'status.json',status)
    items=[]
    for j in source:
        r=records[j['id']]
        items.append({**{k:j[k]for k in ('id','batch','previous_review_id','name','skus','source_sha256','original_path','description','visual_attributes','prompt_file','original_outline_hold')},
            'state':r['state'],'replacement_path':r.get('jpeg_path'),'replacement_sha256':r.get('jpeg_sha256'),
            'replacement_url':Path(r['jpeg_path']).as_uri()if r.get('jpeg_path')else None,
            'rejected_url':Path(j['rejected_candidate_path']).as_uri()})
    manifest={'schema':1,'run_id':status['run_id'],'state':status['state'],'queue_sha256':status['jobs_sha256'],
        'items':items,'review_required_before_selection':True,'reference_images_used':False,'original_images_viewed':False,
        'selection_changed':False,'deployment_changed':False}
    write(queue/'review-manifest.json',manifest)
    public_items=[{k:v for k,v in item.items()if k not in ('original_path','rejected_url')}for item in items]
    payload=json.dumps({**manifest,'items':public_items,'manifest_sha256':sha(queue/'review-manifest.json'),
        'completed':status['completed'],'running':status['running'],'queued':status['queued'],'failed':status['failed']},separators=(',',':')).replace('<','\\u003c')
    template=Path(__file__).with_name('white_jpeg_text_review.html').read_text()
    body=template.replace('__PAYLOAD__',payload)
    if status.get('reviewed_approved'):
        body=body.replace('All 114 marked exceptions keep originals until you approve replacements.',
            str(status['reviewed_approved'])+' recreated replacements are approved and selected locally. NR104 keeps its original.')
    if not complete:body=body.replace('<!--REFRESH-->','<meta http-equiv="refresh" content="60">')
    (queue/'review.html').write_text(body)
    return {k:status[k]for k in ('state','completed','running','queued','failed')}

def record(queue,job_id,generated):
    item=next(j for j in jobs(queue)if j['id']==job_id)
    native=queue/'outputs'/(job_id+'-native-v1'+generated.suffix);jpeg=queue/'outputs'/(job_id+'-v1.jpg')
    if native.exists()or jpeg.exists():raise ValueError('Refusing to overwrite a replacement')
    if sha(item['prompt_file'])!=item['prompt_sha256']:raise ValueError('Prompt changed')
    shutil.copy2(generated,native)
    with Image.open(native)as im:
        native_dimensions=im.size;image=im.convert('RGB')
        if list(image.size)!=item['dimensions']:image=image.resize(tuple(item['dimensions']),Image.Resampling.LANCZOS)
        image.save(jpeg,format='JPEG',quality=90,subsampling=0)
    with Image.open(jpeg)as check:
        check.load();w,h=check.size
        corners=[list(ImageStat.Stat(check.crop(box)).mean)for box in ((0,0,8,8),(w-8,0,w,8),(0,h-8,8,h),(w-8,h-8,w,h))]
        assert check.format=='JPEG'and check.mode=='RGB'and list(check.size)==item['dimensions']
    write(queue/'records'/(job_id+'.json'),{'state':'awaiting_review','id':job_id,'completed_at':time.time(),
        'native_path':str(native),'native_sha256':sha(native),'native_dimensions':native_dimensions,
        'jpeg_path':str(jpeg),'jpeg_sha256':sha(jpeg),'dimensions':item['dimensions'],'jpeg_quality':90,
        'corner_rgb_means':corners,'prompt_file':item['prompt_file'],'prompt_sha256':item['prompt_sha256'],
        'reference_images':[],'original_image_viewed':False,'generation_mode':'built-in imagegen','selection_changed':False})
    return render(queue)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','next','record','refresh','fail']);p.add_argument('--queue',type=Path,required=True);p.add_argument('--job',type=Path);p.add_argument('--id');p.add_argument('--generated',type=Path);p.add_argument('--limit',type=int,default=4);p.add_argument('--error');a=p.parse_args();queue=a.queue.resolve()
    if a.command=='prepare':prepare(a.job.resolve(),queue);print(json.dumps(read(queue/'status.json')))
    else:
        with (queue/'generation.lock').open('a')as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if a.command=='next':
                pending=[j for j in jobs(queue)if not(queue/'records'/(j['id']+'.json')).exists()][:a.limit]
                for j in pending:write(queue/'records'/(j['id']+'.json'),{'id':j['id'],'state':'generating','started_at':time.time()})
                render(queue);print(json.dumps([{'id':j['id'],'prompt':Path(j['prompt_file']).read_text()}for j in pending]))
            elif a.command=='record':print(json.dumps(record(queue,a.id,a.generated.resolve())))
            elif a.command=='fail':
                write(queue/'records'/(a.id+'.json'),{'id':a.id,'state':'needs_attention','error':a.error,'at':time.time()});print(json.dumps(render(queue)))
            else:print(json.dumps(render(queue)))
