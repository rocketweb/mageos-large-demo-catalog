#!/usr/bin/env python3
"""Build private offline pages from native Hyva render evidence, without mock pricing."""
import argparse
from html import escape
import json
import logging
from pathlib import Path
import shutil
from build_realism_review import write_json
from prepare_catalog import sha256
from verify_catalog_repairs import check
from verify_hyva_options import verify_product


def build(args):
    check(not args.output_dir.exists(),'Choose fresh output')
    source=json.loads(args.evidence.read_text());pricing=json.loads(args.pricing.read_text())
    check(source['browser_components_rendered'] is True and source['captured_theme_verified'] is True,'Native captured-theme components required')
    check(source['probe_sha256']==sha256(Path(__file__).with_name('probe_hyva_options.php')),'Rendering probe drift')
    check(source['database_unchanged'] is True and source['after_table_hashes']==pricing['after_table_hashes'],'Pricing or database drift')
    for path,digest in source['component_template_hashes'].items():check(sha256(Path(path))==digest,'Installed asset drift')
    prices={str(p['entity_id']):p for p in pricing['price_index']}
    args.output_dir.mkdir(parents=True)
    assets=args.output_dir/'assets';assets.mkdir()
    shutil.copyfile(source['browser_assets']['alpine'],assets/'alpine.js')
    shutil.copyfile(source['browser_assets']['styles'],assets/'styles.css')
    entries=[]
    for product in source['products']:
        label='Furniture pieces' if product['sku']=='WANDS-030335' else 'Finish'
        labels=['4 Pieces','5 Pieces','6 Pieces','7 Pieces'] if label=='Furniture pieces' else ['Walnut','Oak','Espresso','Bronze']
        verify_product(product,label,labels,prices)
        attribute_id,attribute=next(iter(product['config']['attributes'].items()))
        cases=[]
        for option in attribute['options']:
            child=option['products'][0]
            cases.append({'option_id':option['id'],'label':option['label'],'child_id':child,'sku':prices[child]['sku'],'price':float(prices[child]['final_price'])})
        init='''<script>
const BASE_URL='http://127.0.0.1:18880/';window.COOKIE_CONFIG={};
window.wandsEvents=[];window.wandsPrices=[];window.wandsErrors=[];
window.addEventListener('error',e=>wandsErrors.push(e.message));
window.addEventListener('unhandledrejection',e=>wandsErrors.push(String(e.reason)));
window.addEventListener('configurable-selection-changed',e=>wandsEvents.push(JSON.parse(JSON.stringify(e.detail))));
'''+f"window.addEventListener('update-prices-{product['product_id']}',e=>wandsPrices.push(JSON.parse(JSON.stringify(e.detail))));"+'''</script>'''
        components=product['components'];file=args.output_dir/(product['sku']+'.html')
        html='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        html+='<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'self\' \'unsafe-inline\' \'unsafe-eval\'; style-src \'self\' \'unsafe-inline\'; connect-src \'none\'; form-action \'none\'; base-uri \'none\'">'
        html+='<title>'+escape(product['sku'])+' local component test</title><link rel="stylesheet" href="assets/styles.css">'+init+components['hyva_js']
        html+='<script defer src="assets/alpine.js"></script></head><body><main id="maincontent" class="max-w-xl mx-auto p-6">'
        html+='<h1 class="text-2xl font-bold mb-4">'+escape(product['sku'])+'</h1><p class="mb-6">Local component rehearsal. No live cart, checkout or media loading.</p>'
        html+='<section aria-label="Product price">'+components['price_html']+'</section>'
        html+=components['options_js']+'<form id="product-options" onsubmit="event.preventDefault()">'+product['html']+'</form></main></body></html>'
        file.write_text(html)
        entries.append({'sku':product['sku'],'product_id':str(product['product_id']),'attribute_id':attribute_id,'label':label,'cases':cases,'file':str(file.resolve()),'sha256':sha256(file),
            'initial_price':float(pricing['products'][next(i for i,p in enumerate(pricing['products']) if p['sku']==product['sku'])]['checks']['pricing_final'])})
    paths=[args.evidence,args.pricing,Path(__file__),assets/'alpine.js',assets/'styles.css']
    write_json(args.output_dir/'manifest.json',{'products':entries,'native_business_components':True,'full_storefront':False,
        'network_policy':'no connections, forms or media requests; local scripts and styles only','browser_verified':False,
        'inputs':{str(p.resolve()):sha256(p) for p in paths}})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('evidence','pricing','output-dir'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'),level=logging.INFO)
    try:build(args);logging.info('Offline native component pages prepared; browser acceptance pending')
    except Exception:logging.exception('Browser fixture preparation failed');raise SystemExit(1)
