#!/usr/bin/env python3
"""Build an immutable, additive QA fixture package. No store, model or network calls."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import io
import itertools
import json
from pathlib import Path, PurePosixPath
import shutil
import zipfile

VERSION = 'wands-qa-2026.10.06-v1'
PREFIX = 'WANDS-QA-'
CATEGORY = 'WANDS Catalog/QA Fixtures'
TYPES = {'simple', 'virtual', 'downloadable', 'configurable', 'bundle', 'grouped'}
OPTION_TYPES = ('field', 'area', 'file', 'drop_down', 'radio', 'checkbox', 'multiple', 'date', 'date_time', 'time')
EXPECTED_TYPES = {'simple': 77, 'virtual': 14, 'downloadable': 12, 'configurable': 6, 'bundle': 12, 'grouped': 6}
DISCLOSURE = 'Synthetic QA fixture. Names, prices, services and files are fictional test data. Reused imagery is illustrative; no real service, warranty or offer is provided.'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n')


def csv_rows(path):
    with Path(path).open(newline='') as f:
        return list(csv.DictReader(f))


def safe_relative(value):
    p = PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or '\\' in value or str(p) != value:
        raise ValueError('Unsafe package member: ' + value)
    return p


def verify_package(package):
    package = Path(package).resolve()
    m = json.loads((package / 'manifest.json').read_text())
    if m.get('recipe') != VERSION or m.get('schema') != 1:
        raise ValueError('Unrecognized QA package')
    expected = set(m['files']) | {'manifest.json'}
    actual = {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()}
    if actual != expected:
        raise ValueError('Package member inventory changed')
    for name, item in m['files'].items():
        safe_relative(name)
        p = package / name
        if p.is_symlink() or not p.resolve().is_relative_to(package) or p.stat().st_size != item['bytes'] or sha(p) != item['sha256']:
            raise ValueError('QA package member changed: ' + name)
    products = json.loads((package / 'fixtures.json').read_text())
    validate(products)
    counts = Counter(r['product']['product_type'] for r in products)
    if counts != m['counts']['types'] or counts != EXPECTED_TYPES or len(products) != m['counts']['products']:
        raise ValueError('QA type counts differ')
    imported = csv_rows(package / 'data/products.csv')
    canonical = [{k: v for k, v in f['product'].items() if v != ''} for f in products]
    if [{k: v for k, v in r.items() if v != ''} for r in imported] != canonical:
        raise ValueError('Import CSV differs from fixture definitions')
    for fixture in products:
        row = fixture['product']
        for column in ('base_image', 'small_image', 'thumbnail_image'):
            if row.get(column):
                name = 'media/import' + row[column]
                if name not in m['files']: raise ValueError('Missing fixture image')
        for column in ('downloadable_links', 'downloadable_samples'):
            for member in row.get(column, '').split('|'):
                if not member: continue
                values = dict(p.split('=', 1) for p in member.split(','))
                for field in ('file', 'sample'):
                    if field in values and 'media/import/' + values[field] not in m['files']:
                        raise ValueError('Missing fixture download')
    return m


def key_values(values):
    return ','.join(f'{k}={v}' for k, v in values.items())


def variations(row):
    return [dict(field.split('=', 1) for field in group.split(','))
            for group in row.get('configurable_variations', '').split('|') if group]


def load_sources(package, pin):
    package = Path(package).resolve()
    if (package / 'manifest.json').is_symlink() or sha(package / 'manifest.json') != pin:
        raise ValueError('Accepted export pin differs')
    m = json.loads((package / 'manifest.json').read_text())
    if m.get('profile') != 'expanded-measurement-free' or m.get('products') != 107688:
        raise ValueError('Accepted measurement-free expansion required')
    names = ('data/1-simple.csv', 'data/2-configurable.csv', 'data/4-media.csv')
    for name in names:
        item = m['files'][name]
        if sha(package / name) != item['sha256'] or (package / name).stat().st_size != item['bytes']:
            raise ValueError('Accepted input CSV changed: ' + name)
    simples = {r['sku']: r for r in csv_rows(package / names[0])}
    media = {r['sku']: r for r in csv_rows(package / names[2])}
    sources = [r for r in simples.values() if r['product_online'] == '1'
               and r['visibility'] == 'Catalog, Search' and r['sku'] in media]
    # A real two-axis accepted family supplies color/finish matching images;
    # size-only QA variations may share the same illustration.
    family = None
    for parent in csv_rows(package / names[1]):
        groups = variations(parent)
        if not groups or not all('color' in g and 'wands_finish' in g for g in groups):
            continue
        colors = sorted({g['color'] for g in groups}); finishes = sorted({g['wands_finish'] for g in groups})
        for c in itertools.combinations(colors, 2):
            for f in itertools.combinations(finishes, 2):
                cells = {(g['color'], g['wands_finish']): simples[g['sku']] for g in groups
                         if g['sku'] in media and simples[g['sku']]['product_online'] == '1'}
                if all(pair in cells for pair in itertools.product(c, f)):
                    family = (c, f, cells)
                    break
            if family: break
        if family: break
    if len(sources) < 12 or family is None:
        raise ValueError('Twelve physical sources and a complete color/finish source family required')
    # Use distinct product classes where possible, then fill deterministically.
    selected = []; classes = set()
    for row in sorted(sources, key=lambda r: r['sku']):
        cls = row.get('wands_product_class') or row['name']
        if cls not in classes:
            selected.append(row); classes.add(cls)
        if len(selected) == 12: break
    if len(selected) < 12:
        selected += [r for r in sorted(sources, key=lambda r: r['sku']) if r not in selected][:12-len(selected)]
    chosen = {r['sku']: r for r in selected}
    chosen.update({r['sku']: r for r in family[2].values() if r['color'] in family[0] and r['wands_finish'] in family[1]})
    assets = {}
    for sku in chosen:
        relative = 'media' + media[sku]['base_image']
        safe_relative(relative)
        item = m['files'][relative]; source = package / relative
        if source.is_symlink() or not source.resolve().is_relative_to(package) or sha(source) != item['sha256']:
            raise ValueError('Approved source image differs: ' + sku)
        if source.suffix.lower() != '.jpg': raise ValueError('Approved JPEG required')
        assets[sku] = (relative, item)
    return m, selected, family, assets


def base_product(sku, title, kind='simple', area='Core Types'):
    physical = kind == 'simple'
    return {'sku': PREFIX + sku, 'name': ('QA ' + title)[:255], 'product_type': kind,
            'attribute_set_code': 'Default', 'product_websites': 'wands', 'store_view_code': '',
            'categories': CATEGORY + '/' + area, 'url_key': 'wands-qa-' + sku.lower(),
            'description': DISCLOSURE, 'short_description': title + '. ' + DISCLOSURE,
            'product_online': '1', 'visibility': 'Catalog, Search', 'tax_class_name': 'Taxable Goods',
            'price': '100.00', 'weight': '1' if physical else '', 'qty': '100',
            'is_in_stock': '1', 'manage_stock': '1' if kind in {'simple','virtual','downloadable'} else '0',
            'use_config_manage_stock': '0', 'backorders': '0', 'use_config_backorders': '0',
            'out_of_stock_qty': '0', 'use_config_min_qty': '0',
            'min_sale_qty': '1', 'use_config_min_sale_qty': '0',
            'max_sale_qty': '10000', 'use_config_max_sale_qty': '0',
            'enable_qty_increments': '0', 'use_config_enable_qty_inc': '0',
            'qty_increments': '1', 'use_config_qty_increments': '0', 'is_qty_decimal': '0'}


def make_suite(selected, family, assets):
    fixtures = []
    def add(code, title, kind='simple', area='Core Types', source=None, expect=None, **fields):
        row = base_product(code, title, kind, area)
        if source:
            for key in ('color', 'wands_finish', 'wands_size', 'lab_spec_material', 'lab_spec_frame_material'):
                if source.get(key): row[key] = source[key]
            filename = Path(assets[source['sku']][0]).name
            row.update(base_image='/wands-qa/' + filename, small_image='/wands-qa/' + filename,
                       thumbnail_image='/wands-qa/' + filename)
            row['description'] += ' Illustration reused from ' + source['sku'] + ': ' + source['name'] + '.'
        row.update({k: str(v) for k, v in fields.items()})
        fixtures.append({'id': code.lower(), 'product': row, 'source_sku': source['sku'] if source else None,
                         'expected': expect or {'add_to_cart': 'accepted', 'shipping_required': kind == 'simple'}})
        return row
    physical = []
    for i, source in enumerate(selected):
        fields = {'product_online':0, 'visibility':'Not Visible Individually'} if i == 11 else {'qty':0,'is_in_stock':0} if i == 10 else {}
        physical.append(add(f'COMPONENT-{i+1:02}', source['name'], area='Components', source=source,
            expect={'add_to_cart': 'rejected' if i>=10 else 'accepted', 'shipping_required':True}, **fields))
    virtual = []
    services = ['Assembly Service','Design Consultation','Delivery Planning','Layout Review','Installation Advice',
                'Care Consultation','Warranty Simulation','Membership Simulation','Training Session','Free Consultation',
                'Unavailable Service','Disabled Service']
    for i,title in enumerate(services):
        fields={'tax_class_name':'None'} if i%2 else {}
        if i==9:fields['price']=0
        if i==10:fields.update(qty=0,is_in_stock=0)
        if i==11:fields.update(product_online=0,visibility='Not Visible Individually')
        virtual.append(add(f'VIRTUAL-{i+1:02}', title, 'virtual', area='Virtual Services',
            expect={'add_to_cart':'rejected' if i>=10 else 'accepted','shipping_required':False}, **fields))
    downloadable = []
    for i in range(12):
        separate = i//6; limit=(0,3)[i//3%2]; share=i%3; count=1 if i%2==0 else 2
        links=[]
        for j in range(count):
            file='room-plan.pdf' if (i+j)%2==0 else 'material-kit.zip'
            links.append(key_values({'title':f'QA Download {j+1}', 'file':'wands-qa-downloads/'+file,
                'sample':'wands-qa-downloads/sample.pdf','downloads':limit,'shareable':share,
                'price':str((j+1)*5 if separate else 0),'sort_order':j+1,
                'purchased_separately':separate,'group_title':'QA Downloads'}))
        samples=key_values({'title':'QA Preview','file':'wands-qa-downloads/sample.pdf','sort_order':1,'group_title':'QA Previews'})
        downloadable.append(add(f'DOWNLOAD-{i+1:02}', f'Room Planning Download {i+1:02}', 'downloadable', area='Downloads',
            downloadable_links='|'.join(links), downloadable_samples=samples,
            links_purchased_separately=separate, links_title='QA Downloads', samples_title='QA Previews',
            price=0 if separate else 20, tax_class_name='None' if i%2 else 'Taxable Goods',
            expect={'add_to_cart':'links_required' if separate else 'accepted','shipping_required':False,
                    'links':count,'downloads_per_link':limit,'shareable':share,
                    'download_access':'pending_runtime_order_test'}))
    for kind in OPTION_TYPES:
        for required in (0,1):
            price_type='percent' if required else 'fixed'
            common={'name': 'QA '+kind.replace('_',' '),'type':kind,'required':required,'price':10,'price_type':price_type,
                    'sku':'QAOPT'+kind.upper()+str(required)}
            if kind in {'drop_down','radio','checkbox','multiple'}:
                options='|'.join(key_values({**common,'option_title':f'Choice {j}','sku':common['sku']+str(j),'price':j*5}) for j in (1,2))
            else:
                if kind in {'field','area'}:common['max_characters']=80
                if kind=='file':common.update(file_extension='pdf,txt',image_size_x=0,image_size_y=0)
                options=key_values(common)
            add('OPTION-'+kind.upper().replace('_','-')+f'-{required}',
                kind.replace('_',' ').title()+' Customization '+('Required' if required else 'Optional'),
                area='Custom Options',source=selected[0],custom_options=options,price=200,
                expect={'option_type':kind,'required':bool(required),'price_type':price_type,
                        'base_price':200,'first_option_price_delta':(10 if required else 5) if kind in {'drop_down','radio','checkbox','multiple'} else (20 if required else 10),
                        'missing_option':'rejected' if required else 'accepted','shipping_required':True})
    colors,finishes,cells=family
    config_specs=[('FULL-THREE',list(itertools.product(colors,('Small','Large'),finishes))),
                  ('SPARSE-THREE',list(itertools.product(colors,('Small','Large'),finishes))[:5]),
                  ('OUT-OF-STOCK',list(itertools.product(colors,('Small',),finishes))),
                  ('DISABLED-CHILD',list(itertools.product(colors,('Small',),finishes))),
                  ('VIRTUAL',[(c,'Small',finishes[0]) for c in colors]),
                  ('PRICE-IMAGE',list(itertools.product(colors,('Small',),finishes)))]
    for code, combinations in config_specs:
        groups=[]
        axes=('color',) if code=='VIRTUAL' else ('color','wands_finish') if code not in {'FULL-THREE','SPARSE-THREE'} else ('color','wands_size','wands_finish')
        for i,(color,size,finish) in enumerate(combinations):
            kind='virtual' if code=='VIRTUAL' else 'simple'
            fields={'visibility':'Not Visible Individually','categories':'','color':color,'wands_size':size,'wands_finish':finish,'price':100+i*10}
            unavailable=code=='OUT-OF-STOCK' and i==0; disabled=code=='DISABLED-CHILD' and i==0
            if unavailable:fields.update(qty=0,is_in_stock=0)
            if disabled:fields['product_online']=0
            child=add('CHILD-'+code+f'-{i+1:02}',code.title()+' Variant '+str(i+1),kind,area='Configurable',
                source=cells[(color,finish)] if kind=='simple' else None,
                expect={'add_to_cart':'rejected' if unavailable or disabled else 'accepted','shipping_required':kind=='simple'},**fields)
            groups.append({'sku':child['sku'],**{axis:child[axis] for axis in axes}})
        add('CONFIG-'+code,code.title()+' Configurable','configurable',area='Configurable',
            source=cells[(colors[0],finishes[0])] if code!='VIRTUAL' else None, configurable_variations='|'.join(key_values(g) for g in groups),
            configurable_variation_labels=','.join(axis+'='+{'color':'Color','wands_size':'Size','wands_finish':'Finish'}[axis] for axis in axes),
            expect={'axes':list(axes),'children':len(groups),'missing_selection':'rejected',
                    'shipping_required':code!='VIRTUAL','sparse_combinations':code=='SPARSE-THREE'})
    for i in range(12):
        fixed=i%2==0; control=('select','radio','checkbox','multi')[i//2] if i<8 else 'select'
        csv_control={'select':'dropdown','radio':'radio','checkbox':'checkbox','multi':'multiselect'}[control]
        children=physical[:4] if i<8 else physical[:2]+virtual[:2] if i<10 else virtual[:4]
        selections=[]
        for option in range(2):
            for j in range(2):
                selections.append(key_values({'name':f'QA Option {option+1}','type':csv_control,
                    'required':1 if option==0 else 0,'sku':children[option*2+j]['sku'],
                    'price':5*(j+1) if fixed else 0,'price_type':'fixed' if j==0 else 'percent',
                    'default':1 if j==0 else 0,'default_qty':1,'can_change_qty':1 if i%2 and control in {'select','radio'} else 0}))
        add(f'BUNDLE-{i+1:02}',f'{"Fixed" if fixed else "Dynamic"} {control.title()} '+('Service' if i>=10 else 'Mixed' if i>=8 else 'Physical')+' Bundle',
            'bundle',area='Bundles',source=selected[0] if i<10 else None,
            bundle_values='|'.join(selections),bundle_price_type='fixed' if fixed else 'dynamic',
            bundle_sku_type='fixed' if fixed else 'dynamic',bundle_weight_type='fixed' if fixed and i<10 else 'dynamic',
            bundle_shipment_type='separately' if i%2 and i<8 else 'together',bundle_price_view='As low as',
            weight=4 if fixed and i<10 else '',price=100 if fixed else '',
            expect={'control':control,'price_type':'fixed' if fixed else 'dynamic','optional_option':True,
                    'customer_qty':bool(i%2 and control in {'select','radio'}),'shipping_required':i<10,'missing_required_selection':'rejected'})
    grouped=[physical[:3],physical[:2]+virtual[:1],virtual[:3],physical[:2]+physical[10:11],physical[:2]+physical[11:12],
             list(reversed(physical[:2]))+downloadable[:1]]
    for i,children in enumerate(grouped):
        add(f'GROUPED-{i+1:02}',f'Associated Collection {i+1:02}','grouped',area='Grouped',
            source=selected[0] if i!=2 else None,associated_skus=','.join(child['sku']+'='+str(j if i%2 else 0) for j,child in enumerate(children,1)),
            expect={'associated_skus':[child['sku'] for child in children],'independent_line_prices':True,
                    'zero_quantities':'rejected','shipping_required':i!=2,'unavailable_association':i in {3,4}})
    pricing=[('FREE',{'price':0}),('SPECIAL-ACTIVE',{'special_price':75,'special_from_date':'2000-01-01','special_to_date':'2099-12-31'}),
        ('SPECIAL-EXPIRED',{'special_price':75,'special_from_date':'2000-01-01','special_to_date':'2001-01-01'}),
        ('SPECIAL-FUTURE',{'special_price':75,'special_from_date':'2098-01-01','special_to_date':'2099-01-01'}),
        ('TIER-ALL',{'_tier_price_website':'wands','_tier_price_customer_group':'all','_tier_price_qty':5,'_tier_price_price':70}),
        ('GROUP-GUEST',{'_tier_price_website':'wands','_tier_price_customer_group':0,'_tier_price_qty':1,'_tier_price_price':80}),
        ('NO-TAX',{'tax_class_name':'None'}),('TAXABLE',{'tax_class_name':'Taxable Goods'})]
    price_rows=[]
    for code,fields in pricing:
        price_rows.append(add('PRICE-'+code,code.title()+' Pricing',area='Pricing',source=selected[1],
            expect={'price_case':code.lower(),'reference_date':'2026-10-06','actual_tax':'requires_store_rules',
                    'price_before_tax':0 if code=='FREE' else 75 if code=='SPECIAL-ACTIVE' else 80 if code=='GROUP-GUEST' else 100,
                    'customer_group_id':0,'quantity':1,
                    **({'quantity_five_price_per_unit':70} if code=='TIER-ALL' else {})},**fields))
    price_rows[-1].update(related_skus=physical[0]['sku'],crosssell_skus=physical[1]['sku'],upsell_skus=physical[2]['sku'])
    inventory=[('OUT',{'qty':0,'is_in_stock':0}),('BACKORDER',{'qty':0,'is_in_stock':1,'backorders':1}),
        ('BACKORDER-NOTIFY',{'qty':0,'is_in_stock':1,'backorders':2}),('MINIMUM',{'min_sale_qty':3}),
        ('MAXIMUM',{'max_sale_qty':5}),('INCREMENTS',{'enable_qty_increments':1,'qty_increments':2}),
        ('DECIMAL',{'is_qty_decimal':1,'min_sale_qty':'.5','enable_qty_increments':1,'qty_increments':'.5'}),
        ('UNMANAGED',{'manage_stock':0,'qty':0})]
    for code,fields in inventory:
        add('STOCK-'+code,code.title()+' Inventory',area='Inventory',source=selected[2],
            expect={'inventory_case':code.lower(),'quantity_constraints':fields,'msi_behavior':'requires_runtime_verification'},**fields)
    for i,visibility in enumerate(('Not Visible Individually','Catalog','Search','Catalog, Search')):
        add(f'VISIBILITY-{i+1:02}',visibility+' Visibility',area='Visibility',source=selected[3],visibility=visibility,
            expect={'visibility':visibility,'direct_url':i!=0,'catalog_listing':i in {1,3},'search_listing':i in {2,3}})
    return fixtures


def validate(fixtures):
    rows={f['product']['sku']:f['product'] for f in fixtures}
    if len(rows)!=len(fixtures):raise ValueError('Duplicate QA SKU')
    urls=set()
    for f in fixtures:
        r=f['product'];sku=r['sku']
        if not sku.startswith(PREFIX) or r['product_type'] not in TYPES or r['product_websites']!='wands':
            raise ValueError('Fixture outside QA scope')
        if r['url_key'] in urls:raise ValueError('Duplicate QA URL')
        urls.add(r['url_key'])
        if r['product_type'] in {'virtual','downloadable','grouped','configurable'} and r['weight']:
            raise ValueError('Nonphysical/parent fixture has physical weight')
        if r['product_type']=='configurable':
            groups=variations(r);axes=[k for k in groups[0] if k!='sku'];seen=set()
            for g in groups:
                child=rows.get(g['sku'])
                if child is None or child['product_type'] not in {'simple','virtual'}:raise ValueError('Invalid configurable child')
                if set(g)!=set(axes)|{'sku'} or any(child[k]!=g[k] for k in axes):raise ValueError('Child options differ')
                combination=tuple(g[k] for k in axes)
                if combination in seen:raise ValueError('Duplicate configurable option combination')
                seen.add(combination)
        if r['product_type']=='grouped':
            for pair in r['associated_skus'].split(','):
                child=rows.get(pair.split('=')[0])
                if child is None or child['product_type'] not in {'simple','virtual','downloadable'}:raise ValueError('Invalid grouped dependency')
        if r['product_type']=='bundle':
            for selection in r['bundle_values'].split('|'):
                value=dict(p.split('=',1) for p in selection.split(','));child=rows.get(value['sku'])
                if child is None or child['product_type'] not in {'simple','virtual'}:raise ValueError('Invalid bundle dependency')
        for column in ('related_skus','crosssell_skus','upsell_skus'):
            if any(s not in rows for s in r.get(column,'').split(',') if s):raise ValueError('External merchandising dependency')
        for key in ('downloadable_links','downloadable_samples'):
            for member in r.get(key,'').split('|'):
                if not member:continue
                values=dict(p.split('=',1) for p in member.split(','))
                if any(k in values for k in ('url','link_url','sample_url')):raise ValueError('Remote download not permitted')
                for field in ('file','sample'):
                    if field in values and not str(safe_relative(values[field])).startswith('wands-qa-downloads/'):
                        raise ValueError('Download outside fixture assets')


def pdf_bytes(title):
    # Minimal deterministic one-page PDF with a valid xref table; no third-party assets.
    text=f'BT /F1 16 Tf 50 740 Td ({title}) Tj 0 -30 Td (Synthetic QA file. No real service or product offer.) Tj ET'.encode('ascii')
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
             b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
             b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(text)).encode()+b' >>\nstream\n'+text+b'\nendstream']
    result=bytearray(b'%PDF-1.4\n');offsets=[]
    for i,obj in enumerate(objects,1):offsets.append(len(result));result.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref=len(result);result.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
    for off in offsets:result.extend(f'{off:010} 00000 n \n'.encode())
    result.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(result)


def zip_bytes():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as z:
        for name,body in [('README.txt',b'Synthetic QA material kit. No real product measurements or warranties.\n'),
                          ('materials.json',b'{"synthetic":true,"materials":["wood","fabric"]}\n')]:
            info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.external_attr=0o100644<<16;z.writestr(info,body)
    return stream.getvalue()


def build(source, pin, output):
    source=Path(source).resolve();output=Path(output).resolve()
    if output.exists() or output.is_relative_to(source) or source.is_relative_to(output):raise ValueError('Fresh independent output required')
    _,selected,family,assets=load_sources(source,pin)
    fixtures=make_suite(selected,family,assets);validate(fixtures)
    counts=Counter(f['product']['product_type'] for f in fixtures)
    if dict(counts)!=EXPECTED_TYPES:raise ValueError('Unexpected recipe type counts: '+str(dict(counts)))
    output.mkdir(parents=True);(output/'data').mkdir();media=output/'media/import/wands-qa';media.mkdir(parents=True)
    downloads=output/'media/import/wands-qa-downloads';downloads.mkdir(parents=True)
    (downloads/'room-plan.pdf').write_bytes(pdf_bytes('QA Room Planning Guide'))
    (downloads/'sample.pdf').write_bytes(pdf_bytes('QA Download Preview'))
    (downloads/'material-kit.zip').write_bytes(zip_bytes())
    lineage={}
    for f in fixtures:
        sku=f['source_sku']
        if not sku:continue
        relative,item=assets[sku];target=media/Path(relative).name
        if not target.exists():shutil.copyfile(source/relative,target)
        lineage[f['product']['sku']]={'source_sku':sku,'source_file':relative,'sha256':item['sha256'],
                                    'acceptance':'reused exact approved expansion JPEG; no new generation'}
    rows=[f['product'] for f in fixtures]
    # All rows are validated together so new dependencies are known to native validation.
    columns=['sku']+sorted(set().union(*(set(r) for r in rows))-{'sku'})
    with (output/'data/products.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns,lineterminator='\n');w.writeheader();w.writerows(rows)
    write_json(output/'fixtures.json',fixtures);write_json(output/'media-lineage.json',lineage)
    matrix={'schema':1,'recipe':VERSION,'cases':[{'sku':f['product']['sku'],'case':f['id'],**f['expected']} for f in fixtures],
            'cart_scenarios':[{'id':'physical-only','skus':[PREFIX+'COMPONENT-01'],'expected_shipping':True},
                              {'id':'virtual-only','skus':[PREFIX+'VIRTUAL-01'],'expected_shipping':False},
                              {'id':'download-only','skus':[PREFIX+'DOWNLOAD-01'],'expected_shipping':False},
                              {'id':'mixed-cart','skus':[PREFIX+'COMPONENT-01',PREFIX+'VIRTUAL-01',PREFIX+'DOWNLOAD-01'],'expected_shipping':True}],
            'pending_store_scenarios':['post-order download permissions and limits','checkout and payment','multi-source inventory configuration',
                                       'additional website/store/currency scope','tax and catalog/cart price rules','extension-specific types']}
    write_json(output/'test-matrix.json',matrix)
    proposal={'schema':1,'state':'prepared; not installed','recipe':VERSION,'products_to_create':len(fixtures),'types':dict(counts),
              'sku_prefix':PREFIX,'website':'wands','category_root':CATEGORY,'existing_products_to_update':0,'products_to_delete':0,
              'customers_orders_quotes_reservations_to_create':0,'global_configuration_changes':0,
              'targets':['/Users/matt/code/mageos-latest','/opt/comtom/stores/relevance/src'],
              'apply_requirements':['verified native validation','fresh destination collision/dependency preflight',
                  'private destination backup and fixture-scoped inverse','exact installation approval','runtime and browser acceptance'],
              'inverse_plan':{'products':'remove only newly created fixture IDs after checking no external links or transactions reference them',
                 'categories':'remove only new empty QA categories recorded in destination journal','media':'retain files referenced elsewhere',
                 'protected_data':'preserve existing product IDs, stock, relationships, settings and customer/order/cart data'}}
    write_json(output/'installation-proposal.json',proposal)
    files={p.relative_to(output).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(output.rglob('*')) if p.is_file()}
    manifest={'schema':1,'recipe':VERSION,'source_export_sha256':pin,'state':'prepared; not installed',
              'counts':{'products':len(fixtures),'types':dict(counts),'download_files':3,'image_files':len(list(media.iterdir()))},
              'files':files,'source_files':{Path(__file__).name:sha(__file__)}}
    write_json(output/'manifest.json',manifest);verify_package(output)
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path);p.add_argument('--source-sha256')
    p.add_argument('--output',type=Path);p.add_argument('--verify',type=Path);a=p.parse_args()
    if a.verify:r=verify_package(a.verify)
    else:
        if not a.source or not a.source_sha256 or not a.output:p.error('--source, --source-sha256 and --output required')
        r=build(a.source,a.source_sha256,a.output)
    print(json.dumps({'state':r['state'],'counts':r['counts']},indent=2))

if __name__=='__main__':main()
