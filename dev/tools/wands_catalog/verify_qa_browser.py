"""Render QA product pages and controls on the two existing stores without cart submissions."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import time

from build_qa_catalog import verify_package, variations, sha
from verify_expansion_browser import select_configurable


def check_store(target, package, output, proxy_port=None):
    manifest = verify_package(package)
    fixtures = json.loads((package / 'fixtures.json').read_text())
    flags = ['--session', 'wands-qa-' + target, '--json']
    base = 'http://relevance.comtom.lab:8080/' if target == 'studio' else 'https://relevance.comtom.lab/'
    # Both existing stores expose their hostname through their existing ingress.
    # Per-session resolution avoids changing DNS or host configuration.
    if target == 'studio':
        flags += ['--args', '--host-resolver-rules=MAP relevance.comtom.lab 127.0.0.1']
    elif proxy_port:
        if not 1 <= proxy_port <= 65535: raise ValueError('Invalid local proxy port')
        flags += ['--proxy', 'socks5://127.0.0.1:' + str(proxy_port), '--ignore-https-errors']
    else:
        flags += ['--args', '--host-resolver-rules=MAP relevance.comtom.lab 37.27.126.105', '--ignore-https-errors']
    output.mkdir(parents=True, exist_ok=True)
    results = []; screenshots = []; excluded = []
    def command(*args):
        result = subprocess.run(['agent-browser', *flags, *args], capture_output=True, text=True, timeout=60)
        if result.returncode: raise RuntimeError(target + ' browser command failed: ' + args[0] + ' ' + (result.stderr or result.stdout)[:600])
        response = json.loads(result.stdout)
        if not response.get('success'): raise RuntimeError('Browser command unsuccessful')
        return response['data']
    def evaluate(js): return command('eval', js)['result']
    def batch(commands):
        result = subprocess.run(['agent-browser', *flags, 'batch', '--bail'], input=json.dumps(commands), capture_output=True, text=True, timeout=90)
        responses = json.loads(result.stdout)
        if result.returncode or any(not x.get('success') for x in responses): raise RuntimeError(target + ' browser batch failed: ' + (result.stderr or result.stdout)[:900])
        return [x['result'] for x in responses]
    try:
        try: command('close')
        except RuntimeError: pass
        # The named daemon releases its socket asynchronously after close.
        time.sleep(1)
        command('open', base); command('set', 'viewport', '1920', '1080')
        for fixture in fixtures:
            row = fixture['product']
            sku = row['sku']
            if row['product_online'] != '1' or row['visibility'] == 'Not Visible Individually':
                hidden = batch([['open', base + row['url_key'] + '.html'], ['eval', '({name:document.querySelector("h1")?.textContent.trim(),form:!!document.querySelector("#product_addtocart_form")})']])[-1]['result']
                if hidden['form'] or hidden['name'] == row['name']: raise ValueError('Hidden or disabled product exposed: ' + sku)
                excluded.append({'sku': sku, 'passed': True, **hidden})
                continue
            (output / 'progress.json').write_text(json.dumps({'sku': sku, 'completed': len(results), 'updated': time.time()}))
            data = batch([['open', base + row['url_key'] + '.html'], ['eval', '''({name:document.querySelector('h1')?.textContent.trim(),
              form:!!document.querySelector('#product_addtocart_form'),
              controls:Array.from(document.querySelector('#product_addtocart_form')?.elements || []).map(e=>({name:e.name,type:e.type,required:e.required})),
              body:document.querySelector('main')?.innerText})''']])[-1]['result']
            if data['name'] != row['name']: raise ValueError('Rendered identity differs: ' + sku)
            unavailable = row.get('is_in_stock') == '0' and row.get('manage_stock') == '1'
            if not data['form'] and not unavailable: raise ValueError('Rendered product form missing: ' + sku)
            if unavailable and 'out of stock' not in (data.get('body') or '').lower(): raise ValueError('Unavailable message missing: ' + sku)
            names = [c['name'] for c in data['controls']]
            if row['product_type'] == 'configurable':
                groups = variations(row)
                if sku in {'WANDS-QA-CONFIG-OUT-OF-STOCK', 'WANDS-QA-CONFIG-DISABLED-CHILD'}: groups = groups[1:]
                labels = list(next(iter(groups)).values())[1:]
                selected = select_configurable(evaluate, command, labels)
                if sorted(selected) != sorted(labels): raise ValueError('Configurable selection differs: ' + sku)
                data['selected_labels'] = selected
            if row['product_type'] == 'downloadable':
                choices = [n for n in names if n == 'links[]']
                if bool(choices) != bool(int(row['links_purchased_separately'])): raise ValueError('Download selector differs: ' + sku)
            if row['product_type'] == 'grouped' and not any(n.startswith('super_group[') for n in names): raise ValueError('Grouped controls missing')
            if row['product_type'] == 'bundle' and not any(n.startswith('bundle_option[') for n in names): raise ValueError('Bundle controls missing')
            if 'custom_options' in row and not any(n.startswith('options[') or n.startswith('options_') for n in names): raise ValueError('Custom option control missing')
            if row.get('base_image'):
                stem = Path(row['base_image']).stem
                command('wait', '--fn', 'Array.from(document.images).some(i=>i.naturalWidth>0&&i.src.includes(' + json.dumps(stem) + '))')
                data['image_loaded'] = True
            data.pop('body', None)
            results.append({'sku': sku, 'type': row['product_type'], **data})
            if sku in {'WANDS-QA-DOWNLOAD-07', 'WANDS-QA-CONFIG-FULL-THREE', 'WANDS-QA-GROUPED-06'}:
                screenshot = (output / (sku.lower() + '.png')).resolve()
                command('screenshot', str(screenshot), '--full'); screenshots.append(str(screenshot))
        (output / 'product-pages.json').write_text(json.dumps({'passed': True, 'target': target, 'verified_at': datetime.now(timezone.utc).isoformat(), 'manifest_sha256': sha(package / 'manifest.json'), 'products_checked': len(results), 'excluded_products_checked': len(excluded), 'excluded_checks': excluded, 'checks': results, 'screenshots': screenshots, 'scope': 'product pages only; category acceptance follows'}, indent=2) + '\n')
        category = evaluate('Array.from(document.querySelectorAll("header a")).find(a=>a.textContent.trim()==="QA Fixtures")?.href')
        if not category: raise ValueError('QA category navigation missing')
        command('open', category)
        command('wait', '--fn', 'document.querySelectorAll(".product-item,.item.product").length>0')
        category_result = evaluate('({url:location.href,heading:document.querySelector("h1")?.textContent.trim(),products:document.querySelectorAll(".product-item,.item.product").length})')
        report = {'passed': True, 'target': target, 'verified_at': datetime.now(timezone.utc).isoformat(), 'manifest_sha256': sha(package / 'manifest.json'),
                  'products_checked': len(results), 'excluded_products_checked': len(excluded), 'excluded_checks': excluded, 'checks': results, 'category': category_result,
                  'screenshots': screenshots, 'cart_submissions': 0, 'viewport': [1920, 1080], 'local_proxy_port': proxy_port,
                  'private_ca_bypass': target == 'comtom', 'scope': 'rendered identity, controls, image loading, configurable selections and QA category'}
        (output / 'acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
        return report
    finally:
        command('close')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=('studio', 'comtom'), required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--proxy-port', type=int, help='Existing localhost SOCKS proxy for Comtom; does not start a tunnel')
    args = parser.parse_args()
    result = check_store(args.target, args.package, args.output, args.proxy_port)
    print(json.dumps({'passed': result['passed'], 'products_checked': result['products_checked']}))
