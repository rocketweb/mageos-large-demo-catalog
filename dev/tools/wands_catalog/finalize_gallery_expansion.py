"""Package the 14 inspected gallery additions; preserve original hero images."""
import argparse
from collections import defaultdict
import html
import json
import logging
from pathlib import Path

from bulk_enrichment import csv_bytes, json_bytes, sha256, write_archive
from generate_reference_images import completed, fingerprint
from review_gallery_expansion import CONFIG, INSPECTED_EVENTS_SHA256, decision
from verify_bulk_enrichment import read_catalog

REPAIR_EVENTS_SHA256='1cd803827013aa8b872ec60af9e8252e52136d08f8c79e090ffe0f6ef0a6ce69'


def gallery_assignment(sku, url_key, views):
    # ProductImporter enables FIELDS_ENCLOSURE. Native parseMultiselectValues
    # requires each caption to be quoted inside the already CSV-quoted cell.
    labels=['Synthetic '+view+' illustration; styling not included' for view,_ in views]
    return {'sku':sku,'url_key':url_key,'store_view_code':'',
            'additional_images':','.join(path for _,path in views),
            'additional_image_labels':','.join('"'+label.replace('"','""')+'"' for label in labels)}


def selected_jobs(jobs_path,run_dir,event_pin,first):
    if sha256(run_dir/'generation-events.jsonl')!=event_pin:
        raise ValueError('Visual decisions apply only to the inspected image hashes')
    descriptor=json.loads((run_dir/'run.json').read_text())
    if descriptor['jobs_sha256']!=sha256(jobs_path):
        raise ValueError('Queue changed after generation')
    events=completed(run_dir/'generation-events.jsonl')
    result=[]
    for job in [json.loads(line) for line in jobs_path.read_text().splitlines()]:
        event=events[job['output_file']]
        path=run_dir/job['output_file']
        if event['request_sha256']!=fingerprint(job,CONFIG) or event['image_sha256']!=sha256(path):
            raise ValueError('Image or prompt no longer matches inspected generation')
        if first and not decision(job)[0]:
            continue
        result.append((job,path,event))
    return result


def build(args):
    if args.output.exists():
        raise ValueError('Choose a fresh gallery package directory')
    selected=selected_jobs(args.queue/'jobs.jsonl',args.run_dir,INSPECTED_EVENTS_SHA256,True)
    selected+=selected_jobs(args.review/'repair-jobs.jsonl',args.repairs,REPAIR_EVENTS_SHA256,False)
    if len(selected)!=14 or len({(j['sku'],j['view']) for j,_,_ in selected})!=14:
        raise ValueError('Expected exactly 14 distinct accepted gallery views')
    rows,_=read_catalog(args.catalog)
    media,metadata,by_sku={},[],defaultdict(list)
    cards=[]
    for job,path,event in sorted(selected,key=lambda r:(r[0]['sku'],r[0]['view'])):
        if job['sku'] not in rows:
            raise ValueError('Gallery target absent from catalog')
        name='media/wands-lab/galleries/'+path.name
        media[name]=path
        metadata.append({'sku':job['sku'],'view':job['view'],'file':name,'sha256':event['image_sha256'],
            'reference_sha256':job['reference_images'][0]['sha256'],'prompt':job['prompt'],'seed':job['seed'],
            'model':'FLUX.2-klein-4B','cached_model_revision_observed':'e7b7dc27f91deacad38e78976d1f2b499d76a294',
            'runtime':'mflux 0.19.1','config':CONFIG,'accepted_for':'synthetic catalog illustration',
            'acceptance_method':'direct assistant visual inspection of each final image',
            'license':'CC0-1.0 to the extent Rocket Web holds the rights',
            'disclosure':'Generated illustration. Room furnishings are styling and not included products. Scale and manufacturer accuracy are not verified.'})
        by_sku[job['sku']].append((job['view'],'/wands-lab/galleries/'+path.name))
        cards.append('<article><h2>'+html.escape(job['sku']+' '+job['view'])+'</h2><img src="'+
                     html.escape(path.resolve().as_uri(),quote=True)+'"></article>')
    assignments=[]
    for sku,views in sorted(by_sku.items()):
        assignments.append(gallery_assignment(sku,rows[sku]['url_key'],views))
    media['data/gallery-additions.csv']=csv_bytes(assignments)
    media['data/gallery-provenance.json']=json_bytes(metadata)
    docs=Path(__file__).with_name('distribution')
    for name in ('CC0-1.0.txt','WANDS-LICENSE.txt','CITATION.bib','TERMS.md'):
        media['docs/'+name]=docs/name
    media['docs/ROCKET-WEB-LICENSE.txt']=Path(__file__).with_name('LICENSE.txt')
    media['docs/GALLERIES.txt']=b'Local candidate. Upload media/wands-lab/galleries under pub/media/import/wands-lab/galleries and validate the seven-row media-only CSV before a separately authorized import. No base/small/thumbnail role is changed. No existing gallery removal is requested. Native gallery append behavior and final storefront display still need isolated Magento acceptance.\n'
    args.output.mkdir(parents=True)
    artifact=write_archive(args.output/'gallery-additions.tar',media)
    manifest={'schema':1,'release':'2026.09.13-gallery-v2','profile':'gallery-additions','artifacts':[artifact],
        'images':14,'products':7,'source_images_retained':True,'deployed':False,
        'magento_import_verified':False,'catalog_sha256':sha256(args.catalog)}
    (args.output/'manifest.json').write_bytes(json_bytes(manifest))
    (args.output/'manifest.sha256').write_text(sha256(args.output/'manifest.json')+'  manifest.json\n')
    (args.output/'review.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Accepted catalog galleries</title><style>body{font:16px system-ui;margin:2rem}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}img{width:100%}h2{font-size:16px}</style><h1>14 accepted gallery additions</h1><p>Seven products, each with a detail and room view. Synthetic illustrations; not deployed.</p><main>'+''.join(cards)+'</main></html>')
    logging.info('COMPLETE 14 inspected images for seven products; package pin %s',sha256(args.output/'manifest.json'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('queue','run-dir','review','repairs','catalog','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output.with_suffix('.log'),level=logging.INFO)
    try:
        build(args)
    except Exception:
        logging.exception('Gallery packaging failed')
        raise SystemExit(1)
