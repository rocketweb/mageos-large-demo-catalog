#!/usr/bin/env python3
"""Review saved repairs while retaining interrupted and unattempted run evidence."""
import argparse
from collections import Counter
import json
import logging
from pathlib import Path
import tempfile

from build_component_readiness import inventory, render
from build_realism_review import write_json, write_jsonl
from catalog_repairs import read_jsonl
from completion_review import bind_observations
from component_completion import render as render_repairs
from prepare_catalog import sha256
from reconcile_catalog_media import digest
from run_catalog_component_pilot import verify_layouts
from run_catalog_framing_pilot import validate_directory
from run_catalog_media_pilot import verify_pins
from verify_catalog_repairs import check


def classify_events(cases,events):
    states={c['trial_id']:'unattempted' for c in cases}
    check(len(states)==len(cases),'Duplicate repair case')
    for e in events:
        key=e['trial_id']; status=e['status'];check(key in states,'Unknown repair event')
        check((status=='attempt_started' and states[key]=='unattempted') or
              (status in {'generated','failed'} and states[key]=='attempt_started'),'Invalid repair transition')
        states[key]=status
    return states


def build(args):
    check(not args.output_dir.exists() and not args.output_dir.is_symlink(),'Use a fresh repair review directory')
    briefs,pins=verify_layouts(args.layouts); baseline=args.readiness.resolve(); m=json.loads((baseline/'manifest.json').read_text())
    check(m['version']=='wands-component-readiness-v2','Wrong baseline inventory')
    incoming={**m['inputs'],str(baseline/'manifest.json'):sha256(baseline/'manifest.json'),**{str(baseline/k):v for k,v in m['outputs'].items()}}
    verify_pins(incoming);pins.update(incoming)
    old_assets=read_jsonl(baseline/'assets.proposed.jsonl'); old=[]
    sources=list(dict.fromkeys(h['review_source'] for a in old_assets for h in a['history']))
    # The baseline inventory is already verified. Preserve its history order within each component.
    for source in sources:old.extend({**r,'review_source':source} for r in read_jsonl(Path(source)/'reviews.jsonl'))
    notes=json.loads(args.observations.read_text()); indexed={n['trial_id']:n for n in notes};rows=[];runs=[]
    check(len(indexed)==len(notes),'Duplicate repair observation')
    for directory in args.runs:
        directory=directory.resolve();d=json.loads((directory/'run.json').read_text());cases=read_jsonl(directory/'execution-cases.jsonl')
        check(d['version']=='wands-component-repair-v1' and d['cases_sha256']==digest(cases),'Changed repair descriptor')
        verify_pins(d['inputs']);check(all(k not in pins or pins[k]==v for k,v in d['inputs'].items()),'Conflicting repair provenance');pins.update(d['inputs'])
        validate_directory(directory,cases);events=read_jsonl(directory/'events.jsonl');states=classify_events(cases,events)
        runs.append({'path':str(directory),'states':states})
        completed={e['trial_id']:e for e in events if e['status']=='generated'}
        for c in cases:
            key=c['trial_id']
            if states[key]!='generated':continue
            e=completed[key];image=directory/c['candidate_filename'];meta=image.with_name(image.name+'.json');data=json.loads(meta.read_text())
            check(e['image_sha256']==sha256(image) and e['metadata_sha256']==sha256(meta) and e['filename']==image.name,'Changed repair image or metadata')
            check(data['case']==c and data['execution_case_sha256']==digest(c) and data['publication_approved'] is False and data['has_alpha'] is False,'Changed repair provenance')
            check(key in indexed,'Missing saved-candidate observation')
            rows.extend(bind_observations([c],[indexed.pop(key)],directory))
        pins.update({str(p):sha256(p) for p in directory.iterdir() if p.name!='.pilot.lock'})
    check(not indexed,'Observation refers to an ungenerated image')
    expected={a['asset_requirement_id'] for a in old_assets if a['status']!='initial_visual_pass'}
    ids=[r['case']['asset_requirement_id'] for r in rows]
    check(len(ids)==len(set(ids)) and set(ids)==expected,'Repair review does not cover the unresolved components exactly once')
    new=[{**r,'review_source':str(args.output_dir.resolve())} for r in rows]
    assets,families,counts=inventory(briefs,old+new)
    pins[str(args.observations.resolve())]=sha256(args.observations);pins[str(Path(__file__).resolve())]=sha256(Path(__file__))
    output=args.output_dir.resolve()
    check(not any(Path(p).is_relative_to(output) for p in pins),'Output contains a source input')
    protected={Path(p).parent for p in pins if Path(p).name in {'manifest.json','run.json'} or Path(p).suffix.lower() in {'.png','.jpg','.webp'}}
    check(not any(output.is_relative_to(p) for p in protected),'Output overlaps evidence')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='.'+output.name+'-') as folder:
        stage=Path(folder);write_jsonl(stage/'reviews.jsonl',rows);write_jsonl(stage/'assets.proposed.jsonl',assets);write_jsonl(stage/'families.jsonl',families)
        write_json(stage/'run-states.json',runs);(stage/'repairs.html').write_text(render_repairs(rows));html=render(assets,families,counts)
        html=html.replace('<h1>','<p><a href="repairs.html">Latest repair candidates and exact prompts</a></p><h1>',1)
        html=html.replace('</div><p class="notice">','<p><strong>'+str(counts['failed'])+'</strong>failed component types</p></div><p class="notice">',1)
        (stage/'review.html').write_text(html);verify_pins(pins)
        write_json(stage/'manifest.json',{'version':'wands-component-repair-review-v1','inputs':pins,'outputs':{p.name:sha256(p) for p in stage.iterdir()},
                   'counts':counts,'repair_verdicts':dict(Counter(r['verdict'] for r in rows)),'publication_approved':False})
        stage.rename(output)
    return counts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('layouts','readiness','observations','output-dir'):parser.add_argument('--'+flag,required=True,type=Path)
    parser.add_argument('--runs',required=True,nargs='+',type=Path);args=parser.parse_args();args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_name(args.output_dir.name+'.log'),level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:logging.info('Repair review summary: %s',json.dumps(build(args),sort_keys=True));return 0
    except Exception:logging.exception('Repair review stopped without modifying images');return 1


if __name__=='__main__':raise SystemExit(main())
