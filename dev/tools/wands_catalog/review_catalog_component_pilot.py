#!/usr/bin/env python3
"""Render hash-bound component observations without approving masks, assembly or publication."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from html import escape
import json
import logging
import math
from pathlib import Path
import tempfile

from PIL import Image
from build_realism_review import write_json, write_jsonl
from catalog_repairs import read_jsonl
from plan_catalog_component_layouts import read_review
from plan_catalog_media_repairs import SETTINGS
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from run_catalog_component_pilot import verify_layouts, select_cases, pending_assets
from run_catalog_media_pilot import verify_pins
from verify_catalog_repairs import check

CHECKS = {'single_complete_component','identity_and_construction','appearance_and_view',
          'proportions','no_text_or_extras','synthetic_provenance'}


def bind_observations(cases, notes, run_dir):
    indexed = {n['asset_requirement_id']:n for n in notes}
    check(len(indexed) == len(notes) == len(cases) and set(indexed) == {c['asset_requirement_id'] for c in cases},
          'Observation scope differs from exact component pilot')
    rows = []
    for c in cases:
        n = indexed[c['asset_requirement_id']]
        check(n['brief_sha256'] == c['brief_sha256'] and n['runtime_prompt_sha256'] == c['runtime_prompt_sha256'] and
              n['image_sha256'] == sha256(run_dir/c['candidate_filename']), 'Stale component observation')
        check(set(n['checks']) == CHECKS and all(v in {'pass','fail','uncertain'} for v in n['checks'].values()),
              'Missing or incomplete component checks')
        check(n['review_method'] == 'direct_image_inspection' and all(isinstance(n[k],str) and n[k].strip()
              for k in ('review_date','finding','next_direction','bbox_note')), 'Incomplete visual evidence')
        bounds = n['estimated_subject_bbox']
        check(isinstance(bounds,list) and len(bounds)==4 and all(type(v) in (int,float) and math.isfinite(v) for v in bounds),
              'Invalid diagnostic image bounds')
        x1,y1,x2,y2=bounds
        check(0 <= x1 < x2 <= 768 and 0 <= y1 < y2 <= 768, 'Diagnostic bounds outside image')
        dims=c['brief']['component']['dimensions_cm']; width=dims['lab_spec_width_cm']
        height=dims['lab_spec_height_cm'] if c['brief']['view']=='front elevation' else dims.get('lab_spec_length_cm',dims.get('lab_spec_depth_cm'))
        verdict='fail' if 'fail' in n['checks'].values() else 'uncertain' if 'uncertain' in n['checks'].values() else 'pass'
        rows.append({**n,'verdict':verdict,'case':c,'image_path':str(run_dir/c['candidate_filename']),
                     'diagnostic_ratio':{'target':height/width,'estimated_image':(y2-y1)/(x2-x1)},
                     'mask_ready':False,'assembly_ready':False,'publication_approved':False,'reference_use_approved':False})
    return rows


def verify_completed(layouts, selection, run_dir):
    briefs,pins=verify_layouts(layouts)
    descriptor=json.loads((run_dir/'run.json').read_text())
    check(descriptor['layout_manifest_sha256']==sha256(layouts/'manifest.json') and
          descriptor['selection_sha256']==sha256(selection), 'Run input fingerprint changed')
    runner=Path(__file__).with_name('run_catalog_component_pilot.py')
    check(descriptor['runner_sha256']==sha256(runner) and descriptor['settings']==SETTINGS, 'Runner or settings changed')
    pins[str(selection.resolve())]=sha256(selection); pins[str(runner.resolve())]=sha256(runner)
    pins.update(descriptor['runtime']['tokenizer_hashes'])
    planned=select_cases(briefs,json.loads(selection.read_text()))
    cases=read_jsonl(run_dir/'execution-cases.jsonl')
    check(len(cases)==len(planned)==descriptor['max_attempts'] and digest(cases)==descriptor['cases_sha256'], 'Run scope changed')
    for c,p in zip(cases,planned):
        check(type(c['token_count']) is int and 0 < c['token_count'] <= 512, 'Invalid prompt token count')
        expected={**p,'token_count':c['token_count'],'candidate_filename':p['asset_requirement_id']+'-'+digest({'case':p,'settings':SETTINGS})[:12]+'.webp'}
        check(c==expected,'Runtime component differs from selected brief')
    check(not pending_assets(cases,run_dir),'Component pilot is incomplete')
    allowed={'run.json','execution-cases.jsonl','events.jsonl','.pilot.lock'} | {
        n for c in cases for n in (c['candidate_filename'],c['candidate_filename']+'.json')}
    check({p.name for p in run_dir.iterdir()}<=allowed,'Unexpected component run contents')
    for path in run_dir.iterdir():
        check(not path.is_symlink() and path.is_file(),'Unexpected run path')
        if path.name!='.pilot.lock': pins[str(path)]=sha256(path)
    for c in cases:
        path=run_dir/c['candidate_filename']; meta=json.loads((run_dir/(path.name+'.json')).read_text())
        check(meta['settings']==SETTINGS and meta['visual_acceptance']=='pending' and meta['mask_acceptance']=='pending' and
              meta['required_disclosure']==c['brief']['required_disclosure'] and meta['has_alpha'] is False and
              meta['publication_approved'] is False and meta['reference_use_approved'] is False,'Original component acceptance state changed')
        with Image.open(path) as image:
            check(image.size==(768,768) and image.format=='WEBP' and image.mode=='RGB','Unexpected component format or alpha')
            image.verify()
    verify_pins(pins)
    return cases,pins


def render(rows, counts):
    h=lambda v:escape(str(v),quote=True)
    labels={'pass':'Initial visual pass','uncertain':'Uncertain: hold','fail':'Fails visual review'}
    cards=[]
    for r in rows:
        c=r['case']; b=c['brief']; ratio=r['diagnostic_ratio']
        checks=''.join('<li><strong>'+h(v.upper())+'</strong>: '+h(k.replace('_',' '))+'</li>' for k,v in r['checks'].items())
        cards.append('<article id="'+h(r['asset_requirement_id'])+'"><p class="tag">'+h(c['root_sku'])+'</p><h2>'+h(b['component']['label'])+
                     '</h2><p class="badge '+r['verdict']+'">'+labels[r['verdict']]+'</p><div class="comparison"><figure><figcaption>Earlier whole-set attempt</figcaption>'+
                     '<img src="'+h(Path(r['earlier_image']).as_uri())+'" alt="'+h(b['parent_product_name']+' earlier failed image')+'"></figure>'+
                     '<figure><figcaption>New single-component candidate</figcaption><a href="'+h(Path(r['image_path']).as_uri())+'"><img src="'+
                     h(Path(r['image_path']).as_uri())+'" alt="'+h(b['component']['label'])+'"></a></figure></div><p>'+h(r['finding'])+
                     '</p><p><strong>Next:</strong> '+h(r['next_direction'])+'</p><p>Height/width: synthetic target <strong>'+f"{ratio['target']:.2f}"+
                     '</strong>; approximate image envelope <strong>'+f"{ratio['estimated_image']:.2f}"+'</strong>. This is a visual diagnostic, not physical measurement.</p>'+
                     '<details><summary>Actual prompt, checks and provenance</summary><ul>'+checks+'</ul><pre>'+h(c['runtime_prompt'])+
                     '</pre><p>'+str(c['token_count'])+' / 512 prompt tokens. Seed '+str(c['seed'])+'.</p><p>'+h(b['required_disclosure'])+
                     '</p><p>'+h(r['bbox_note'])+'</p><code>Image SHA256: '+h(r['image_sha256'])+'</code></details></article>')
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Catalog component-image pilot review</title><style>
*{box-sizing:border-box}body{margin:0;background:#eff2ef;color:#172b24;font:17px/1.55 system-ui,sans-serif}
main{max-width:1220px;margin:auto;padding:36px 24px}h1{font-size:clamp(2rem,4vw,3rem);line-height:1.15;max-width:900px}
h2{font-size:1.7rem;margin:8px 0}.tag{font-size:13px;letter-spacing:.06em;text-transform:uppercase}
article{background:white;border:1px solid #d5ded7;border-radius:12px;padding:28px;margin:28px 0;scroll-margin-top:20px}
.stats{display:flex;gap:12px;flex-wrap:wrap}.stats div{background:white;border-radius:10px;padding:12px 20px}.stats strong{display:block;font-size:2rem}
.notice{background:#fff2d2;border-left:4px solid #a87520;padding:14px 18px}.comparison{display:grid;grid-template-columns:1fr 1fr;gap:20px}
figure{margin:0;min-width:0}figcaption{font-size:14px;margin:10px 0}img{display:block;width:100%;height:auto;aspect-ratio:1;object-fit:contain;border-radius:8px}
.badge{display:inline-block;padding:5px 12px;border-radius:8px}.pass{color:#18582d;background:#e1f3e5}.uncertain{color:#75500d;background:#fff0c5}
.fail{color:#8c251f;background:#ffe6e1}a,summary{color:#135a8b}summary{cursor:pointer}pre,code{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}
pre{background:#f0f3f1;padding:15px}nav{display:flex;flex-wrap:wrap;gap:10px 24px;margin:24px 0}
@media(max-width:700px){main{padding:20px 14px}article{padding:16px}.comparison{grid-template-columns:1fr}}
</style></head><body><main><p class="tag">Local FLUX component pilot · no retries · no compositing</p>
<h1>Single components.<br>Structure and proportions under review.</h1>
<p>FLUX.2 Klein 4B, 4-bit, 768 × 768, four steps. Text-only generation from corrected component briefs.
Family quantities and assembly instructions stay out of the model prompts. No source image or planning diagram was used as a model reference.</p>
<div class="stats">""" + ''.join('<div><strong>'+str(counts[k])+'</strong>'+label+'</div>' for k,label in (
        ('reviewed','components reviewed'),('pass','initial passes'),('uncertain','uncertain'),('fail','visual failures'),('assembly_ready','assembly-ready assets'))) + """
</div><p class="notice">This is a small development pilot, not a catalog-wide success-rate estimate. All candidates are opaque RGB images.
No transparent mask or composite has been produced. An initial visual pass does not approve masking, reference conditioning, publication
or bulk expansion. Earlier whole-set images and new single-object images are different tasks, not an equal-condition model benchmark.</p>
<p>Approximate subject bounds help diagnose silhouette drift. They are hand-estimated visual evidence, not segmentation masks,
manufacturer measurements or a new automatic pass threshold. Full-set consistency, scale, lighting and final composition remain untested.</p>
<nav aria-label="Component candidates">""" + ''.join('<a href="#'+h(r['asset_requirement_id'])+'">'+h(r['case']['brief']['component']['label'])+
        '</a>' for r in rows) + '</nav>' + ''.join(cards) + '</main></body></html>\n'


def build(layouts,selection,run_dir,notes_path,output):
    run_dir=run_dir.resolve()
    check(not output.exists() and not output.is_symlink(),'Use a fresh component review directory')
    output=output.resolve()
    cases,pins=verify_completed(layouts,selection,run_dir)
    raw=notes_path.read_bytes(); notes=json.loads(raw)
    check(isinstance(notes,list),'Observations must be an array')
    pins[str(notes_path.resolve())]=hashlib.sha256(raw).hexdigest(); pins[str(Path(__file__).resolve())]=sha256(Path(__file__))
    protected={Path(p).parent for p in pins if Path(p).name=='manifest.json' or Path(p).suffix.lower() in {'.jpg','.webp','.png'}}
    check(not any(Path(p).is_relative_to(output) for p in pins) and not any(output.is_relative_to(p) for p in protected),
          'Review output overlaps source packets or images')
    rows=bind_observations(cases,notes,run_dir)
    m=json.loads((layouts/'manifest.json').read_text())
    earlier,_=read_review(Path(m['source_review'])); earlier={r['root_sku']:r for r in earlier}
    for r in rows: r['earlier_image']=earlier[r['case']['root_sku']]['candidate_path']
    totals=Counter(r['verdict'] for r in rows)
    counts={'reviewed':len(rows),**{k:totals[k] for k in ('pass','fail','uncertain')},
            'single_complete_components':sum(r['checks']['single_complete_component']=='pass' for r in rows),
            'mask_ready':0,'assembly_ready':0,'publication_approved':0}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='.'+output.name+'-') as folder:
        stage=Path(folder); write_jsonl(stage/'reviews.jsonl',rows)
        (stage/'review.html').write_text(render(rows,counts))
        verify_pins(pins)
        write_json(stage/'manifest.json',{'version':'wands-component-image-review-v1','run':str(run_dir),'inputs':pins,
                   'outputs':{p.name:sha256(p) for p in sorted(stage.iterdir())},'counts':counts,
                   'publication_approved':False,'generation_approved':False,'assembly_ready':False})
        stage.rename(output)
    return counts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('layouts','selection','run-dir','observations','output-dir'):
        parser.add_argument('--'+flag,required=True,type=Path)
    parser.add_argument('--json',action='store_true',help='Opt in to a terminal summary')
    args=parser.parse_args(); args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_name(args.output_dir.name+'.log'),level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        result=build(args.layouts,args.selection,args.run_dir,args.observations,args.output_dir)
        logging.info('Completed component review: %s',json.dumps(result,sort_keys=True))
        if args.json: print(json.dumps(result,sort_keys=True,indent=2))
        return 0
    except Exception:
        logging.exception('Component review stopped; no images, masks or approvals changed')
        return 1


if __name__=='__main__':
    raise SystemExit(main())
