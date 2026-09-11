#!/usr/bin/env python3
"""Exercise native offline Hyva components with an isolated named browser session."""
import argparse
import json
import logging
from pathlib import Path
import re
import subprocess
import time
from build_realism_review import write_json
from prepare_catalog import sha256
from verify_catalog_repairs import check

STATE_JS='''(() => {
const event=window.wandsEvents.at(-1), price=window.wandsPrices.at(-1),select=document.querySelector('select');
return {priceText:document.querySelector('[aria-label="Product price"]').innerText,
valid:document.querySelector('form').checkValidity(),value:select.value,
options:Array.from(select.options).map(o=>({value:o.value,text:o.textContent,disabled:o.disabled})),
selection:event?{productId:event.productId,optionId:event.optionId,value:event.value,productIndex:event.productIndex,candidates:event.candidates,skuCandidates:event.skuCandidates}:null,
priceEvent:price?{amount:price.finalPrice.amount,isMinimalPrice:price.isMinimalPrice}:null,
errors:window.wandsErrors,overflow:document.documentElement.scrollWidth>innerWidth};
})()'''


def visible_price_ready(price):
    return r'''(() => {const amounts=Array.from(document.querySelector('[aria-label="Product price"]').innerText.matchAll(/\$([0-9,]+\.[0-9]{2})/g),m=>Number(m[1].replaceAll(',','')));return amounts.length===1 && amounts[0]==='''+json.dumps(price)+';})()'


def check_state(state,product,case=None,reset=False):
    check(state['errors']==[] and state['overflow'] is False,'Browser errors or horizontal overflow')
    expected=case['price'] if case else product['initial_price']
    values=[float(n.replace(',','')) for n in re.findall(r'\$([0-9,]+\.[0-9]{2})',state['priceText'])]
    check(values==[expected],'Visible native price differs from indexed price')
    options=state['options']
    check(len(options)==5 and options[0]['value']=='','Wrong visible option count')
    for actual,wanted in zip(options[1:],product['cases']):
        check(actual['value']==wanted['option_id'] and actual['text'].startswith(wanted['label']) and actual['disabled'] is False,'Wrong or disabled visible choice')
    if case:
        event=state['selection'];price=state['priceEvent']
        check(state['valid'] is True and state['value']==case['option_id'],'Valid selection did not satisfy required control')
        check(event['productId']==product['product_id'] and event['optionId']==product['attribute_id'] and event['value']==case['option_id'],'Wrong selection event')
        check(str(event['productIndex'])==case['child_id'] and event['candidates']==[case['child_id']] and event['skuCandidates']==[case['sku']],'Wrong selected child identity')
        check(price['amount']==expected and price['isMinimalPrice'] is False,'Wrong selected price event')
    else:
        check(state['valid'] is False and state['value']=='','Empty selection passed required validation')
        if reset:check(state['priceEvent']['amount']==expected and state['priceEvent']['isMinimalPrice'] is True,'Clear-selection price did not reset')


def run(args):
    check(not args.output_dir.exists(),'Choose fresh output')
    manifest=json.loads(args.manifest.read_text())
    for path,digest in manifest['inputs'].items():check(sha256(Path(path))==digest,'Browser fixture input changed')
    check(len(manifest['products'])==2,'Wrong browser scope')
    for product in manifest['products']:check(sha256(Path(product['file']))==product['sha256'],'Browser page changed')
    args.output_dir.mkdir(parents=True);session='wands-options-'+sha256(args.manifest)[:12]
    started=time.monotonic();calls=0;checks=[];screenshots={}
    def browser(*command):
        nonlocal calls
        calls+=1
        result=subprocess.run([args.browser,'--session',session,'--json',*command],capture_output=True,text=True,timeout=45)
        logging.info('Browser %s\n%s\n%s',command,result.stdout,result.stderr)
        check(result.returncode==0,'Browser command failed; inspect log')
        response=json.loads(result.stdout);check(response['success'] is True,'Browser action failed')
        return response['data']
    def select_ref(product):
        refs=browser('snapshot','-i')['refs']
        matches=[key for key,value in refs.items() if value['role']=='combobox' and value['name']==product['label']]
        check(len(matches)==1,'Native accessible dropdown not found')
        return '@'+matches[0]
    try:
        for width,height in ((1920,1080),(390,844)):
            for product in manifest['products']:
                browser('--allow-file-access','open',Path(product['file']).as_uri())
                browser('set','viewport',str(width),str(height))
                browser('wait','--fn',"!!window.Alpine && !!document.querySelector('[x-data=\"initConfigurableDropdownOptions\"]')._x_dataStack")
                initial=browser('eval',STATE_JS)['result'];check_state(initial,product)
                checks.append({'sku':product['sku'],'width':width,'scenario':'empty-required','observed':initial})
                for case in product['cases']:
                    reference=select_ref(product);browser('scrollintoview',reference);browser('select',reference,case['option_id'])
                    condition='window.wandsEvents.at(-1)?.value === '+json.dumps(case['option_id'])+' && '+visible_price_ready(case['price'])
                    browser('wait','--fn',condition)
                    state=browser('eval',STATE_JS)['result'];check_state(state,product,case)
                    checks.append({'sku':product['sku'],'width':width,'scenario':'selected-'+case['option_id'],'expected':case,'observed':state})
                screenshot=args.output_dir/(product['sku']+'-'+str(width)+'.png')
                browser('screenshot','--full',str(screenshot.resolve()));screenshots[str(screenshot.resolve())]=sha256(screenshot)
                browser('select',select_ref(product),'')
                browser('wait','--fn',"window.wandsPrices.at(-1)?.isMinimalPrice === true && "+visible_price_ready(product['initial_price']))
                state=browser('eval',STATE_JS)['result'];check_state(state,product,reset=True)
                checks.append({'sku':product['sku'],'width':width,'scenario':'cleared-required','observed':state})
                check(browser('errors')['errors']==[],'Browser page errors')
        check(len(checks)==24,'Incomplete browser coverage')
        write_json(args.output_dir/'result.json',{'checks':checks,'count':24,'selected_cases':16,'required_or_reset_cases':8,
            'viewports':[[1920,1080],[390,844]],'native_component_browser_verified':True,'full_storefront_verified':False,
            'persisted_cart_verified':False,'media_loaded':False,'live_writes':False,'screenshots':screenshots,
            'visual_review_pending':True,'browser_version':subprocess.run([args.browser,'--version'],capture_output=True,text=True,check=True).stdout.strip(),
            'calls':calls,'elapsed_seconds':round(time.monotonic()-started,2),'manifest_sha256':sha256(args.manifest),'runner_sha256':sha256(Path(__file__))})
    finally:browser('close')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--browser',default='agent-browser');args=parser.parse_args()
    args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'),level=logging.INFO)
    try:run(args);logging.info('All 24 native component browser scenarios verified')
    except Exception:logging.exception('Browser component acceptance failed');raise SystemExit(1)
