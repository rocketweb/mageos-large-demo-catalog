#!/usr/bin/env python3
"""Bind browser checks and visual observations to the accepted native rollback evidence."""
import argparse
import json
import logging
from pathlib import Path
from build_realism_review import write_json
from prepare_catalog import sha256
from test_hyva_browser_components import check_state
from verify_catalog_repairs import check


def verify(args):
    check(not args.output_dir.exists(),'Choose fresh output')
    paths={name:getattr(args,name).resolve() for name in ('result','manifest','observations','native_acceptance')}
    result,manifest,observations,native=[json.loads(paths[k].read_text()) for k in ('result','manifest','observations','native_acceptance')]
    check(result['manifest_sha256']==sha256(paths['manifest']),'Browser manifest drift')
    runner=Path(__file__).with_name('test_hyva_browser_components.py');paths['runner']=runner
    check(result['runner_sha256']==sha256(runner),'Browser runner drift')
    for packet in (manifest,native):
        for path,digest in packet['inputs'].items():check(sha256(Path(path))==digest,'Acceptance input drift')
    check(native['native_template_verified'] is True and native['rollback_verified'] is True and native['captured_theme_verified'] is True,'Native acceptance or recovery incomplete')
    check(result['count']==24 and result['selected_cases']==16 and result['required_or_reset_cases']==8,'Incomplete browser totals')
    check(result['native_component_browser_verified'] is True and result['full_storefront_verified'] is False and result['persisted_cart_verified'] is False and result['media_loaded'] is False and result['live_writes'] is False,'Incorrect browser boundary')
    expected={}
    for product in manifest['products']:
        check(sha256(Path(product['file']))==product['sha256'],'Rendered page drift')
        for width in (1920,390):
            for scenario,case in [('empty-required',None),('cleared-required',None)]+[('selected-'+case['option_id'],case) for case in product['cases']]:
                expected[(product['sku'],width,scenario)]=(product,case)
    observed={(c['sku'],c['width'],c['scenario']):c for c in result['checks']}
    check(len(observed)==len(result['checks'])==len(expected)==24 and set(observed)==set(expected),'Missing or duplicate browser scenario')
    for key,(product,case) in expected.items():check_state(observed[key]['observed'],product,case,reset=key[2]=='cleared-required')
    check(set(observations)==set(result['screenshots']) and len(observations)==4,'Incomplete screenshot review')
    for path,digest in result['screenshots'].items():
        check(sha256(Path(path))==digest==observations[path]['sha256'],'Screenshot drift')
        check(observations[path]['accepted'] is True and observations[path]['scope']=='native_component_only','Visual check incomplete')
    paths['verifier']=Path(__file__).resolve();args.output_dir.mkdir(parents=True)
    write_json(args.output_dir/'result.json',{'browser_component_verified':True,'browser_cases':24,'selected_cases':16,
        'screenshots_reviewed':4,'full_storefront_verified':False,'persisted_cart_verified':False,'media_verified':False,
        'rollback_verified':True,'remote_catalog_writes':0,'publication_approved':False,
        'inputs':{str(p):sha256(p) for p in paths.values()}})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('result','manifest','observations','native-acceptance','output-dir'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'),level=logging.INFO)
    try:verify(args);logging.info('Browser behavior, screenshots and native rollback accepted')
    except Exception:logging.exception('Browser evidence acceptance failed');raise SystemExit(1)
