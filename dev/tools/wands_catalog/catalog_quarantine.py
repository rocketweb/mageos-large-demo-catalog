"""Exact user-approved 213-SKU quarantine, separate from image acceptance."""
from pathlib import Path
import json
from build_expanded_catalog import csv_rows,digest
from prepare_catalog import sha256

CANDIDATE='921e5e1a0d8a386c93bf0f80dd6543c9d3561e5ad27e31df5b80b9d3e0d8502e'
PROPOSAL='27a78eca69ecd2b31b3d97983238d0aeb3b3aefb54d571fb3dbd7c041e72dd79'
INVERSE='5a4ac73ec47df05a5671afaa7aed5afe29bdd03658780537b4dbce830f5a798c'
PROTECTED='WANDS-SYN-S-KITCHEN-TABLETOP-02007'
AUTHORIZATION='continue wiuth recommendations: exact reviewed 213-SKU quarantine on Studio and Comtom; preserve approved Keep'

def approved_rows(proposal,candidate):
    if sha256(proposal)!=PROPOSAL or sha256(candidate/'manifest.json')!=CANDIDATE:
        raise ValueError('Quarantine differs from approved proposal or candidate')
    entries=csv_rows(proposal)
    targets={r['sku']:r for n in ('1-simple.csv','2-configurable.csv','3-bundle.csv') for r in csv_rows(candidate/'data'/n)}
    if len(entries)!=213 or len({r['sku'] for r in entries})!=213 or any(r['sku']==PROTECTED for r in entries):
        raise ValueError('Quarantine scope or protected Keep changed')
    for e in entries:
        r=targets.get(e['sku'])
        if (not r or r['product_type']!='simple' or r['product_online']!=e['product_online_before']
                or r['visibility']!=e['visibility_before'] or e['product_online_proposed']!='2'
                or e['visibility_proposed']!='Not Visible Individually'):
            raise ValueError('Quarantine source or proposed fields changed')
    return entries

def policy(run,desc=None):
    run=Path(run).resolve();path=run/'catalog-quarantine.json'
    if not path.exists():return None
    desc=desc or json.loads((run/'run.json').read_text());p=json.loads(path.read_text())
    if (p.get('schema')!=1 or p.get('authorization')!=AUTHORIZATION
            or p.get('source_run_sha256')!=sha256(run/'run.json')
            or p.get('source_candidate_sha256')!=desc['candidate_sha256'] or desc['candidate_sha256']!=CANDIDATE
            or p.get('review_identity')!=desc['review_identity']):raise ValueError('Quarantine policy belongs to another run')
    entries=approved_rows(Path(p['proposal_path']),Path(desc['candidate']))
    if p.get('entries')!=entries or p.get('proposal_sha256')!=PROPOSAL or sha256(Path(p['inverse_path']))!=INVERSE:
        raise ValueError('Quarantine receipt differs from approved scope')
    return p

def skus(p):return {r['sku'] for r in p['entries']} if p else set()

def all_quarantined(job,excluded):
    if not excluded:return False
    assigned=set(job['skus'])
    return bool(assigned) and assigned<=excluded

def apply_fields(rows,p):
    for e in (p or {}).get('entries',[]):
        row=rows[e['sku']]
        if row['product_online']!=e['product_online_before'] or row['visibility']!=e['visibility_before']:
            raise ValueError('Quarantine conflicts with another product correction')
        row.update(product_online='2',visibility='Not Visible Individually')

def verified_package(package,manifest,run):
    pin=manifest.get('catalog_quarantine_sha256')
    if not pin:return None
    if run is None:raise ValueError('Quarantine requires the trusted run')
    p=policy(run);path=package/'catalog-quarantine.json'
    if not p or not path.is_file() or digest(p)!=pin or json.loads(path.read_text())!=p:
        raise ValueError('Package quarantine differs from trusted scope')
    if 'catalog-quarantine.json' not in manifest['files']:raise ValueError('Quarantine receipt missing from package inventory')
    return p
