"""Package enriched medium/full candidates, keeping original media unchanged."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tarfile

from bulk_enrichment import csv_bytes, json_bytes, sha256
sys.path.insert(0,str(Path(__file__).with_name('distribution')))
from release import dependencies, closure, write_archive, verify_release


def subset_data(data, selected):
    selected=set(selected)
    result=dict(data)
    rows={}
    for filename in ('data/1-simple.csv','data/2-configurable.csv','data/3-bundle.csv'):
        group=[r for r in csv.DictReader(io.StringIO(data[filename].decode())) if r['sku'] in selected]
        for row in group:
            # Merchandising links are not required dependencies: prune external targets.
            for field in ('related_skus','crosssell_skus','upsell_skus'):
                if field in row:
                    row[field]=','.join(s for s in row[field].split(',') if s in selected)
            rows[row['sku']]=row
        result[filename]=csv_bytes(group)
    if set(rows)!=selected or closure(rows,selected)!=selected:
        raise ValueError('Medium profile has incomplete dependencies')
    media=[r for r in csv.DictReader(io.StringIO(data['data/4-media.csv'].decode())) if r['sku'] in selected]
    result['data/4-media.csv']=csv_bytes(media)
    lineage=json.loads(data['data/media-lineage.json'])
    assignments={s:v for s,v in lineage['assignments'].items() if s in selected}
    missing=sorted(selected-set(assignments))
    if any(rows[s].get('product_online')=='1' for s in missing):
        raise ValueError('Enabled medium product has no media')
    names={v['file'] for v in assignments.values()}
    inventory=json.loads(data['data/media-inventory.json'])
    result['data/media-inventory.json']=json_bytes({name:inventory[name] for name in sorted(names)})
    result['data/media-lineage.json']=json_bytes({'assignments':assignments,'missing_disabled_skus':missing})
    specs=[json.loads(line) for line in data['data/specification-provenance.jsonl'].decode().splitlines()]
    specs=[r for r in specs if r['sku'] in selected]
    result['data/specification-provenance.jsonl']=''.join(json.dumps(r,sort_keys=True)+'\n' for r in specs).encode()
    links=[json.loads(line) for line in data['data/merchandising-provenance.jsonl'].decode().splitlines()]
    links=[r for r in links if r['sku'] in selected]
    for link in links:
        for code in ('related_skus','crosssell_skus'):
            link[code]=[s for s in link[code] if s in selected]
        for kind in link['evidence']:
            link['evidence'][kind]=[r for r in link['evidence'][kind] if r['target_sku'] in selected]
    result['data/merchandising-provenance.jsonl']=''.join(json.dumps(r,sort_keys=True)+'\n' for r in links).encode()
    stats={'products':len(rows),'product_types':dict(Counter(r['product_type'] for r in rows.values())),
        'disabled_products':sum(r.get('product_online')=='2' for r in rows.values()),
        'configurable_links':sum(len(dependencies(r)) for r in rows.values() if r['product_type']=='configurable'),
        'bundle_selections':sum(len(r['bundle_values'].split('|')) for r in rows.values() if r['product_type']=='bundle'),
        'bundle_options':sum(len({dict(f.split('=',1) for f in g.split(','))['name'] for g in r['bundle_values'].split('|')})
            for r in rows.values() if r['product_type']=='bundle'),
        'image_files':len(names),'media_assignments':len(media),'media_roles':len(media)*3,
        'media_coverage':dict(Counter(v['origin'] for v in assignments.values()))}
    result['data/counts.json']=json_bytes(stats)
    result['data/enrichment-coverage.json']=json_bytes({'profile':'medium','records':len(specs),
        'specification_values':sum(len(r['specifications']) for r in specs),
        'related_links':sum(len(r['related_skus']) for r in links),'crosssell_links':sum(len(r['crosssell_skus']) for r in links)})
    return result,stats,names


def build(args):
    if args.output.exists():
        raise ValueError('Choose a new medium release directory')
    manifest_path=args.enrichment/'manifest.json'
    if sha256(manifest_path)!=args.enrichment_sha256:
        raise ValueError('Enrichment manifest pin mismatch')
    enrichment=json.loads(manifest_path.read_text())
    for name in ('catalog-enriched.tar','medium-skus.json'):
        if sha256(args.enrichment/name)!=enrichment['outputs'][name]:
            raise ValueError('Enrichment output changed')
    verify_release(args.baseline,enrichment['baseline_manifest_sha256'])
    selected=json.loads((args.enrichment/'medium-skus.json').read_text())
    with tarfile.open(args.enrichment/'catalog-enriched.tar') as archive:
        data={m.name:archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}
    if args.profile=='full':
        stats=json.loads(data['data/counts.json'])
        needed=set(json.loads(data['data/media-inventory.json']))
    else:
        data,stats,needed=subset_data(data,selected)
    args.output.mkdir(parents=True)
    artifacts=[write_archive(args.output/'catalog.tar',data)]
    module_root=args.repository/'app/code/RocketWeb/LabCatalog'
    module={}
    for path in sorted(module_root.rglob('*')):
        relative=path.relative_to(module_root)
        if path.is_file() and relative.parts[0]!='Test' and path.suffix in {'.php','.xml','.json','.txt'}:
            module['module/'+relative.as_posix()]=path
    artifacts.append(write_archive(args.output/'module.tar',module))
    chunk,chunk_bytes,number,found={},0,1,set()
    inventory=json.loads(data['data/media-inventory.json'])
    for archive_path in sorted(args.baseline.glob('media-*.tar')):
        if args.profile=='full':
            baseline_manifest=json.loads((args.baseline/'manifest.json').read_text())
            item=next(a for a in baseline_manifest['artifacts'] if a['path']==archive_path.name)
            # Same-filesystem hard links avoid another 2.2 GB media copy. These
            # immutable candidates never modify archive contents after creation.
            os.link(archive_path,args.output/archive_path.name)
            artifacts.append(item)
            found.update(item['files'])
            continue
        with tarfile.open(archive_path) as archive:
            for member in archive:
                if member.name not in needed:
                    continue
                if not member.isfile() or member.name in found:
                    raise ValueError('Unexpected media member')
                content=archive.extractfile(member).read()
                if hashlib.sha256(content).hexdigest()!=inventory[member.name]['sha256']:
                    raise ValueError('Media inventory mismatch')
                if chunk and chunk_bytes+len(content)>128*1024**2:
                    artifacts.append(write_archive(args.output/f'media-{number:03d}.tar',chunk))
                    chunk,chunk_bytes,number={},0,number+1
                chunk[member.name]=content;chunk_bytes+=len(content);found.add(member.name)
    if found!=needed:
        raise ValueError('Missing medium media')
    if chunk:
        artifacts.append(write_archive(args.output/f'media-{number:03d}.tar',chunk))
    manifest={'schema':1,'release':args.release,'profile':args.profile,
        'status':'local enriched candidate; Magento import and browser acceptance pending',
        'install_mode':'fresh dedicated lab only; not an existing-store update',
        'counts':stats,'artifacts':artifacts,'dependency_closure':True,
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.repository,text=True).strip(),
        'source_files':{str(p.relative_to(args.repository)):sha256(p) for p in module.values()},
        'enrichment_manifest_sha256':args.enrichment_sha256,
        'baseline_manifest_sha256':enrichment['baseline_manifest_sha256'],
        'licensing':{'code':'MIT','authored_data':'MIT','upstream':'MIT','generated_media':'CC0-1.0',
                     'media_scope':'rights held by Rocket Web; third-party rights not waived'}}
    (args.output/'manifest.json').write_bytes(json_bytes(manifest))
    pin=sha256(args.output/'manifest.json')
    (args.output/'manifest.sha256').write_text(pin+'  manifest.json\n')
    (args.output/'release.py').write_bytes(Path(__file__).with_name('distribution').joinpath('release.py').read_bytes())
    verified=verify_release(args.output,pin)
    logging.info('COMPLETE %s',json.dumps({'counts':stats,'manifest_sha256':pin,'verification':verified}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for option in ('baseline','enrichment','repository','output'):
        parser.add_argument('--'+option,type=Path,required=True)
    parser.add_argument('--enrichment-sha256',required=True)
    parser.add_argument('--release',required=True)
    parser.add_argument('--profile',choices=['medium','full'],default='medium')
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output.with_suffix('.log'),level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        build(args)
    except Exception:
        logging.exception('Medium packaging stopped; no published assets changed')
        raise SystemExit(1)
