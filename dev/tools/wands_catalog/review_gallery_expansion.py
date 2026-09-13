"""Record the inspected first gallery batch and prepare a targeted repair queue."""
import argparse
import hashlib
import html
import json
import logging
from pathlib import Path

from generate_reference_images import completed, fingerprint
from prepare_catalog import sha256
from prepare_gallery_expansion import APPROVED_HASHES

CONFIG={'model':'flux2-klein-4b','quantize':4,'steps':4,'width':768,'height':768}
INSPECTED_EVENTS_SHA256='1ff824a963dc9272c17f8a751e3f7d597717798728be882ab6900c498f34b157'


def decision(job):
    if job['view']=='angle':
        return False,'Near-duplicate of the hero; does not add a useful viewing angle.'
    if job['view']=='room':
        if job['sku']=='WANDS-000711':
            return False,'Conical base became visibly faceted; preserve the smooth circular cone.'
        return True,'Product identity retained in room context; background styling is not included.'
    if job['sku']=='WANDS-000083':
        return True,'Single close-up retains the beige braid texture and octagonal edge.'
    return False,'Detail image adds duplicate objects or a collage instead of one close-up.'


def build(queue,run_dir,output):
    if output.exists():
        raise ValueError('Choose a new review directory')
    if sha256(run_dir/'generation-events.jsonl')!=INSPECTED_EVENTS_SHA256:
        raise ValueError('This review applies only to the directly inspected image hashes')
    jobs=[json.loads(line) for line in (queue/'jobs.jsonl').read_text().splitlines()]
    descriptor=json.loads((run_dir/'run.json').read_text())
    if descriptor['jobs_sha256']!=sha256(queue/'jobs.jsonl') or len(jobs)!=21:
        raise ValueError('Unexpected first gallery queue')
    events=completed(run_dir/'generation-events.jsonl')
    observations,repairs,approved=[],[],[]
    cards=[]
    for job in jobs:
        path=run_dir/job['output_file']
        event=events.get(job['output_file'],{})
        if event.get('request_sha256')!=fingerprint(job,CONFIG) or event.get('image_sha256')!=sha256(path):
            raise ValueError('Generated image/request changed since the run')
        keep,note=decision(job)
        record={'sku':job['sku'],'view':job['view'],'file':job['output_file'],'sha256':sha256(path),
            'accepted':keep,'reason':note,'method':'direct assistant visual inspection, 2026-09-12',
            'manufacturer_accuracy_verified':False}
        observations.append(record)
        if keep:
            approved.append(record)
        elif job['view']!='angle':
            if job['view']=='room':
                prompt='Place the exact white lamp from Image 1 on a side table in a calm room. The base must remain a smooth rotationally symmetric circular cone with no facets or ridges. Preserve the cylindrical white shade. One lamp only. Background styling is not included.'
            elif '00008' in job['sku']:
                prompt='Zoom tightly into one corner or edge of the single braided rug in Image 1. Fill the frame with one continuous flat surface and its adjacent bound edge. Preserve its exact color and braid pattern. The rug is flat, not folded. No other rug, no full product, no collage, no inset panels.'
            elif job['sku']=='WANDS-000304':
                prompt='Zoom tightly into the junction of the brown upholstered seat and the wooden armrest of the chair in Image 1. A single continuous close-up photograph. Show only this small part of the chair, with the same wood tone and brown upholstery. No whole chair, no sample swatch, no collage or inset.'
            else:
                prompt='Zoom tightly into the lower edge of the white lampshade from Image 1. Fill the entire image with one continuous macro photograph of the shade fabric and its rim. Preserve the exact white shade texture. No whole lamp, no lamp base, no collage, no panels, no split screen.'
            prompt+=' Soft photorealistic product lighting. No words, logos, watermarks or measurements.'
            signature=hashlib.sha256((job['reference_images'][0]['sha256']+prompt).encode()).hexdigest()
            repairs.append({**job,'prompt':prompt,'seed':int(signature[:8],16),
                'output_file':job['sku']+'-gallery-'+job['view']+'-repair-'+signature[:10]+'.jpg'})
        cards.append('<article><h2>'+html.escape(job['sku']+' '+job['view'])+'</h2><img src="'+
            html.escape(path.resolve().as_uri(),quote=True)+'"><p>'+('Accepted: ' if keep else 'Excluded: ')+html.escape(note)+'</p></article>')
    output.mkdir(parents=True)
    for name,entries in [('observations.jsonl',observations),('accepted.jsonl',approved),('repair-jobs.jsonl',repairs)]:
        (output/name).write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in entries))
    audit=[json.loads(line) for line in (queue/'reference-audit.jsonl').read_text().splitlines()]
    if any(r['image_sha256'] not in APPROVED_HASHES.values() for r in audit):
        raise ValueError('Unexpected approved reference')
    (output/'reference-audit.jsonl').write_bytes((queue/'reference-audit.jsonl').read_bytes())
    (output/'review.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Gallery expansion review</title><style>body{font:16px system-ui;margin:2rem}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}img{width:100%}article{border:1px solid #ddd;padding:1rem}h2{font-size:16px}</style><h1>Gallery expansion: 7 accepted, 7 repairs, 7 redundant views</h1><p>Synthetic illustrations. No media installed.</p><main>'+''.join(cards)+'</main></html>')
    (output/'manifest.json').write_text(json.dumps({'accepted':len(approved),'repair_jobs':len(repairs),
        'redundant':7,'images_installed':0,'queue_sha256':sha256(queue/'jobs.jsonl'),
        'outputs':{p.name:sha256(p) for p in sorted(output.iterdir())}},indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('queue','run-dir','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output.with_suffix('.log'),level=logging.INFO)
    try:
        build(args.queue,args.run_dir,args.output)
        logging.info('Completed first-batch visual review and repair preparation')
    except Exception:
        logging.exception('Review preparation failed')
        raise SystemExit(1)
