#!/usr/bin/env python3
"""Consolidate reviewed component candidates without approving masks or publication."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from html import escape
import json
import logging
from pathlib import Path
import tempfile

from build_realism_review import write_json, write_jsonl
from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from run_catalog_component_pilot import verify_layouts
from run_catalog_media_pilot import verify_pins
from verify_catalog_repairs import check

VERSIONS=('wands-component-image-review-v1','wands-framing-review-v1','wands-framing-refinement-review-v1')


def inventory(briefs,reviews):
    known={b['asset_requirement_id']:b for b in briefs}; history=defaultdict(list)
    check(len(known)==len(briefs),'Duplicate component brief')
    for r in reviews:
        c=r['case'].get('source_case',r['case']); key=c['asset_requirement_id']
        check(key in known and c['brief']==known[key],'Unknown component or changed brief')
        check(r['verdict'] in {'pass','uncertain','fail'},'Unreviewed candidate cannot enter readiness')
        history[key].append({'verdict':r['verdict'],'image_path':r['image_path'],'image_sha256':r['image_sha256'],
                             'finding':r['finding'],'review_source':r['review_source'],'execution_case_sha256':digest(r['case'])})
    assets=[]
    for key,b in sorted(known.items()):
        attempts=history[key]; chosen=None; status='unattempted'
        for verdict,state in (('pass','initial_visual_pass'),('uncertain','uncertain'),('fail','failed')):
            matching=[r for r in attempts if r['verdict']==verdict]
            if matching: chosen=matching[-1]; status=state; break
        assets.append({'asset_requirement_id':key,'root_sku':b['root_sku'],'component_id':b['component_id'],
                       'label':b['component']['label'],'required_instances':b['required_instances'],'brief_sha256':digest(b),
                       'status':status,'proposed_candidate':chosen,'history':attempts,
                       'next_step':'evaluate_mask_method' if status=='initial_visual_pass' else
                                   'resolve_visual_uncertainty' if status=='uncertain' else
                                   'repair_geometry_or_identity' if status=='failed' else 'generate_initial_component',
                       'mask_execution_approved':False,'mask_ready':False,'assembly_ready':False,'publication_approved':False})
    grouped=defaultdict(list)
    for a in assets: grouped[a['root_sku']].append(a)
    families=[{'root_sku':sku,'component_types':len(parts),'required_instances':sum(p['required_instances'] for p in parts),
               'initial_visual_pass_types':sum(p['status']=='initial_visual_pass' for p in parts),
               'missing_visual_pass_types':sum(p['status']!='initial_visual_pass' for p in parts),
               'missing_visual_pass_components':[p['label'] for p in parts if p['status']!='initial_visual_pass'],
               'assembly_ready':False,'publication_approved':False} for sku,parts in sorted(grouped.items())]
    states=Counter(a['status'] for a in assets)
    counts={'families':len(families),'component_types':len(assets),'required_instances':sum(a['required_instances'] for a in assets),
            'reviewed_attempts':len(reviews),'unique_image_hashes':len({r['image_sha256'] for r in reviews}),
            **{k:states[k] for k in ('initial_visual_pass','uncertain','failed','unattempted')},
            'mask_evaluation_candidates':states['initial_visual_pass'],
            'instances_with_initial_visual_pass':sum(a['required_instances'] for a in assets if a['status']=='initial_visual_pass'),
            'mask_ready':0,'assembly_ready':0,'publication_approved':0}
    return assets,families,counts


def render(assets,families,counts):
    h=lambda v:escape(str(v),quote=True)
    family_rows=''.join('<tr><th scope="row">'+h(f['root_sku'])+'</th><td>'+str(f['component_types'])+'</td><td>'+str(f['required_instances'])+
                      '</td><td>'+str(f['initial_visual_pass_types'])+'</td><td>'+h(', '.join(f['missing_visual_pass_components']))+'</td></tr>' for f in families)
    cards=[]
    for a in assets:
        c=a['proposed_candidate']; content=''
        if c:
            content=('<a href="'+h(Path(c['image_path']).as_uri())+'"><img src="'+h(Path(c['image_path']).as_uri())+'" alt="'+h(a['label'])+
                    '"></a><p>'+h(c['finding'])+'</p><p><a href="'+h((Path(c['review_source'])/'review.html').as_uri())+'">Full image review and prompt</a></p>')
        history=''.join('<li>'+h(r['verdict'])+': '+h(r['image_sha256'])+'</li>' for r in a['history'])
        cards.append('<article><p class="tag">'+h(a['root_sku'])+'</p><h2>'+h(a['label'])+'</h2><p><strong>'+h(a['status'].replace('_',' '))+
            '</strong> · '+str(a['required_instances'])+' required physical instance(s)</p>'+content+'<p>Next: '+h(a['next_step'].replace('_',' '))+
            '</p><details><summary>'+str(len(a['history']))+' reviewed attempts</summary><ul>'+history+'</ul></details></article>')
    return ('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Catalog component readiness</title><style>*{box-sizing:border-box}body{margin:0;background:#eef2ef;color:#192b25;font:17px/1.55 system-ui}
main{max-width:1220px;margin:auto;padding:32px 24px}h1{font-size:clamp(2rem,4vw,3rem);line-height:1.15}.stats{display:flex;flex-wrap:wrap;gap:12px}.stats p{background:white;padding:12px 18px;border-radius:10px}
.stats strong{display:block;font-size:2rem}.notice{background:#fff1cf;border-left:4px solid #a37322;padding:18px}.table{overflow-x:auto}table{border-collapse:collapse;background:white;width:100%;font-size:14px}
td,th{padding:12px;text-align:left;border-bottom:1px solid #d0dcd3;vertical-align:top}.cards{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:24px}
article{min-width:0;padding:24px;background:white;border:1px solid #d0dcd3;border-radius:12px}article img{width:100%;height:340px;object-fit:contain}h2{font-size:1.4rem}.tag{font-size:13px;text-transform:uppercase}
a,summary{color:#165e8a}summary{cursor:pointer}li{overflow-wrap:anywhere;font-size:13px}@media(max-width:700px){main{padding:20px 14px}.cards{grid-template-columns:1fr}article{padding:16px}}
</style></head><body><main><h1>Component readiness, without losing the evidence.</h1><div class="stats">'''+''.join('<p><strong>'+str(counts[k])+'</strong>'+label+'</p>' for k,label in (
        ('component_types','planned types'),('initial_visual_pass','initial visual passes'),('uncertain','uncertain'),('unattempted','unattempted'),('assembly_ready','assembly-ready sets')))+'''
</div><p class="notice">No publication or mask execution is approved by this inventory. An initial visual pass only identifies a candidate for a separate mask evaluation.
No images or product definitions were replaced. Every prior failed attempt is retained.</p><p>This covers the five component-layout pilot families, not the whole WANDS catalog.
The proposed candidate is the latest initial pass, otherwise the latest uncertainty or failure. This is a review pointer, not a deployed media assignment.</p>
<h2>What each complete assortment still needs</h2><div class="table"><table><thead><tr><th>Family</th><th>Types</th><th>Physical instances</th><th>Initial passes</th><th>Types without a visual pass</th></tr></thead><tbody>'''+family_rows+
        '</tbody></table></div><div class="cards">'+''.join(cards)+'</div></main></body></html>\n')


def build(layouts,packets,output):
    check(not output.exists() and not output.is_symlink(),'Use a fresh readiness directory')
    briefs,pins=verify_layouts(layouts); reviews=[]
    check(len(packets)==len(VERSIONS) and len({p.resolve() for p in packets})==len(packets),'Provide the three distinct review passes in order')
    for packet,version in zip(packets,VERSIONS):
        packet=packet.resolve(); m=json.loads((packet/'manifest.json').read_text())
        check(m['version']==version and set(m['outputs'])=={'reviews.jsonl','review.html'} and
              {p.name for p in packet.iterdir()}=={'manifest.json',*m['outputs']} and m['publication_approved'] is False,'Wrong review pass or state')
        incoming={**m['inputs'],str(packet/'manifest.json'):sha256(packet/'manifest.json'),**{str(packet/k):v for k,v in m['outputs'].items()}}
        check(all(k not in pins or pins[k]==v for k,v in incoming.items()),'Conflicting review provenance')
        verify_pins(incoming); pins.update(incoming)
        for r in read_jsonl(packet/'reviews.jsonl'):
            check(pins.get(str(Path(r['image_path']).resolve()))==r['image_sha256'] and sha256(Path(r['image_path']))==r['image_sha256'],
                  'Candidate image is unpinned or changed')
            reviews.append({**r,'review_source':str(packet)})
    pins[str(Path(__file__).resolve())]=sha256(Path(__file__)); output=output.resolve()
    protected={Path(p).parent for p in pins if Path(p).name=='manifest.json' or Path(p).suffix.lower() in {'.jpg','.png','.webp'}}
    check(not any(Path(p).is_relative_to(output) for p in pins) and not any(output.is_relative_to(p) for p in protected),'Readiness output overlaps source')
    assets,families,counts=inventory(briefs,reviews); output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='.'+output.name+'-') as folder:
        stage=Path(folder); write_jsonl(stage/'assets.proposed.jsonl',assets); write_jsonl(stage/'families.jsonl',families)
        (stage/'review.html').write_text(render(assets,families,counts)); verify_pins(pins)
        write_json(stage/'manifest.json',{'version':'wands-component-readiness-v1','inputs':pins,
            'outputs':{p.name:sha256(p) for p in sorted(stage.iterdir())},'counts':counts,'mask_execution_approved':False,'publication_approved':False})
        stage.rename(output)
    return counts


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--layouts',required=True,type=Path)
    parser.add_argument('--reviews',required=True,nargs=3,type=Path); parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--json',action='store_true'); args=parser.parse_args(); args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_name(args.output_dir.name+'.log'),level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        counts=build(args.layouts,args.reviews,args.output_dir); logging.info('Completed component readiness: %s',json.dumps(counts,sort_keys=True))
        if args.json: print(json.dumps(counts,sort_keys=True))
        return 0
    except Exception:
        logging.exception('Readiness stopped without media or approval changes'); return 1


if __name__=='__main__':
    raise SystemExit(main())
