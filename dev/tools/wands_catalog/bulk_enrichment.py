"""Build a local, versioned catalog-depth candidate from an authenticated release.

No live imports, model calls, network access or published-asset replacement.
"""
import argparse
from bisect import bisect_left
from collections import Counter, defaultdict, deque
import copy
import csv
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import html
import io
import json
import logging
from pathlib import Path
import re
import sys
import tarfile
import tempfile

from catalog_depth import ATTRIBUTES, COMPLEMENTS, extract_specs, recommend, tokens
from prepare_catalog import department, sha256
from synthetic_dimensions import add_dimensions, source_context, summarize_family

sys.path.insert(0, str(Path(__file__).with_name('distribution')))
from release import closure, dependencies, write_archive, verify_release
from build_release import csv_bytes, json_bytes

VERSION = 'wands-bulk-enrichment-v1'
SPEC_MARKER = '<section data-wands-specifications="v1">'
DISCLOSURE = 'Contains synthetic lab specifications. Dimensions and variant options are test data, not manufacturer measurements or fit guarantees. See the description for per-field labels.'


def money(value):
    return str(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def enabled(row):
    return row.get('product_online') == '1'


def visible(row):
    return enabled(row) and row.get('visibility') in {'Catalog, Search', 'Catalog', 'Search'}


def sale_price(row):
    base = Decimal(row.get('price') or '0')
    special = Decimal(row.get('special_price') or '0')
    return special if 0 < special < base else base


def family_map(rows):
    parents, options, axes = {}, {}, {}
    for sku, row in rows.items():
        if row['product_type'] != 'configurable':
            continue
        axes[sku] = set()
        for variation in row['configurable_variations'].split('|'):
            values = dict(field.split('=', 1) for field in variation.split(','))
            child = values.pop('sku')
            if child not in rows or child in parents:
                raise ValueError('Missing child or multiple parents: '+child)
            if any(rows[child].get(k) != v for k, v in values.items()):
                raise ValueError('Current child option mismatch: '+child)
            parents[child], options[child] = sku, values
            axes[sku].update(values)
    return parents, options, axes


def enrich_specs(rows, source, corrected, synthetic=True):
    parents, options, axes = family_map(rows)
    records = []
    for sku, row in sorted(rows.items()):
        if not enabled(row) or row['product_type'] == 'bundle':
            continue
        match = re.match(r'^WANDS-(\d{6})(?:-|$)', sku)
        if not match or str(int(match[1])) not in source:
            raise ValueError('Missing WANDS source identity: '+sku)
        pid = str(int(match[1]))
        original = source[pid]
        root = parents.get(sku, sku)
        axis_codes = axes.get(root, set())
        facts, withheld = extract_specs(original, axis_codes, options.get(sku, {}))
        record = {'sku':sku, 'source_product_id':pid, 'name':row['name'], 'kind':row['product_type'],
            'source_class':row.get('wands_product_class') or original['product_class'],
            'department':department(original), 'price':float(sale_price(row)),
            'salable':row.get('is_in_stock') == '1', 'axis_codes':sorted(axis_codes),
            'variant_options':options.get(sku, {}), 'specifications':facts, 'withheld':withheld,
            'design_context':source_context(original)}
        if sku in parents:
            record['parent_sku'] = parents[sku]
        previous = corrected.get(sku)
        if previous:
            if (previous['name'] != row['name'] or previous['kind'] != row['product_type']
                    or previous['variant_options'] != record['variant_options']):
                raise ValueError('Corrected definition disagrees with release: '+sku)
            # Accepted corrections outrank raw source conflicts and historical SKU tokens.
            for key in ('specifications', 'withheld', 'dimension_design', 'design_context', 'source_class'):
                if key in previous:
                    record[key] = copy.deepcopy(previous[key])
        elif synthetic and row['product_type'] == 'simple':
            record = add_dimensions(record)
        records.append(record)
    children = defaultdict(list)
    for record in records:
        if record.get('parent_sku'):
            children[record['parent_sku']].append(record)
    if synthetic:
        records = [summarize_family(r,children[r['sku']]) if r['kind']=='configurable'
                   and r['sku'] not in corrected else r for r in records]
    return records


def build_links(rows, records):
    candidates = [r for r in records if visible(rows[r['sku']]) and r['salable'] and r['price']>0]
    indexes = defaultdict(list)
    appearance = ('lab_spec_style','lab_spec_color','lab_spec_finish')
    for record in candidates:
        for cls in tokens(record['source_class']):
            for code in appearance:
                fact = record['specifications'].get(code)
                if fact and not fact.get('synthetic'):
                    indexes[(cls,code,fact['value'])].append(record)
    prices = {}
    for key, bucket in indexes.items():
        bucket.sort(key=lambda r:(r['price'],r['sku']))
        prices[key] = [r['price'] for r in bucket]
    result = {}
    for current in candidates:
        classes = tokens(current['source_class'])
        allowed = classes | set().union(*(COMPLEMENTS.get(c,set()) for c in classes))
        pool = {}
        for cls in allowed:
            for code in appearance:
                fact = current['specifications'].get(code)
                if not fact or fact.get('synthetic'):
                    continue
                key = (cls,code,fact['value'])
                bucket = indexes.get(key,[])
                center = bisect_left(prices.get(key,[]),current['price'])
                for other in bucket[max(0,center-24):center+24]:
                    pool[other['sku']] = other
        choices = recommend(current,list(pool.values()))
        for matches in choices.values():
            for match in matches:
                match['review_required'] = False
                match['decision'] = 'bulk synthetic merchandising, source-backed class and appearance rules'
        related = [r['target_sku'] for r in choices['alternatives']]
        complements = [r['target_sku'] for r in choices['complements']]
        if related or complements:
            result[current['sku']] = {'related_skus':related, 'crosssell_skus':complements,
                'evidence':choices, 'basis':'deterministic synthetic lab merchandising, not physical compatibility'}
    return result


def medium_selection(rows, target=5000):
    if target <= 0:
        raise ValueError('Medium target must be positive')
    parents = defaultdict(set)
    for sku, row in rows.items():
        if row['product_type']=='configurable':
            for child in dependencies(row):
                parents[child].add(sku)
    selected = set()
    def include(seed):
        pending = [seed]
        while pending:
            sku = pending.pop()
            if sku in selected:
                continue
            selected.add(sku)
            pending.extend((dependencies(rows[sku]) | parents[sku])-selected)
    # Keep all room bundles and their entire dependency families.
    for sku in sorted(rows):
        if rows[sku]['product_type']=='bundle' and enabled(rows[sku]):
            include(sku)
    groups = defaultdict(list)
    for sku,row in sorted(rows.items()):
        if visible(row):
            groups[row.get('wands_product_class','Unknown')].append(sku)
    queues = [deque(sorted(pool,key=lambda sku:hashlib.sha256(sku.encode()).hexdigest()))
              for _,pool in sorted(groups.items())]
    while len(selected)<target and any(queues):
        for queue in queues:
            if queue and len(selected)<target:
                include(queue.popleft())
    return sorted(selected)


def commerce_scenarios(rows):
    scenarios = []
    def add(kind, sku, changes, expected):
        scenarios.append({'id':kind+':'+sku, 'kind':kind, 'root_sku':sku,
            'apply_to':'isolated disposable fixture only', 'clock':'2026-10-15T12:00:00Z',
            'preconditions':['USD','no tax, shipping, catalog/cart rules or customer-group discounts',
                             'restore baseline between scenarios','reindex before checking'],
            'changes':changes, 'restore':{s:{k:{'present':k in rows[s], 'value':rows[s].get(k)}
                for k in values} for s,values in changes.items()}, 'expected':expected,
            'magento_runtime_verified':False})
    simple = [r for _,r in sorted(rows.items()) if visible(r) and r['product_type']=='simple' and sale_price(r)>0][:60]
    for row in simple:
        sku, price = row['sku'], Decimal(row['price'])
        discount = money(price*Decimal('.85'))
        add('active-sale',sku,{sku:{'special_price':discount,'special_from_date':'2026-10-01 00:00:00',
            'special_to_date':'2026-10-31 23:59:59'}},{'unit_price_ex_tax':discount})
        add('expired-sale',sku,{sku:{'special_price':discount,'special_from_date':'2026-09-01 00:00:00',
            'special_to_date':'2026-09-30 23:59:59'}},{'unit_price_ex_tax':money(price)})
        add('out-of-stock',sku,{sku:{'manage_stock':'1','use_config_manage_stock':'0','qty':'0',
            'is_in_stock':'0','backorders':'0','use_config_backorders':'0'}},{'salable':False})
        add('backorder-notify',sku,{sku:{'manage_stock':'1','use_config_manage_stock':'0','qty':'0',
            'is_in_stock':'1','backorders':'2','use_config_backorders':'0','min_qty':'0','use_config_min_qty':'0'}},
            {'quantity':1,'can_backorder':True,'notify_customer':True})
        add('tier-price',sku,{sku:{'special_price':'','tier_prices':[{'qty':5,'unit_price':discount,
            'customer_group':'ALL GROUPS','website':'wands'}]}},
            {'quantity':5,'unit_price_ex_tax':discount,'line_total_ex_tax':money(Decimal(discount)*5)})
    for sku,row in sorted(rows.items()):
        if not enabled(row) or row['product_type'] not in {'configurable','bundle'}:
            continue
        children = sorted(dependencies(row))
        if row['product_type']=='configurable':
            if sum(s['kind']=='unavailable-variant' for s in scenarios)>=50:
                continue
            add('unavailable-variant',sku,{children[0]:{'manage_stock':'1','use_config_manage_stock':'0',
                'qty':'0','is_in_stock':'0','backorders':'0','use_config_backorders':'0'}},
                {'unavailable_child':children[0], 'other_child_baseline_preserved':children[1:]})
        else:
            selections = [dict(f.split('=',1) for f in group.split(',')) for group in row['bundle_values'].split('|')]
            group = selections[0]['name']
            required = {s['sku'] for s in selections if s['name']==group}
            add('required-bundle-option-unavailable',sku,{s:{'manage_stock':'1','use_config_manage_stock':'0',
                'qty':'0','is_in_stock':'0','backorders':'0','use_config_backorders':'0'} for s in sorted(required)},
                {'required_option':group,'can_purchase_complete_bundle':False})
    return scenarios


def search_cases(rows, records, limit=500):
    cases, seen = [], set()
    for r in sorted(records,key=lambda r:hashlib.sha256(r['sku'].encode()).hexdigest()):
        if not visible(rows[r['sku']]):
            continue
        cls = r['source_class'].split('|')[0].strip().lower()
        facts = r['specifications']
        for code in ('lab_spec_material','lab_spec_color','lab_spec_style','lab_spec_finish'):
            if code not in facts:
                continue
            query = str(facts[code]['value']).lower()+' '+cls
            if query in seen:
                continue
            seen.add(query)
            cases.append({'query_id':'enriched-'+hashlib.sha256(query.encode()).hexdigest()[:12],
                'query':query,'candidate_sku':r['sku'],'constraint':{code:facts[code]['value']},
                'origin':'attribute-derived synthetic shopper query seed','judgment':None,
                'ranking_ground_truth':False,'status':'requires independent intent review and pooled judgments',
                'family_partition':'holdout' if int(hashlib.sha256(r['source_product_id'].encode()).hexdigest()[:8],16)%5==0 else 'development'})
            if len(cases)>=limit:
                return cases
    return cases


def specification_html(record):
    if not record['specifications']:
        return ''
    entries = []
    for code,fact in sorted(record['specifications'].items()):
        label = ATTRIBUTES[code]['label']
        suffix = ' (synthetic lab specification)' if fact.get('synthetic') else ''
        entries.append('<li>'+html.escape(label+': '+str(fact['value'])+suffix)+'</li>')
    return SPEC_MARKER+'<h3>Product specifications</h3><ul>'+''.join(entries)+'</ul>' + \
        '<p>Synthetic values are test data, not manufacturer measurements or fit guarantees.</p></section>'


def build(args):
    if args.output.exists():
        raise ValueError('Choose a new output directory')
    verify_release(args.release_dir,args.manifest_sha256)
    input_paths = {'manifest':args.release_dir/'manifest.json','source':args.source,
        'definitions':args.definitions/'manifest.json','builder':Path(__file__),
        'depth':Path(__file__).with_name('catalog_depth.py'),
        'dimensions':Path(__file__).with_name('synthetic_dimensions.py')}
    pins = {k:sha256(p) for k,p in input_paths.items()}
    baseline_manifest = json.loads((args.release_dir/'manifest.json').read_text())
    if pins['source'] != baseline_manifest['upstream']['product_csv_sha256']:
        raise ValueError('Source differs from the authenticated WANDS release')
    with tarfile.open(args.release_dir/'catalog.tar') as archive:
        def read(name):
            return archive.extractfile(name).read()
        data = {m.name:read(m.name) for m in archive.getmembers() if m.isfile()}
    rows = {}
    for filename in ('data/1-simple.csv','data/2-configurable.csv','data/3-bundle.csv'):
        for row in csv.DictReader(io.StringIO(data[filename].decode())):
            if row['sku'] in rows:
                raise ValueError('Duplicate release SKU')
            rows[row['sku']]=row
    source = {r['product_id']:r for r in csv.DictReader(args.source.open(),delimiter='\t')}
    definition_manifest=json.loads((args.definitions/'manifest.json').read_text())
    corrected={}
    for name in ('candidate-products.jsonl','candidate-children.jsonl'):
        if sha256(args.definitions/name)!=definition_manifest['outputs'][name]:
            raise ValueError('Definition packet changed')
        for line in (args.definitions/name).read_text().splitlines():
            r=json.loads(line)
            if r['sku'] in rows and enabled(rows[r['sku']]):
                corrected[r['sku']]=r
    logging.info('Enriching %d current products with %d retained definitions',len(rows),len(corrected))
    records=enrich_specs(rows,source,corrected)
    logging.info('Structured specs complete; building indexed merchandising links')
    links=build_links(rows,records)
    enriched=copy.deepcopy(rows)
    for record in records:
        row=enriched[record['sku']]
        row.update({k:str(f['value']) for k,f in record['specifications'].items()})
        if any(f.get('synthetic') for f in record['specifications'].values()):
            row['lab_spec_disclosure'] = DISCLOSURE
        if SPEC_MARKER in row.get('description',''):
            raise ValueError('Already enriched input; do not append duplicate specifications')
        row['description']=row.get('description','')+specification_html(record)
    for sku,link in links.items():
        for code in ('related_skus','crosssell_skus'):
            if link[code]:
                enriched[sku][code]=','.join(link[code])
    for sku in rows:
        for key in ('sku','url_key','product_type','configurable_variations','bundle_values','price','qty','product_online'):
            if rows[sku].get(key)!=enriched[sku].get(key):
                raise ValueError('Protected catalog field changed: '+sku+' '+key)
    selected=medium_selection(rows,args.medium_target)
    scenarios=commerce_scenarios(rows)
    queries=search_cases(rows,records)
    coverage={'products':len(rows),'enriched_records':len(records),
        'records_with_specs':sum(bool(r['specifications']) for r in records),
        'specification_values':sum(len(r['specifications']) for r in records),
        'synthetic_values':sum(f.get('synthetic',False) for r in records for f in r['specifications'].values()),
        'attribute_coverage':dict(Counter(k for r in records for k in r['specifications'])),
        'linked_products':len(links),'related_links':sum(len(v['related_skus']) for v in links.values()),
        'crosssell_links':sum(len(v['crosssell_skus']) for v in links.values()),
        'medium_records':len(selected),'medium_types':dict(Counter(rows[s]['product_type'] for s in selected)),
        'commerce_scenarios':len(scenarios),'search_query_seeds':len(queries),
        'dimension_status':dict(Counter(r.get('dimension_design',{}).get('status','not_requested') for r in records)),
        'live_writes':0,'magento_import_verified':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.enrichment-',dir=args.output.parent) as temp:
        stage=Path(temp)/'candidate';stage.mkdir()
        def jsonl(name,entries):
            (stage/name).write_text(''.join(json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n' for r in entries))
        jsonl('specifications.jsonl',records)
        jsonl('merchandising.jsonl',[{'sku':k,**v} for k,v in sorted(links.items())])
        jsonl('commerce-scenarios.jsonl',scenarios)
        jsonl('search-query-seeds.jsonl',queries)
        (stage/'coverage.json').write_bytes(json_bytes(coverage))
        (stage/'medium-skus.json').write_bytes(json_bytes(selected))
        # Data-only overlay: original media archives stay byte-identical and separate.
        for index,kind in enumerate(('simple','configurable','bundle'),1):
            data[f'data/{index}-{kind}.csv']=csv_bytes([r for _,r in sorted(enriched.items()) if r['product_type']==kind])
        options=json.loads(data['data/attribute-options.json'])
        for code,rule in ATTRIBUTES.items():
            if rule['kind']=='select':
                options[code]=rule['options']
        data['data/attribute-options.json']=json_bytes(options)
        data['data/enrichment-coverage.json']=json_bytes(coverage)
        data['data/specification-provenance.jsonl']=(stage/'specifications.jsonl').read_bytes()
        data['data/merchandising-provenance.jsonl']=(stage/'merchandising.jsonl').read_bytes()
        data['docs/ENRICHMENT.txt']=b'Local fresh-install candidate. Not a live update or verified Magento import. Apply the current catalog module, including depth attributes. Retain specification provenance separately. Original media hashes are unchanged.\n'
        artifact=write_archive(stage/'catalog-enriched.tar',data)
        if any(sha256(p)!=pins[k] for k,p in input_paths.items()):
            raise ValueError('Input changed during build')
        manifest={'version':VERSION,'baseline_manifest_sha256':args.manifest_sha256,'inputs':pins,
            'coverage':coverage,'catalog_artifact':artifact,
            'outputs':{p.name:sha256(p) for p in sorted(stage.iterdir())},
            'status':'local candidate, not deployed or published',
            'medium_profile':'dependency-closed SKU selection; media packaging is a separate step',
            'scenario_policy':'independent fixtures, never apply all scenarios to one catalog',
            'benchmark_policy':'unjudged seeds, not WANDS labels or independent ranking ground truth'}
        (stage/'manifest.json').write_bytes(json_bytes(manifest))
        stage.rename(args.output)
    logging.info('COMPLETE %s',json.dumps(coverage,sort_keys=True))
    return coverage


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('release-dir','source','definitions','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--medium-target',type=int,default=5000)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output.with_suffix('.log'),level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        build(args)
        return 0
    except Exception:
        logging.exception('Bulk enrichment stopped; no live writes')
        return 1


if __name__=='__main__':
    raise SystemExit(main())
