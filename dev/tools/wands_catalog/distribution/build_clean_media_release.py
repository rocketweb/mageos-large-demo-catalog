"""Package approved media and exact catalog cleanup as a new immutable release."""
import argparse
from collections import Counter
import csv
from itertools import zip_longest
import json
import logging
from pathlib import Path
import re
import sys

from build_media_release import (build as build_media, check_references, encoded,
                                extract_subset, media_archives)
from build_expanded_release import product_inventory
from release import digest, verify_release, write_archive

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import catalog_exclusions as cleanup


def validated_projection(projection, config, data):
    """Hashes alone cannot authorize arbitrary changes to a product row."""
    if digest(Path(projection['exclusions'])) != projection['exclusions_sha256']:
        raise ValueError('Approved exclusion policy changed')
    if digest(Path(config['text_policy'])) != projection['text_policy_sha256']:
        raise ValueError('Approved text policy changed')
    excluded = {x['sku'] for x in json.loads(Path(projection['exclusions']).read_text())['products']}
    rules = json.loads(Path(config['text_policy']).read_text())['replacements']
    result = {}
    for name, change in projection['changes'].items():
        before, after = data['data/' + name], Path(projection['data']) / name
        if digest(before) != change['source_sha256'] or digest(after) != change['output_sha256']:
            raise ValueError('Approved catalog input checksum changed: ' + name)
        with before.open(newline='') as a, after.open(newline='') as b:
            old, new = csv.DictReader(a), csv.DictReader(b)
            if old.fieldnames != new.fieldnames:
                raise ValueError('Catalog schema changed')
            for row in old:
                if row['sku'] in excluded:
                    continue
                expected = dict(row)
                for field in cleanup.LIST_FIELDS:
                    if expected.get(field):
                        expected[field] = ','.join(x for x in expected[field].split(',') if x.strip() not in excluded)
                if expected.get('bundle_values') and set(re.findall(r'WANDS-[A-Z0-9-]+', expected['bundle_values'])) & excluded:
                    expected['bundle_values'], _ = cleanup.prune_bundle(expected['bundle_values'], excluded)
                expected = {k: cleanup.rename_text(v or '', rules) for k, v in expected.items()}
                if next(new, None) != expected:
                    raise ValueError('Catalog differs from exact approved changes: ' + row['sku'])
            if next(new, None) is not None:
                raise ValueError('Extra unapproved product row')
        result['data/' + name] = after
    return result


def clean_json(value, excluded, rules):
    if isinstance(value, dict):
        return {k: clean_json(v, excluded, rules) for k, v in value.items() if k not in excluded}
    if isinstance(value, list):
        return [clean_json(v, excluded, rules) for v in value if not isinstance(v, str) or v not in excluded]
    return cleanup.rename_text(value, rules) if isinstance(value, str) else value


def resume_base(output, selection, tag):
    inventory=json.loads((output/'assets/release-inventory.json').read_text())
    if inventory['tag']!=tag or inventory['image_selection']['selection_verification_sha256']!=digest(selection/'verification.json'):
        raise ValueError('Existing base candidate belongs to a different release or selection')
    if inventory['counts']['products']!=107815:
        raise ValueError('Only the fully verified baseline candidate can be resumed')
    for profile in ('full','toolkit'):
        for asset in (output/'assets').glob(profile+'-*'):
            target=output/profile/asset.name.removeprefix(profile+'-')
            if not target.exists():target.hardlink_to(asset)
        verify_release(output/profile,inventory['profile_pins'][profile])
    return inventory


def build(base, selection, output, tag, job):
    output, selection, job = Path(output).resolve(), Path(selection).resolve(), Path(job).resolve()
    projection = json.loads((job / 'local-catalog.json').read_text())
    config = json.loads((job / 'catalog-exclusions.json').read_text())
    if projection['selection_verification_sha256'] != digest(selection / 'verification.json'):
        raise ValueError('Clean catalog belongs to a different image selection')
    inventory = build_media(base, selection, output, tag) if not output.exists() else resume_base(output, selection, tag)
    full, toolkit, assets = output / 'full', output / 'toolkit', output / 'assets'
    old_manifest = json.loads((full / 'manifest.json').read_text())
    data = extract_subset(full, old_manifest, output / 'clean-inputs-r2', lambda n: n.startswith(('data/', 'docs/')))
    data.update(validated_projection(projection, config, data))
    excluded = {x['sku'] for x in json.loads(Path(projection['exclusions']).read_text())['products']}
    rules = json.loads(Path(config['text_policy']).read_text())['replacements']
    referenced = set()
    for name in ['data/4-media.csv', 'data/6-qa.csv']:
        with data[name].open() as stream:
            for row in csv.DictReader(stream):
                referenced.update('media/' + row[k].lstrip('/') for k in ('base_image', 'small_image', 'thumbnail', 'thumbnail_image') if row.get(k))
    images = {name: selection / 'selected-media' / name.removeprefix('media/') if name.startswith('media/wands-expanded/')
              else output / 'build-inputs/qa' / name for name in referenced}
    images.update({name: output / 'build-inputs/qa' / name for artifact in old_manifest['artifacts']
                   for name in artifact['files'] if name.startswith('media/wands-qa-downloads/')})
    for path in images.values():
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing retained catalog media')
    def save(name, value):
        path = output / 'clean-updated' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else encoded(value))
        data[name] = path
    for name, path in list(data.items()):
        if not name.endswith('.json') or not name.startswith('data/'):
            continue
        value = clean_json(json.loads(path.read_text()), excluded, rules)
        if name == 'data/media-inventory.json':
            value = {k: v for k, v in value.items() if k in images}
        save(name, value)
    counts = dict(old_manifest['counts'])
    counts.update(product_inventory([data['data/' + n + '.csv'] for n in ('1-simple', '2-configurable', '3-bundle', '6-qa')]))
    counts.update(check_references(data, images))
    with data['data/background-selection.csv'].open() as stream:
        reader = csv.DictReader(stream);fields = reader.fieldnames
        rows = [r for r in reader if 'media/wands-expanded/' + r['selected_file'] in referenced]
    path = output / 'clean-updated/data/background-selection.csv'
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields);writer.writeheader();writer.writerows(rows)
    data['data/background-selection.csv'] = path
    actions = dict(Counter(r['action'] for r in rows))
    jpeg_names = [n for n in images if n.endswith('.jpg')]
    counts.update(image_files=len(jpeg_names), distinct_image_hashes=len({digest(images[n]) for n in jpeg_names}),
                  white_background_selections=sum(v for k, v in actions.items() if k != 'original'),
                  original_background_selections=actions.get('original', 0), excluded_products=len(excluded))
    if counts['products'] != projection['counts']['products'] or counts['media_assignments'] != projection['counts']['media_assignments']:
        raise ValueError('Clean catalog product/media coverage changed')
    summary = {**inventory['image_selection'], 'source_images': len(rows), 'counts': actions,
               'excluded_products': len(excluded), 'text_replacements': projection['text_replacements'],
               'catalog_exclusions_sha256': projection['exclusions_sha256'],
               'catalog_text_policy_sha256': projection['text_policy_sha256'], 'pending_reviews_kept_original': 0}
    save('data/counts.json', counts);save('docs/WHITE_BACKGROUND_SELECTION.json', summary)
    guide = data['docs/PRODUCTION_RELEASE.md'].read_text().replace('107,815', f"{counts['products']:,}").replace('95,401', f"{len(rows):,}")
    old_white = sum(v for k, v in inventory['image_selection']['counts'].items() if k != 'original')
    guide = guide.replace(f'{old_white:,}', f"{counts['white_background_selections']:,}").replace(str(inventory['image_selection']['counts']['original']), str(counts['original_background_selections']))
    guide = guide.replace('The image review is\nincomplete; this is a verified selection with original-image fallbacks.', 'Automated and human batch reviews are complete for this selection. Original-image fallbacks remain for scenes and rejected or uncertain results.')
    guide = guide.replace(f"{old_manifest['counts']['image_files']:,}", f"{counts['image_files']:,}")
    guide += '\n## Catalog cleanup\n\n77 Star Wars products are excluded, with their image assignments and merchandising links removed. Disney text is replaced with Datney in catalog data. Source data and images remain intact in the operator archive.\n'
    save('docs/PRODUCTION_RELEASE.md', guide.encode())
    card = data['docs/DATA_CARD.md'].read_text()
    for key in ('products', 'image_files', 'distinct_image_hashes'):
        card = card.replace(f"{old_manifest['counts'][key]:,}", f"{counts[key]:,}")
    card = card.replace(f"{old_manifest['counts']['product_types']['simple']:,}", f"{counts['product_types']['simple']:,}")
    save('docs/DATA_CARD.md', card.encode())
    save('docs/CATALOG_CLEANUP.json', {'excluded_products':len(excluded), 'text_replacements':projection['text_replacements'], 'exclusions_sha256':projection['exclusions_sha256'], 'text_policy_sha256':projection['text_policy_sha256']})
    save('docs/build_clean_media_release.py', Path(__file__).read_bytes())
    save('docs/catalog_exclusions.py', Path(cleanup.__file__).read_bytes())
    for path in list(full.glob('media-*.tar')):
        path.unlink()
    (full / 'catalog.tar').unlink()
    artifacts = [write_archive(full / 'catalog.tar', data), next(a for a in old_manifest['artifacts'] if a['path'] == 'module.tar')]
    artifacts += media_archives(full, images)
    manifest = {**old_manifest, 'counts':counts, 'artifacts':artifacts, 'catalog_cleanup':summary,
                'media_update_source':{**old_manifest['media_update_source'], 'cleanup_builder_sha256':digest(Path(__file__))}}
    (full / 'manifest.json').write_bytes(encoded(manifest))
    toolkit_manifest = json.loads((toolkit / 'manifest.json').read_text())
    tools = extract_subset(toolkit, toolkit_manifest, output / 'clean-toolkit', lambda n: True)
    tools.update({'README.md':guide.encode(), 'docs/PRODUCTION_RELEASE.md':guide.encode(), 'docs/DATA_CARD.md':data['docs/DATA_CARD.md'], 'docs/WHITE_BACKGROUND_SELECTION.json':data['docs/WHITE_BACKGROUND_SELECTION.json'], 'docs/CATALOG_CLEANUP.json':data['docs/CATALOG_CLEANUP.json']})
    (toolkit / 'tools.tar').unlink()
    artifact = write_archive(toolkit / 'tools.tar', tools)
    (toolkit / 'manifest.json').write_bytes(encoded({'schema':1,'release':tag,'profile':'toolkit','artifacts':[artifact]}))
    for path in assets.iterdir():
        if path.name.startswith(('full-', 'toolkit-')):
            path.unlink()
    pins = {}
    for name, folder in [('full', full), ('toolkit', toolkit)]:
        pins[name] = digest(folder / 'manifest.json')
        verify_release(folder, pins[name])
        for path in folder.iterdir():
            (assets / (name + '-' + path.name)).hardlink_to(path)
    (assets / 'README.md').write_text(guide)
    inventory.update(counts=counts, profile_pins=pins, image_selection=summary,
                     offline_verification=verify_release(full,pins['full']), toolkit_verification=verify_release(toolkit,pins['toolkit']),
                     preserved_nonmedia_members={n:digest(p) for n,p in data.items() if n=='data/6-qa.csv'})
    inventory['assets'] = {p.name:{'bytes':p.stat().st_size,'sha256':digest(p)} for p in assets.iterdir() if p.name not in ('release-inventory.json','SHA256SUMS')}
    (assets / 'release-inventory.json').write_bytes(encoded(inventory))
    (assets / 'SHA256SUMS').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in sorted(assets.iterdir()) if p.name!='SHA256SUMS'))
    (output / 'prepublication-verification.json').write_bytes(encoded({'prepared':True,'published':False,'profile_pins':pins,'counts':counts,'all_catalog_rows_match_approved_cleanup':True,'full':inventory['offline_verification'],'toolkit':inventory['toolkit_verification']}))
    return inventory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base','selection','output','job'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--tag',required=True)
    args = parser.parse_args();logging.basicConfig(level=logging.INFO)
    result=build(args.base,args.selection,args.output,args.tag,args.job)
    print(json.dumps({'counts':result['counts'],'pins':result['profile_pins']}))
