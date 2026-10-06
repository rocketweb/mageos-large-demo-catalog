"""Rendered acceptance of the two existing WANDS storefronts, without cart writes."""
import json
import re
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import urlsplit, urlencode
from finish_expansion_project import LOCAL, REMOTE, SSH, private_json

DEPARTMENTS={'Furniture','Bed & Bath','Kitchen & Tabletop','Décor & Pillows','Lighting','Rugs',
             'Outdoor','Storage & Organization','Home Improvement','Baby & Kids','Pet'}


def select_configurable(evaluate, command, labels):
    controls_js='''Array.from(document.querySelectorAll('select[name^=super_attribute],input[type=radio][name^=super_attribute]')).flatMap(e=>e.tagName==='SELECT'?Array.from(e.options).filter(o=>o.value).map(o=>({name:e.name,kind:'select',id:e.id,value:o.value,label:o.dataset.optionLabel||o.textContent.trim(),disabled:e.disabled||o.disabled})):[{name:e.name,kind:'radio',id:e.id,value:e.value,label:e.dataset.optionLabel||e.getAttribute('aria-label')||e.closest('label')?.textContent.trim(),disabled:e.disabled}])'''
    groups=list(dict.fromkeys(c['name'] for c in evaluate(controls_js)))
    used=[]
    for group in groups:
        # Earlier selections can change which choices are enabled.
        choice=next((c for c in evaluate(controls_js) if c['name']==group
                     and c['label'] in labels and c['label'] not in used and not c['disabled']),None)
        if not choice or not re.fullmatch(r'[A-Za-z0-9_-]+',choice['id']):
            raise ValueError('Required variant option unavailable')
        if choice['kind']=='radio':command('check','#'+choice['id'])
        else:command('select','#'+choice['id'],choice['value'])
        used.append(choice['label'])
    return evaluate('''Array.from(document.querySelectorAll('select[name^=super_attribute],input[type=radio][name^=super_attribute]:checked')).flatMap(e=>e.tagName==='SELECT'?Array.from(e.selectedOptions).filter(o=>o.value).map(o=>o.dataset.optionLabel||o.textContent.trim()):[e.dataset.optionLabel||e.getAttribute('aria-label')||e.closest('label')?.textContent.trim()])''')


def open_existing_tunnel(port):
    # A multiplexed SSH forward exits successfully after adding the listener
    # to its existing master. It is not a persistent child process to poll.
    ready=subprocess.run([*SSH,'comtom','true'],capture_output=True,timeout=30)
    forward=[*SSH,'-O','forward','-D','127.0.0.1:'+str(port),'comtom']
    if ready.returncode or subprocess.run(forward,capture_output=True,timeout=30).returncode:
        raise RuntimeError('Existing Comtom browser forward failed')
    cancel=[*SSH,'-O','cancel','-D','127.0.0.1:'+str(port),'comtom']
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=2):pass
    except OSError:
        subprocess.run(cancel,capture_output=True,timeout=15)
        raise RuntimeError('Existing Comtom browser listener unavailable')
    return cancel


def browser_acceptance(root, cases, output, *, full=True):
    if root not in (LOCAL,REMOTE):raise ValueError('Only the existing stores may be tested')
    name='local' if root==LOCAL else 'comtom';session='wands-completion-'+name
    base='http://relevance.comtom.lab:8080/' if root==LOCAL else 'https://relevance.comtom.lab/'
    flags=['--session',session,'--json'];proxy=None;results=[]
    if root==LOCAL:flags+=['--args','--host-resolver-rules=MAP relevance.comtom.lab 127.0.0.1']
    else:
        with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        proxy=open_existing_tunnel(port)
        flags+=['--proxy','socks5://127.0.0.1:'+str(port),'--ignore-https-errors']
    def command(*args):
        p=subprocess.run(['agent-browser',*flags,*args],capture_output=True,text=True,timeout=60)
        if p.returncode:raise RuntimeError(name+' rendered check failed: '+args[0])
        value=json.loads(p.stdout)
        if not value.get('success'):raise RuntimeError(name+' browser command did not succeed')
        return value['data']
    def evaluate(js):return command('eval',js)['result']
    def navigate(path):
        if not path.startswith('/') or path.startswith('//'):raise ValueError('Unexpected storefront path')
        command('open',base.rstrip('/')+path)
        command('wait','--load','domcontentloaded')
    def progress(kind, identity):
        private_json(output/(name+'-browser-progress.json'),{'target':name,'phase':kind,
            'current':identity,'checks_completed':len(results),'updated':time.time()})
    try:
        # Only this named test session is closed or reused.
        try:command('close')
        except (RuntimeError,subprocess.TimeoutExpired):pass
        command('open',base);command('set','viewport','1920','1080')
        menu=evaluate('Array.from(document.querySelectorAll("header a")).map(a=>({text:a.textContent.trim(),path:new URL(a.href).pathname})).filter(a=>a.text)')
        categories={d:next((a['path'] for a in menu if a['text']==d or a['text']=='See all '+d),None) for d in DEPARTMENTS}
        if full and not all(categories.values()):raise ValueError('Missing rendered department navigation')
        if full:
            for department,path in sorted(categories.items()):
                progress('category',department)
                navigate(path)
                command('wait','--fn','document.querySelectorAll(".product-item, .item.product").length > 0')
                data=evaluate('({heading:document.querySelector("h1")?.textContent.trim(),products:document.querySelectorAll(".product-item, .item.product").length})')
                if not data['products']:raise ValueError('Rendered category is empty')
                results.append({'kind':'category','department':department,'path':path,**data})
        for case in cases:
            progress('product',case['sku'])
            navigate(urlsplit(case['url']).path)
            expected=Path(case['image']).name
            command('wait','--fn','Array.from(document.images).some(i=>i.naturalWidth>0 && i.src.includes('+json.dumps(expected)+'))')
            data=evaluate('({name:document.querySelector("h1")?.textContent.trim(),image_loaded:Array.from(document.images).some(i=>i.naturalWidth>0 && i.src.includes('+json.dumps(expected)+')),form:!!document.querySelector("#product_addtocart_form"),options:Array.from(document.querySelectorAll("select[name^=super_attribute]")).map(e=>({id:e.id,labels:Array.from(e.options).map(o=>o.dataset.optionLabel||o.textContent.trim())}))})')
            if data['name']!=case['name'] or not data['image_loaded'] or not data['form']:raise ValueError('Rendered product identity, photo or cart form mismatch')
            if case['type']=='configurable':
                labels=list(case['options'].values())
                selected=select_configurable(evaluate,command,labels)
                if sorted(selected)!=sorted(labels):raise ValueError('Rendered configurable selections incomplete')
                command('wait','--fn','document.querySelector("#product_addtocart_form").checkValidity()')
                data['selected_labels']=selected
            results.append({'kind':'product','sku':case['sku'],'path':urlsplit(case['url']).path,**data})
        screenshot=output/(name+'-rendered-product.png');command('screenshot',str(screenshot),'--full')
        if full:
            for term in ('monitor riser','pet bed'):
                progress('search',term)
                navigate('/catalogsearch/result/?'+urlencode({'q':term}))
                # navigate accepts the whole local path, including its query.
                command('wait','--fn','document.querySelectorAll(".product-item, .item.product").length > 0')
                count=evaluate('document.querySelectorAll(".product-item, .item.product").length')
                if not count:raise ValueError('Rendered search has no results')
                results.append({'kind':'search','term':term,'products':count})
            search_screenshot=output/(name+'-rendered-search.png');command('screenshot',str(search_screenshot),'--full')
        receipt={'passed':True,'target':name,'checks':results,'viewport':[1920,1080],'screenshot':str(screenshot),
            'cart_submissions':0,'scope':'Rendered categories, image loading, product identity, configurable controls and search; backend unsaved-cart acceptance is separate.',
            'private_comtom_certificate_bypass':root==REMOTE,'full_catalog_acceptance':full}
        if full:receipt['search_screenshot']=str(search_screenshot)
        private_json(output/(name+'-browser-acceptance.json'),receipt);return receipt
    finally:
        try:command('close')
        finally:
            if proxy:subprocess.run(proxy,capture_output=True,timeout=15)
