#!/usr/bin/env python3
"""Review local framing trials with hash-bound observations and read-only pixel diagnostics."""
from __future__ import annotations

import argparse
from collections import Counter
from html import escape
import json
import logging
import math
from pathlib import Path
import tempfile

from PIL import Image
from build_realism_review import write_json, write_jsonl
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from review_catalog_component_pilot import CHECKS
from run_catalog_framing_pilot import verify_source, pending, validate_directory
from run_catalog_media_pilot import verify_pins
from verify_catalog_repairs import check


def measure_envelope(image):
    """Read pixel contrast against white. Never save, crop, mask or approve an image."""
    gray=image.convert('L'); rows=[]
    for contrast in (16,32,64):
        box=gray.point(lambda v:255 if v < 255-contrast else 0).getbbox()
        rows.append({'contrast_from_white':contrast,'bbox':list(box) if box else None,
                     'height_width_ratio':(box[3]-box[1])/(box[2]-box[0]) if box else None,
                     'touches_edge':bool(box and (box[0]==0 or box[1]==0 or box[2]==image.width or box[3]==image.height))})
    return {'status':'diagnostic_only','is_mask':False,'thresholds':rows,
            'limitations':'Shadows, bright metal, background tone and disconnected pixels can bias the envelope.'}


def verify_run(run_dir):
    run_dir=run_dir.resolve(); descriptor=json.loads((run_dir/'run.json').read_text())
    check(descriptor['version']=='wands-framing-pilot-v1' and descriptor['max_attempts']==4 and
          descriptor['publication_approved'] is False,'Unexpected framing descriptor')
    verify_pins(descriptor['inputs'])
    cases,source_pins=verify_source(Path(descriptor['source_review']),descriptor['source_sha256'])
    check(all(descriptor['inputs'].get(k)==v for k,v in source_pins.items()),'Framing source pins omitted')
    runner=Path(__file__).with_name('run_catalog_framing_pilot.py').resolve()
    check(descriptor['inputs'].get(str(runner))==sha256(runner),'Framing runner changed')
    check(digest(cases)==descriptor['cases_sha256'] and cases==read_jsonl(run_dir/'execution-cases.jsonl'), 'Framing cases changed')
    validate_directory(run_dir,cases); check(not pending(cases,run_dir),'Framing run is incomplete')
    pins={**descriptor['inputs'],**{str(p):sha256(p) for p in run_dir.iterdir() if p.name!='.pilot.lock'}}
    source=json.loads((Path(descriptor['source_review'])/'manifest.json').read_text())
    original=json.loads((Path(source['run'])/'run.json').read_text())
    check(descriptor['runtime']==original['runtime'],'Framing runtime changed')
    for c in cases:
        path=run_dir/c['candidate_filename']; meta=json.loads((run_dir/(path.name+'.json')).read_text())
        check(meta['visual_acceptance']=='pending' and meta['mask_acceptance']=='pending' and meta['has_alpha'] is False and
              meta['publication_approved'] is False and meta['reference_use_approved'] is False and
              meta['required_disclosure']==c['source_case']['brief']['required_disclosure'],'Framing provenance or acceptance changed')
        with Image.open(path) as im:
            check(im.size==(c['settings']['width'],c['settings']['height']) and im.format=='WEBP' and im.mode=='RGB',
                  'Framing image dimensions, format or alpha changed')
            im.verify()
    return cases,pins


def bind_observations(cases,notes,run_dir):
    indexed={n['trial_id']:n for n in notes}
    check(len(indexed)==len(notes)==len(cases) and set(indexed)=={c['trial_id'] for c in cases},'Observation scope differs')
    rows=[]
    for c in cases:
        n=indexed[c['trial_id']]; path=run_dir/c['candidate_filename']; s=c['settings']; b=c['source_case']['brief']
        check(n['image_sha256']==sha256(path) and n['case_sha256']==digest(c),'Stale framing observation')
        check(n['review_method']=='direct_image_inspection' and
              all(isinstance(n[k],str) and n[k].strip() for k in ('review_date','finding','next_direction')),'Incomplete framing evidence')
        check(set(n['checks'])==CHECKS and all(v in {'pass','fail','uncertain'} for v in n['checks'].values()),'Incomplete visual checks')
        box=n['estimated_subject_bbox']
        check(isinstance(box,list) and len(box)==4 and all(type(v) in (float,int) and math.isfinite(v) for v in box), 'Invalid visual bounds')
        x1,y1,x2,y2=box
        check(0<=x1<x2<=s['width'] and 0<=y1<y2<=s['height'],'Visual bounds outside canvas')
        dims=b['component']['dimensions_cm']
        h=dims['lab_spec_height_cm'] if b['view']=='front elevation' else dims.get('lab_spec_length_cm',dims.get('lab_spec_depth_cm'))
        target=h/dims['lab_spec_width_cm']; observed=(y2-y1)/(x2-x1)
        with Image.open(path) as image: diagnostics=measure_envelope(image)
        verdict='fail' if 'fail' in n['checks'].values() else 'uncertain' if 'uncertain' in n['checks'].values() else 'pass'
        rows.append({**n,'case':c,'image_path':str(path.resolve()),'verdict':verdict,
                     'target_ratio':target,'estimated_ratio':observed,'relative_ratio_error':observed/target-1,
                     'square_repeat_matches_original':sha256(path)==c['source_image_sha256'] if c['arm']=='square' else None,
                     'pixel_diagnostics':diagnostics,'mask_ready':False,'assembly_ready':False,'publication_approved':False,
                     'reference_use_approved':False})
    return rows


def render(rows):
    h=lambda v:escape(str(v),quote=True); groups={}
    for r in rows: groups.setdefault(r['case']['asset_requirement_id'],[]).append(r)
    sections=[]
    for key,pair in groups.items():
        cards=[]
        for r in pair:
            c=r['case']; s=c['settings']
            diagnostics=''.join('<tr><td>'+str(d['contrast_from_white'])+'</td><td>'+h(d['bbox'])+'</td><td>'+
                (f"{d['height_width_ratio']:.2f}" if d['height_width_ratio'] else 'none')+'</td></tr>' for d in r['pixel_diagnostics']['thresholds'])
            checks=''.join('<li>'+h(k.replace('_',' '))+': <strong>'+h(v)+'</strong></li>' for k,v in r['checks'].items())
            cards.append('<section><h3>'+h(c['arm'].title())+' · '+str(s['width'])+' × '+str(s['height'])+'</h3><p class="badge '+r['verdict']+'">'+
                h(r['verdict'].upper())+'</p><a href="'+h(Path(r['image_path']).as_uri())+'"><img src="'+h(Path(r['image_path']).as_uri())+'" alt="'+
                h(c['source_case']['brief']['component']['label']+' '+c['arm'])+'"></a><p>'+h(r['finding'])+'</p><p>Approximate silhouette ratio: <strong>'+
                f"{r['estimated_ratio']:.2f}"+'</strong>; synthetic target <strong>'+f"{r['target_ratio']:.2f}"+'</strong>; signed ratio error '+
                f"{r['relative_ratio_error']:+.1%}"+'.</p><p><strong>Next:</strong> '+h(r['next_direction'])+'</p><details><summary>Visual checks and pixel diagnostics</summary><ul>'+checks+
                '</ul><p>Three contrast thresholds against white, not an object mask or an acceptance test.</p><div class="table"><table><thead><tr><th>Contrast</th><th>Pixel envelope</th><th>H/W</th></tr></thead><tbody>'+diagnostics+
                '</tbody></table></div><p>'+h(r['pixel_diagnostics']['limitations'])+'</p><code>Image SHA256: '+h(r['image_sha256'])+'</code></details></section>')
        source=pair[0]['case']['source_case']; repeated=pair[0]['square_repeat_matches_original']
        sections.append('<article id="'+h(key)+'"><p class="tag">'+h(source['root_sku'])+'</p><h2>'+h(source['brief']['component']['label'])+
            '</h2><p>Square control matches the earlier image byte for byte: <strong>'+('yes' if repeated else 'no')+'</strong>.</p><div class="pair">'+''.join(cards)+
            '</div><details><summary>Unchanged prompt and provenance</summary><pre>'+h(source['runtime_prompt'])+'</pre><p>Seed '+str(source['seed'])+'; '+str(source['token_count'])+
            ' / 512 prompt tokens.</p><p>'+h(source['brief']['required_disclosure'])+'</p></details></article>')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Component framing experiment</title><style>*{box-sizing:border-box}body{margin:0;background:#eef2ef;color:#192b25;font:17px/1.55 system-ui,sans-serif}
main{max-width:1220px;margin:auto;padding:32px 24px}h1{font-size:clamp(2rem,4vw,3rem);line-height:1.15}h2{font-size:1.7rem}.tag{font-size:13px;text-transform:uppercase}
article{background:white;border:1px solid #d0dcd3;border-radius:12px;padding:28px;margin:28px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:28px}
section{min-width:0}img{display:block;width:100%;height:600px;object-fit:contain;background:#fff}.notice{background:#fff1cf;border-left:4px solid #a37322;padding:16px}
.badge{display:inline-block;padding:4px 14px;border-radius:8px}.fail{background:#ffe4df;color:#862820}.uncertain{background:#fff1cf;color:#795311}.pass{background:#e0f3e4;color:#21572f}
summary,a{color:#165e8a}summary{cursor:pointer}details{margin:20px 0}pre,code{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}pre{padding:18px;background:#eff3f0}
table{border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:8px;border-bottom:1px solid #d4ddd6}.table{overflow-x:auto}
@media(max-width:700px){main{padding:20px 14px}article{padding:16px}.pair{grid-template-columns:1fr}img{height:480px}}
</style></head><body><main><p class="tag">Local FLUX framing experiment · exact paired prompts · no retries</p>
<h1>Does a tall canvas improve product proportions?</h1><p>Two products, one seed per product, square and portrait. Each image contains 589,824 pixels.
The prompt, seed, local model, quantization, guidance and step count are unchanged within each pair. Changing the canvas changes spatial noise arrangement;
this is not an identical noise field or a catalog-wide quality estimate.</p><p class="notice">No masks or composites have been produced. No candidate is approved for publication.
Visual bounds are approximate diagnostics, not physical measurements or a new automatic acceptance threshold. Failed candidates remain evidence only.</p>'''+''.join(sections)+'</main></body></html>\n'


def build(run_dir,notes_path,output):
    check(not output.exists() and not output.is_symlink(),'Use a fresh framing review directory')
    run_dir=run_dir.resolve(); output=output.resolve(); cases,pins=verify_run(run_dir)
    pins[str(notes_path.resolve())]=sha256(notes_path); pins[str(Path(__file__).resolve())]=sha256(Path(__file__))
    protected={Path(p).parent for p in pins if Path(p).name=='manifest.json' or Path(p).suffix.lower() in {'.jpg','.png','.webp'}}
    check(not any(Path(p).is_relative_to(output) for p in pins) and not any(output.is_relative_to(p) for p in protected), 'Review overlaps source inputs')
    rows=bind_observations(cases,json.loads(notes_path.read_text()),run_dir)
    counts=Counter(r['verdict'] for r in rows)
    counts={**{k:counts[k] for k in ('pass','fail','uncertain')},'reviewed':len(rows),
            'square_controls_reproduced':sum(r['square_repeat_matches_original'] is True for r in rows),
            'mask_ready':0,'assembly_ready':0,'publication_approved':0}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='.'+output.name+'-') as folder:
        stage=Path(folder); write_jsonl(stage/'reviews.jsonl',rows); (stage/'review.html').write_text(render(rows))
        verify_pins(pins)
        write_json(stage/'manifest.json',{'version':'wands-framing-review-v1','run':str(run_dir),'inputs':pins,
                   'outputs':{p.name:sha256(p) for p in sorted(stage.iterdir())},'counts':counts,'publication_approved':False})
        stage.rename(output)
    return counts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('run-dir','observations','output-dir'): parser.add_argument('--'+flag,required=True,type=Path)
    parser.add_argument('--json',action='store_true'); args=parser.parse_args()
    args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_name(args.output_dir.name+'.log'),level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        counts=build(args.run_dir,args.observations,args.output_dir); logging.info('Completed framing review: %s',json.dumps(counts,sort_keys=True))
        if args.json: print(json.dumps(counts,sort_keys=True))
        return 0
    except Exception:
        logging.exception('Framing review stopped without changing images or approval'); return 1


if __name__=='__main__':
    raise SystemExit(main())
