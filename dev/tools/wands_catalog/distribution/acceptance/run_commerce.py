"""Serial, receipt-driven commerce scenarios in the approved enriched fixture."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

from enriched_instance import ROOT, CLI


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile',choices=['medium','full'])
    parser.add_argument('--pilot',action='store_true')
    parser.add_argument('--source-sha256',required=True)
    args=parser.parse_args()
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('Wrong fixture directory')
    source=ROOT/'packages/commerce-scenarios.jsonl'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=args.source_sha256:
        raise RuntimeError('Scenario source changed')
    skus=set()
    for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv'):
        with (ROOT/'packages'/f'{args.profile}-staged/data'/name).open() as file:
            skus.update(row['sku'] for row in csv.DictReader(file))
    cases=[json.loads(line) for line in source.read_text().splitlines()]
    cases=[case for case in cases if {case['root_sku'],*case['changes']}<=skus]
    if args.pilot:
        kinds=set(); selected=[]
        for case in cases:
            if case['kind'] not in kinds: selected.append(case); kinds.add(case['kind'])
        cases=selected
    receipts=ROOT/'receipts'/('commerce-'+args.profile)
    receipts.mkdir(exist_ok=True)
    status=ROOT/('commerce-'+args.profile+'-state.json')
    for number,case in enumerate(cases,1):
        name=re.sub('[^A-Za-z0-9_.-]','_',case['id'])
        output=receipts/(name+'.json')
        if output.exists():
            previous=json.loads(output.read_text())
            if previous['status']=='passed' and previous['restored']: continue
            raise RuntimeError('Unresolved prior case: '+case['id'])
        status.write_text(json.dumps({'stage':case['id'],'status':'running','number':number,'total':len(cases)}))
        with (receipts/(name+'.log')).open('xb') as error:
            result=subprocess.run(CLI+['/packages/commerce_case.php'],input=json.dumps(case).encode(),
                                  stdout=subprocess.PIPE,stderr=error)
        output.write_bytes(result.stdout)
        if result.returncode:
            status.write_text(json.dumps({'stage':case['id'],'status':'failed','number':number,'total':len(cases)}))
            raise RuntimeError('Case failed; inspect exact receipt: '+case['id'])
    status.write_text(json.dumps({'status':'passed','cases':len(cases),'pilot':args.pilot,
                                 'source_sha256':args.source_sha256}))


if __name__=='__main__': main()
