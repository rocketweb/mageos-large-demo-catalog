#!/usr/bin/env python3
"""Accept native template output without claiming browser or deployment acceptance."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
import logging
from pathlib import Path
from build_realism_review import write_json
from prepare_catalog import sha256
from verify_catalog_repairs import check
from verify_mageos_rehearsal import index, number, VERSIONS


class OptionsHtml(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.labels={};self.selects={};self.scripts=[]
        self.label=None;self.select=None;self.option=None;self.script=None
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attrs=dict(attributes)
        if tag=='label':
            self.label=attrs.get('for');check(self.label not in self.labels,'Duplicate label')
            self.labels[self.label]=''
        elif tag=='select':
            self.select=attrs.get('id');check(self.select not in self.selects,'Duplicate select')
            self.selects[self.select]={'attributes':attrs,'options':[]}
        elif tag=='option' and self.select:
            self.option={'attributes':attrs,'text':''}
            self.selects[self.select]['options'].append(self.option)
        elif tag=='script' and attrs.get('type')=='application/json':self.script=''

    def handle_data(self, data):
        if self.label is not None:self.labels[self.label]+=data
        if self.option is not None:self.option['text']+=data
        if self.script is not None:self.script+=data

    def handle_endtag(self, tag):
        if tag=='label':self.label=None
        elif tag=='option':self.option=None
        elif tag=='select':self.select=None
        elif tag=='script' and self.script is not None:
            self.scripts.append(json.loads(self.script));self.script=None


def verify_product(product, expected_label, expected_options, pricing):
    config=product['config'];html=OptionsHtml(product['html'])
    check(html.scripts==[config],'Embedded JSON differs from native configuration')
    check(len(config['attributes'])==1,'Wrong attribute count')
    attribute_id,attribute=next(iter(config['attributes'].items()));key='attribute'+attribute_id
    check(set(html.labels)==set(html.selects)=={key},'Wrong rendered controls')
    check(html.labels[key].strip()==expected_label,'Wrong rendered family label')
    select=html.selects[key];attrs=select['attributes']
    check(attrs['name']=='super_attribute['+attribute_id+']' and 'required' in attrs and attrs.get('@change')=='reflectOption','Broken form binding')
    options=attribute['options'];rendered=select['options']
    check(len(rendered)==5 and rendered[0]['attributes']['value']=='','Missing prompt or option')
    check({o['label'] for o in options}==set(expected_options) and len(options)==4,'Wrong assortment choices')
    ids=[]
    for option,actual in zip(options,rendered[1:]):
        check(actual['attributes']['value']==option['id'] and actual['text'].strip()==option['label'],'Rendered option mismatch')
        check(actual['attributes'].get('data-option-label')==option['label'],'Wrong reactive label')
        check(len(option['products'])==1,'Ambiguous child selection')
        child=option['products'][0];ids.append(child)
        check(config['index'][child]=={attribute_id:option['id']},'Wrong child option mapping')
        price=pricing[child]
        check(config['sku'][child]==price['sku'],'Wrong selected child SKU')
        number(config['optionPrices'][child]['finalPrice']['amount'],price['final_price'])
        number(config['optionPrices'][child]['oldPrice']['amount'],price['price'])
    check(len(set(ids))==4 and set(ids)==set(config['index'])==set(config['optionPrices'])==set(config['sku']),'Wrong child coverage')
    check(str(config['productId'])==str(product['product_id']),'Wrong root identity')
    return [o['label'] for o in options]


def verify(args):
    check(not args.output_dir.exists(),'Choose fresh output')
    paths={k:getattr(args,k).resolve() for k in ('baseline','candidate','pricing','plan','rollback_baseline','restored','receipt')}
    data={k:json.loads(p.read_text()) for k,p in paths.items()}
    baseline=data['baseline'];candidate=data['candidate'];prices=data['pricing']
    for filename in ('probe_hyva_options.php','rehearsal_runtime.php','isolate_rehearsal_autoloader.php','probe_mageos_pricing.php'):
        paths[filename]=Path(__file__).with_name(filename)
    check(prices['probe_sha256']==sha256(paths['probe_mageos_pricing.php']) and prices['reindexed'] is False,'Invalid fresh pricing probe')
    check(prices['runtime_sha256']==sha256(paths['rehearsal_runtime.php']) and prices['plan_sha256']==sha256(paths['plan']),'Pricing scope drift')
    check(not any(p['errors'] for p in prices['products']),'Native pricing errors')
    price_index={str(p['entity_id']):p for p in prices['price_index']}
    check(len(price_index)==len(prices['price_index'])==13,'Wrong active price coverage')
    for evidence,enabled in ((baseline,False),(candidate,True)):
        check(evidence['versions']==prices['versions']==VERSIONS and evidence['database']==prices['database'],'Runtime mismatch')
        check(evidence['probe_sha256']==sha256(paths['probe_hyva_options.php']) and evidence['runtime_sha256']==sha256(paths['rehearsal_runtime.php']),'Changed rendering runtime')
        check(evidence['plan_sha256']==sha256(paths['plan']),'Scope drift')
        check(evidence['database_unchanged'] is True and evidence['before_table_hashes']==evidence['after_table_hashes']==prices['after_table_hashes'],'Rendering changed database or evidence drifted')
        check(evidence['candidate_frontend_xml_discovered'] is enabled and evidence['native_template_rendered'] is True,'Wrong candidate mode')
        check(evidence['source_generated_code_excluded'] is True and evidence['autoload_isolation_sha256']==sha256(paths['isolate_rehearsal_autoloader.php']),'Unisolated generated code')
        for flag in ('browser_verified','full_storefront_verified','media_verified','module_deployment_verified','live_writes'):
            check(evidence[flag] is False,'Unsupported acceptance claim')
        check(evidence['shared_piece_count_label_after']=='Piece Count','Shared EAV label mutated')
        template=Path(evidence['template_path']);check(sha256(template)==evidence['template_sha256'],'Template drift');paths[str(template)]=template
        for product in evidence['products']:
            check(product['block_file'].startswith(evidence['isolated_root']+'/generated/'),'Source generated block loaded')
    check(baseline['template_path']==candidate['template_path'] and baseline['template_sha256']==candidate['template_sha256'],'Different baseline/candidate templates')
    module=Path(__file__).resolve().parents[3]/'app/code/RocketWeb/LabCatalog'
    expected_hashes={str(module/p):sha256(module/p) for p in ('Plugin/ConfigurableFamilyLabel.php','etc/frontend/di.xml')}
    check(candidate['candidate_hashes']==expected_hashes and baseline['candidate_hashes']==[],'Candidate content mismatch')
    for path in expected_hashes:paths[path]=Path(path)
    base=index(baseline['products']);changed=index(candidate['products'])
    check(set(base)==set(changed)=={'WANDS-030335','WANDS-035295'},'Wrong parent coverage')
    summaries=[]
    for sku,labels in [('WANDS-030335',['4 Pieces','5 Pieces','6 Pieces','7 Pieces']),('WANDS-035295',['Walnut','Oak','Espresso','Bronze'])]:
        old_label='Piece Count' if sku=='WANDS-030335' else 'Finish'
        new_label='Furniture pieces' if sku=='WANDS-030335' else 'Finish'
        verify_product(base[sku],old_label,labels,price_index)
        order=verify_product(changed[sku],new_label,labels,price_index)
        check(base[sku]['config']==changed[sku]['config'],'Caption fix changed JSON prices, options or media references')
        summaries.append({'sku':sku,'old_label':old_label,'new_label':new_label,'option_order':order,'exact_selection_prices_verified':True})
    restored=data['restored'];old=data['rollback_baseline'];receipt=data['receipt']
    check(restored['database']==candidate['database'] and restored['versions']==old['versions']==VERSIONS,'Wrong rollback runtime')
    check(restored['probe_sha256']==old['probe_sha256']==sha256(paths['probe_mageos_pricing.php']) and restored['runtime_sha256']==old['runtime_sha256']==sha256(paths['rehearsal_runtime.php']),'Rollback runtime drift')
    check(restored['plan_sha256']==old['plan_sha256']==receipt['plan_sha256']==sha256(paths['plan']),'Rollback scope drift')
    check(restored['reindexed'] is True and old['reindexed'] is True,'Rollback needs native reindexing')
    check(restored['products']==old['products'] and restored['price_index']==old['price_index'],'Restored product/price drift')
    metadata={'theme','theme_file','design_change','directory_currency_rate'}
    check(set(restored['after_table_hashes'])==set(old['after_table_hashes'])|metadata,'Unexpected restored table coverage')
    for table,digest in old['after_table_hashes'].items():
        check(restored['after_table_hashes'][table]==digest,'Restored baseline table differs: '+table)
    for table in metadata:
        check(restored['after_table_hashes'][table]==candidate['after_table_hashes'][table],'Synthetic theme metadata changed during rollback')
    dsn=f'mysql:host=127.0.0.1;port=13380;dbname={restored["database"]};charset=utf8mb4'
    check(receipt['dsn_sha256']==hashlib.sha256(dsn.encode()).hexdigest(),'Receipt destination mismatch')
    for suffix in ('.committed','.rolled-back'):paths[suffix]=Path(str(paths['receipt'])+suffix)
    committed=json.loads(paths['.committed'].read_text());inverse=json.loads(paths['.rolled-back'].read_text())
    check(committed['receipt_sha256']==sha256(paths['receipt']) and committed['operations']==len(receipt['operations'])==105,'Invalid migration receipt')
    check(inverse['verified_before_parity'] is True,'Missing verified inverse')
    paths['verifier']=Path(__file__).resolve();args.output_dir.mkdir(parents=True)
    write_json(args.output_dir/'result.json',{'native_template_verified':True,'database_unchanged':True,'parents':summaries,
        'shared_attribute_unchanged':True,'source_generated_code_excluded':True,'browser_verified':False,
        'rollback_verified':True,'restored_baseline_tables':len(old['after_table_hashes']),'retained_synthetic_metadata_tables':sorted(metadata),
        'module_deployment_verified':False,'media_verified':False,'live_writes':False,'publication_approved':False,
        'inputs':{str(path):sha256(path) for path in paths.values()}})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('baseline','candidate','pricing','plan','rollback-baseline','restored','receipt','output-dir'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'),level=logging.INFO)
    try:verify(args);logging.info('Native labels and eight exact option/price bindings verified')
    except Exception:logging.exception('Rendered option verification failed');raise SystemExit(1)
