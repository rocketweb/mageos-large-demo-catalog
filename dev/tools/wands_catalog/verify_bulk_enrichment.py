"""Read-only whole-catalog verification of an enriched candidate and its baseline."""
import argparse
from collections import Counter
import csv
import io
import json
import logging
import math
from pathlib import Path
import sys
import tarfile

from catalog_depth import ATTRIBUTES
from prepare_catalog import sha256
from synthetic_dimensions import validate_dimensions
sys.path.insert(0,str(Path(__file__).with_name('distribution')))
from release import dependencies, safe_path, verify_release


def read_catalog(path):
    with tarfile.open(path) as archive:
        data={m.name:archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}
    rows={}
    for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv'):
        parsed=list(csv.DictReader(io.StringIO(data['data/'+name].decode())))
        for row in parsed:
            if row['sku'] in rows:
                raise ValueError('Duplicate product SKU')
            rows[row['sku']]=row
    return rows,data


def verify(baseline, candidate, manifest_pin):
    if sha256(candidate/'manifest.json')!=manifest_pin:
        raise ValueError('Candidate manifest mismatch')
    manifest=json.loads((candidate/'manifest.json').read_text())
    verify_release(baseline,manifest['baseline_manifest_sha256'])
    for name,digest in manifest['outputs'].items():
        safe_path(name)
        if sha256(candidate/name)!=digest:
            raise ValueError('Candidate content changed: '+name)
    before,original_data=read_catalog(baseline/'catalog.tar')
    after,data=read_catalog(candidate/'catalog-enriched.tar')
    if set(before)!=set(after):
        raise ValueError('SKU identity changed')
    checks=0
    allowed={'description','related_skus','crosssell_skus','lab_spec_disclosure',*ATTRIBUTES}
    for sku,row in after.items():
        for key in set(row)|set(before[sku]):
            if key not in allowed and (row.get(key) or '')!=(before[sku].get(key) or ''):
                raise ValueError('Unapproved field mutation: '+sku+' '+key)
            checks+=1
        for field in ('related_skus','crosssell_skus'):
            targets=[s for s in row.get(field,'').split(',') if s]
            if len(targets)!=len(set(targets)) or sku in targets:
                raise ValueError('Self or duplicate merchandise link')
            for target in targets:
                if (target not in after or after[target].get('product_online')!='1'
                        or after[target].get('visibility')=='Not Visible Individually'):
                    raise ValueError('Broken, disabled or hidden merchandise target')
                checks+=1
        for child in dependencies(row):
            if child not in after or after[child]['product_type']!='simple':
                raise ValueError('Broken dependent product')
            checks+=1
    records=[json.loads(line) for line in (candidate/'specifications.jsonl').read_text().splitlines()]
    if len({r['sku'] for r in records})!=len(records):
        raise ValueError('Duplicate specification record')
    counts=Counter()
    for record in records:
        row=after[record['sku']]
        if row.get('product_online')!='1':
            raise ValueError('Disabled product received specs')
        if record.get('dimension_design',{}).get('status') in {'synthetic_design_complete','synthetic_components_complete'}:
            validate_dimensions(record)
        for code,fact in record['specifications'].items():
            if code not in ATTRIBUTES or not fact.get('evidence') or 'synthetic' not in fact:
                raise ValueError('Missing specification provenance')
            if row.get(code)!=str(fact['value']):
                raise ValueError('Native field differs from provenance')
            rule=ATTRIBUTES[code]
            if rule['kind']=='select' and fact['value'] not in rule['options']:
                raise ValueError('Unknown specification option')
            if rule['kind']=='length' and (not math.isfinite(float(fact['value'])) or float(fact['value'])<=0):
                raise ValueError('Invalid measurement')
            if fact['synthetic'] and (not row.get('lab_spec_disclosure') or 'synthetic lab specification' not in row['description']):
                raise ValueError('Synthetic specification lacks visible disclosure')
            counts[code]+=1;checks+=1
    if dict(counts)!=manifest['coverage']['attribute_coverage']:
        raise ValueError('Coverage disagrees with actual records')
    for name in ('data/4-media.csv','data/media-inventory.json','data/media-lineage.json','data/counts.json'):
        if data[name]!=original_data[name]:
            raise ValueError('Original media or counts changed')
    if data['data/specification-provenance.jsonl']!=(candidate/'specifications.jsonl').read_bytes():
        raise ValueError('Packaged provenance differs')
    scenarios=[json.loads(line) for line in (candidate/'commerce-scenarios.jsonl').read_text().splitlines()]
    if len({s['id'] for s in scenarios})!=len(scenarios):
        raise ValueError('Duplicate scenario identity')
    for scenario in scenarios:
        for sku,fields in scenario['changes'].items():
            if sku not in before or set(fields)!=set(scenario['restore'][sku]):
                raise ValueError('Scenario target or inverse incomplete')
            for key,prior in scenario['restore'][sku].items():
                if prior!={'present':key in before[sku],'value':before[sku].get(key)}:
                    raise ValueError('Scenario inverse differs from baseline')
                checks+=1
    seeds=[json.loads(line) for line in (candidate/'search-query-seeds.jsonl').read_text().splitlines()]
    if any(s['judgment'] is not None or s['ranking_ground_truth'] for s in seeds):
        raise ValueError('Unjudged seeds presented as benchmark labels')
    return {'status':'passed','checks':checks,'products':len(after),'specification_values':sum(counts.values()),
        'scenarios':len(scenarios),'query_seeds':len(seeds),'magento_import_verified':False,'live_writes':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    args.report.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.report.with_suffix('.log'),level=logging.INFO)
    try:
        result=verify(args.baseline,args.candidate,args.manifest_sha256)
        with args.report.open('x') as stream:
            json.dump(result,stream,indent=2);stream.write('\n')
        logging.info('PASS %s',result)
    except Exception:
        logging.exception('Enrichment verification failed')
        raise SystemExit(1)
