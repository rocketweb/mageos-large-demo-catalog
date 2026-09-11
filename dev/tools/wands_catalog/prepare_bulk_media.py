#!/usr/bin/env python3
"""Verify completed bulk images and prepare a quiet, URL-preserving media import."""
import argparse
from html import escape
import json
import logging
from pathlib import Path
import shutil

from catalog_repairs import read_jsonl
from prepare_catalog import sha256
from prepare_bulk_import import preserve_urls, write_csv
from run_bulk_completion_images import pending
from verify_catalog_repairs import check


def build(args):
    from PIL import Image
    check(not args.output_dir.exists(), 'Choose a fresh output directory')
    manifest = json.loads((args.packet/'manifest.json').read_text())
    for name, digest in manifest['outputs'].items():
        check(Path(name).name == name and sha256(args.packet/name) == digest, 'Packet drift')
    jobs = read_jsonl(args.packet/'image-jobs.jsonl')
    reuse = read_jsonl(args.packet/'reused-images.jsonl')
    media = args.run_dir/'media'
    check(not pending(jobs, media, args.run_dir/'events.jsonl'), 'Image generation incomplete')
    images, sources = {}, {}
    for job in jobs+reuse:
        path = media/job['output_file']
        check(path.parent == media and path.is_file(), 'Unsafe or missing image')
        digest = sha256(path)
        if job in reuse:
            check(digest == job['source_sha256'], 'Reviewed image drift')
        with Image.open(path) as image:
            image.verify()
        check(job['sku'] not in images, 'Duplicate image SKU')
        images[job['sku']] = {'file': path.name, 'sha256': digest, 'bytes': path.stat().st_size}
        sources[job['sku']] = path
    for repair_dir in args.repairs or []:
        repairs = read_jsonl(repair_dir.with_suffix('.jsonl'))
        events = {r['output_file']:r for r in read_jsonl(repair_dir/'generation-events.jsonl')}
        seen = set()
        for job in repairs:
            sku = job['sku']
            check(sku in images and sku not in seen, 'Unknown or duplicate repair SKU')
            seen.add(sku)
            check(images[sku]['file'] == job['original_file'], 'Repair source mismatch')
            path = repair_dir/job['output_file']
            check(path.parent == repair_dir and path.suffix == '.jpg', 'Unsafe repair path')
            event = events.get(path.name,{})
            check(event.get('status') == 'generated' and event.get('sku') == sku and event.get('seed') == job['seed'], 'Repair incomplete or mismatched')
            with Image.open(path) as image:
                image.verify()
            images[sku] = {'file':path.name, 'sha256':sha256(path), 'bytes':path.stat().st_size, 'replaces':job['original_file']}
            sources[sku] = path
    parents = read_jsonl(args.packet/'parent-media.jsonl')
    assignments = {sku: sku for sku in images}
    for parent in parents:
        check(parent['default_child_sku'] in images, 'Missing parent hero')
        assignments[parent['root_sku']] = parent['default_child_sku']
    products = {r['sku']: r for r in read_jsonl(args.packet/'products.jsonl')}
    rows = []
    for sku, image_sku in sorted(assignments.items()):
        path = '/wands/bulk-completion-v1/'+images[image_sku]['file']
        label = products[image_sku]['catalog_fields']['name']+' (synthetic lab illustration)'
        rows.append({'sku': sku, 'store_view_code': '', 'base_image': path,
                     'small_image': path, 'thumbnail': path, 'base_image_label': label,
                     'small_image_label': label, 'thumbnail_label': label})
    rows = preserve_urls(rows, args.snapshot)
    args.output_dir.mkdir(parents=True)
    (args.output_dir/'media').mkdir()
    for sku, source in sources.items():
        target = args.output_dir/'media'/images[sku]['file']
        shutil.copyfile(source,target)
        check(sha256(target) == images[sku]['sha256'], 'Media copy changed')
    write_csv(args.output_dir/'media-updates.csv', rows)
    if args.delta_from:
        previous=json.loads(args.delta_from.read_text())
        changed={sku for sku,image_sku in assignments.items()
                 if previous['images'].get(previous['assignments'].get(sku),{}).get('sha256') != images[image_sku]['sha256']}
        check(bool(changed),'No changed media to import')
        write_csv(args.output_dir/'media-delta.csv',[row for row in rows if row['sku'] in changed])
    cards = []
    for parent in parents:
        sku = parent['default_child_sku']
        image = (args.output_dir/'media'/images[sku]['file']).resolve().as_uri()
        name = products[sku]['catalog_fields']['name']
        cards.append('<article><img src="'+escape(image)+'"><p>'+escape(sku)+'<br>'+escape(name)+'</p></article>')
    (args.output_dir/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Bulk catalog image review</title><style>body{font:14px sans-serif;margin:20px;background:#eee}main{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}article{background:white;padding:8px;break-inside:avoid}img{width:100%;aspect-ratio:1;object-fit:contain}p{min-height:55px}h1{font-size:22px}</style><h1>93 corrected families · synthetic test imagery</h1><main>'+''.join(cards)+'</main>')
    result = {'images': images, 'assignments': assignments, 'image_count': len(images),
              'media_rows': len(rows), 'family_views': len(parents), 'catalog_images_in_git': False,
              'technical_validation': 'all decoded and matched generation or reviewed-source hashes',
              'visual_validation': 'batch review required; technical validity is not visual accuracy',
              'packet_sha256': sha256(args.packet/'manifest.json'),
              'repair_jobs_sha256': {str(p):sha256(p.with_suffix('.jsonl')) for p in args.repairs or []},
              'csv_sha256': sha256(args.output_dir/'media-updates.csv')}
    (args.output_dir/'manifest.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('packet', 'run-dir', 'snapshot', 'output-dir'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--repairs', type=Path, action='append')
    parser.add_argument('--delta-from', type=Path)
    args = parser.parse_args()
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'), level=logging.INFO)
    try:
        build(args)
        logging.info('Bulk media verified and prepared')
    except Exception:
        logging.exception('Bulk media preparation failed')
        raise SystemExit(1)
