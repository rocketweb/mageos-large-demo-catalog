#!/usr/bin/env python3
"""Prepare an exact local or Comtom catalog delta from a read-only snapshot."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from build_expanded_catalog import csv_rows, write_csv, write_json, variations
from prepare_catalog import sha256


def prepare(candidate,snapshot,output,desired_rows=None,reconciliation=None):
    manifest=json.loads((candidate/'manifest.json').read_text())
    for name,pin in manifest['outputs'].items():
        if sha256(candidate/name)!=pin:raise ValueError('Candidate changed')
    live=json.loads(snapshot.read_text())
    if live['database_writes'] or live['shared_wands_skus']:raise ValueError('Unsafe snapshot scope')
    if live['root'] not in {'/Users/matt/code/mageos-latest','/var/www/html'}:raise ValueError('Unapproved destination')
    rows={r['sku']:r for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv') for r in csv_rows(candidate/'data'/name)}
    if desired_rows is not None:
        if (set(desired_rows)!=set(rows)
                or any(desired_rows[sku]['product_type']!=row['product_type'] for sku,row in rows.items())):
            raise ValueError('Verified product corrections changed catalog scope')
        rows=desired_rows
    if len(rows)!=107688:raise ValueError('Unexpected target size')
    current={sku:r for sku,r in live['products'].items() if r['wands']}
    if set(current)-set(rows):raise ValueError('Existing WANDS products absent from candidate; no deletion authorized by this delta')
    collisions={sku for sku,r in live['products'].items() if not r['wands']} & set(rows)
    if collisions:raise ValueError('Candidate collides with products outside WANDS')
    if reconciliation:
        from catalog_reconciliation import validate
        validate(reconciliation,live,rows)
    elif any(sku.startswith('WANDS-SYN-') for sku in current):raise ValueError('Synthetic additions already exist; reconcile exact applied state')
    is_local=live['root']=='/Users/matt/code/mageos-latest'
    expected=reconciliation['before_wands_products'] if reconciliation else (42994 if is_local else 53844)
    if len(current)!=expected:raise ValueError('Live population drifted from approved baseline')
    additions=[r for sku,r in rows.items() if sku not in current]
    conversions=[]
    for sku,r in current.items():
        desired=rows[sku]
        if r['type']==desired['product_type']:continue
        if not is_local or r['type']!='simple' or desired['product_type']!='configurable':
            raise ValueError('Unexpected type conversion')
        conversions.append({'sku':sku,'source_product_id':desired['wands_product_id'],
                            'expected_type':'simple','target_type':'configurable',
                            # The converter verifies the original 2/4/6
                            # children. Expanded children are linked by import.
                            'child_skus':[g['sku'] for g in variations(desired) if g['sku'].startswith(sku+'-')]})
    if any(len(c['child_skus']) not in {2,4,6} for c in conversions):
        raise ValueError('Original conversion children do not match the installed converter contract')
    # Both installed catalogs have older retained content than the accepted
    # export. Parent-only updates leave stale prices and descriptions behind.
    # Keep existing IDs and stock, and refresh the complete approved WANDS rows.
    updates=[rows[sku] for sku in sorted(current)]
    if any(r['sku'] not in current for r in updates):raise ValueError('Update references a missing existing product')
    if output.exists():raise ValueError('Delta directory must not exist')
    output.mkdir(parents=True)
    for kind in ('simple','configurable','bundle'):
        selected=[r for r in additions if r['product_type']==kind]
        if selected:write_csv(output/('new-'+kind+'.csv'),selected)
    for kind in ('simple','configurable','bundle'):
        selected=[r for r in updates if r['product_type']==kind]
        if selected:write_csv(output/('existing-'+kind+'.csv'),selected)
    with (output/'type-conversions.jsonl').open('x') as stream:
        for record in conversions:stream.write(json.dumps(record,sort_keys=True)+'\n')
    report={'schema':1,'reconciliation':reconciliation,'status':'prepared; images and native import validation still required',
            'target_root':live['root'],'website_code':'wands','website_id':live['website_id'],
            'candidate_sha256':sha256(candidate/'manifest.json'),'snapshot_sha256':sha256(snapshot),
            'before_wands_products':len(current),'after_wands_products':len(rows),
            'product_inserts':len(additions),'insert_types':dict(Counter(r['product_type'] for r in additions)),
            'existing_content_updates':len(updates),'type_conversions':len(conversions),
            'products_deleted':0,'unrelated_products_preserved':live['other_products'],
            'whole_database_expected':len(rows)+live['other_products'],'protected':live['protected'],
            'media_policy':'Replace only WANDS gallery associations with accepted staged images; retain original files and backups.',
            'application_gates':['Complete image export acceptance','Fresh target snapshot matches expected scope',
                                 'Private database and module backup with verified hashes','Exact inverse operation staged',
                                 'Native import validation and attribute-option checks','Preserve existing remote stock on parent updates',
                                 'Post-import protected-data checks, reindex, storefront and cart acceptance'],
            'files':{p.name:sha256(p) for p in sorted(output.iterdir())}}
    write_json(output/'plan.json',report)
    return {k:v for k,v in report.items() if k not in {'protected','files','application_gates','reconciliation'}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(prepare(a.candidate.resolve(),a.snapshot.resolve(),a.output.resolve()),indent=2))


if __name__=='__main__':main()
