#!/usr/bin/env python3
"""Build the approved doubled catalog as immutable data. No store or model calls."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import csv
import hashlib
import html
import json
from pathlib import Path
import re

from expansion_profiles import EXISTING, EXISTING_QUOTAS, EXPANSIONS, NAME_FIRST, NAME_LAST
from image_policy import VERSION as IMAGE_POLICY, product_prompt, validate_prompt
from prepare_catalog import sha256, slug
from realism_rules import COLLECTIONS

VERSION = 'wands-expansion-20260918-v1'
BASE_PIN = 'b525ca0441e7f04858613fdcba4d8e3ae18421240f4c25a757bf34fa5587951b'
DISCLOSURE = ('Synthetic product design, options, prices and specifications for a demonstration catalog. '
              'Dimensions are fictional lab specifications, not manufacturer measurements or fit guarantees. '
              'Images are generated illustrations.')
PALETTE = ('Black', 'White', 'Green', 'Navy', 'Terracotta', 'Gray', 'Cream', 'Blue', 'Beige', 'Ivory')
SCALES = (.84, .92, 1.0, 1.08, 1.16)
EXPECTED = {'products': 107688, 'simple': 103643, 'configurable': 3995, 'bundle': 50,
            'configurable_links': 27736, 'new_products': 53844, 'new_standalones': 34844,
            'new_parents': 2000, 'new_children': 17000, 'existing_family_children': 8000}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def csv_rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    columns = ['sku'] + sorted(set().union(*(set(row) for row in rows)) - {'sku'})
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n')


def variations(row):
    result = []
    for group in row.get('configurable_variations', '').split('|'):
        if group:
            fields = [field.split('=', 1) for field in group.split(',')]
            if any(len(field) != 2 for field in fields) or len(dict(fields)) != len(fields):
                raise ValueError('Invalid configurable relationship: ' + row['sku'])
            result.append(dict(fields))
    return result


def encode_variations(groups):
    return '|'.join(','.join(['sku=' + g['sku']] + [k + '=' + g[k] for k in sorted(g) if k != 'sku']) for g in groups)


def load_baseline(data, manifest_path):
    if sha256(manifest_path) != BASE_PIN:
        raise ValueError('Baseline release manifest differs from the approved pin')
    manifest = json.loads(manifest_path.read_text())
    inventory = next(a['files'] for a in manifest['artifacts'] if a['path'] == 'catalog.tar')
    for name, item in inventory.items():
        if name.startswith('data/'):
            path = data / name.removeprefix('data/')
            if not path.is_file() or sha256(path) != item['sha256']:
                raise ValueError('Baseline data changed: ' + name)
    rows = [r for name in ('1-simple.csv', '2-configurable.csv', '3-bundle.csv') for r in csv_rows(data/name)]
    result = {r['sku']: r for r in rows}
    if len(result) != 53844 or len(rows) != len(result):
        raise ValueError('Unexpected baseline identities')
    return result


def category_map(rows):
    result = defaultdict(Counter)
    all_paths = {}
    for row in rows.values():
        for path in row.get('categories', '').split(','):
            parts = path.split('/')
            if len(parts) < 3:
                continue
            all_paths[normalize_category(path)] = path
            for cls in row.get('wands_product_class', '').split('|'):
                result[(parts[1], cls.strip().casefold())][path] += 1
    return result, all_paths


def normalize_category(path):
    return '/'.join(re.sub(r'[^\w]+', '', p.casefold()) for p in path.split('/'))


def resolve_category(profile, department, index):
    matches = index.get((department, profile.product_class.casefold()))
    if not matches:
        raise ValueError('No existing category for ' + department + ': ' + profile.product_class)
    return sorted(matches, key=lambda p: (-matches[p], len(p.split('/')), p))[0]


def make_design(profile, index, department, category, sku, lane):
    # Mixed-radix enumeration gives unique material/structure/geometry combinations
    # within a profile. Color does not manufacture extra standalone identities.
    n = index
    material = profile.materials[n % len(profile.materials)]; n //= len(profile.materials)
    construction = profile.designs[n % len(profile.designs)]; n //= len(profile.designs)
    width_scale = SCALES[n % len(SCALES)]; n //= len(SCALES)
    depth_scale = SCALES[n % len(SCALES)]; n //= len(SCALES)
    height_scale = SCALES[n % len(SCALES)]; n //= len(SCALES)
    if n:
        raise ValueError('Exhausted unique physical designs for ' + profile.key)
    surface_detail = ''
    if profile.key in {'round-rug', 'bowl', 'mug', 'canister', 'vase', 'candle-holder'}:
        # Circular forms keep their plan proportions. A real surface treatment,
        # rather than an invisible identifier, distinguishes the depth radix.
        surface_detail = ('fine linear surface texture', 'subtle crosshatched surface texture',
                          'smooth uniform surface', 'gently stippled surface texture',
                          'fine repeating ripple texture')[SCALES.index(depth_scale)]
        depth_scale = width_scale
        construction += '; ' + surface_detail
    if profile.dimensions[2] < 1:
        # Sub-millimeter rounding must not create duplicate fabric designs.
        construction += '; ' + ('plain edge stitching', 'double-row edge stitching',
                                 'decorative zigzag edge stitching', 'scalloped edge stitching',
                                 'contrasting blanket edge stitching')[SCALES.index(height_scale)]
        height_scale = 1.0
    name = NAME_FIRST[index % len(NAME_FIRST)] + ' ' + NAME_LAST[(index // len(NAME_FIRST)) % len(NAME_LAST)]
    dimensions = {axis: round(value * factor, 1) for axis, value, factor in zip(
        ('width', 'depth', 'height'), profile.dimensions, (width_scale, depth_scale, height_scale))}
    color = PALETTE[int(digest([profile.key, index])[:8], 16) % len(PALETTE)]
    base_price = profile.price * (0.85 + .1 * (index % 5)) * (sum(dimensions.values()) / sum(profile.dimensions)) ** .45
    return {'schema': 1, 'recipe': VERSION, 'sku': sku, 'lane': lane, 'department': department,
            'profile': profile.key, 'product_class': profile.product_class, 'category': category,
            'subject': profile.subject, 'collection': name, 'material': material,
            'construction': construction, 'color': color, 'dimensions_cm': dimensions,
            'base_price': round(max(4, base_price)) + .99, 'source': 'authored synthetic design',
            'style': ('Contemporary', 'Modern', 'Scandinavian', 'Transitional')[index % 4],
            'reference_required': False}


def product_row(design, *, parent=False, options=None, scale=1.0):
    options = options or {}
    color = options.get('color', design['color'])
    name = design['collection'] + ' ' + design['subject'].removeprefix('single ').split(' neatly ')[0].split(' laid flat')[0].title()
    if not parent:
        name += ' - ' + ', '.join(options.values() or [color])
    brand = COLLECTIONS.get(design['department'], ('Morrow Grid', ''))[0]
    price = f"{round((design['base_price'] - .99) * scale ** .65) + .99:.2f}"
    bucket = int(digest(design['sku'])[:8], 16)
    stock = 'out_of_stock' if bucket % 29 == 0 else 'low_stock' if bucket % 11 == 0 else 'in_stock'
    quantity = 0 if stock == 'out_of_stock' else 3 if stock == 'low_stock' else 20 + bucket % 70
    specifications = {f'lab_spec_{key}_cm': f'{value * scale:.1f}' for key, value in design['dimensions_cm'].items()}
    if parent:
        specifications = {}  # Child size choices must not become one parent dimension.
    appearance = design['material'] + ' construction with ' + design['construction']
    facts = '' if parent else '<p>Color: ' + html.escape(color) + '.</p>'
    specs_html = ''.join('<li>' + key.removeprefix('lab_spec_').replace('_cm', '').title() + ' (cm): ' + value +
                         ' (synthetic lab specification)</li>' for key, value in sorted(specifications.items()))
    description = '<p>' + html.escape(name) + '.</p><p>' + html.escape(appearance) + '.</p>' + facts
    description += '<section data-wands-specifications="v1"><h3>Product specifications</h3><ul>' + specs_html + '</ul><p>' + DISCLOSURE + '</p></section>'
    volume = 1
    for dimension in design['dimensions_cm'].values(): volume *= dimension * scale
    density = .00035 if design['department']=='Kitchen & Tabletop' else .000055
    weight = f'{max(.05, volume*density):.2f}'
    return {'sku': design['sku'], 'attribute_set_code': 'Default', 'product_type': 'configurable' if parent else 'simple',
            'product_websites': 'wands', 'store_view_code': '', 'categories': design['category'] if not options else '',
            'name': name[:255], 'description': description, 'short_description': '<p>' + html.escape(appearance) + '.</p><p>' + DISCLOSURE + '</p>',
            'meta_title': name[:255], 'meta_description': (appearance + '. ' + DISCLOSURE)[:255],
            'url_key': slug(design['sku'].lower() + '-' + name)[:240], 'product_online': '1',
            'visibility': 'Not Visible Individually' if options else 'Catalog, Search',
            'price': price, 'tax_class_name': 'Taxable Goods', 'weight': weight,
            'qty': str(quantity), 'is_in_stock': '1' if quantity else '0', 'manage_stock': '0' if parent else '1',
            'use_config_manage_stock': '0', 'out_of_stock_qty': '0', 'use_config_min_qty': '1',
            'backorders': '0', 'use_config_backorders': '0', 'lab_stock_scenario': stock,
            'lab_brand': brand, 'lab_sale_unit': 'one complete product as described',
            'lab_price_synthetic': 'Yes', 'lab_price_method': 'authored-class-material-geometry', 'lab_price_version': VERSION,
            'lab_spec_material': design['material'], 'lab_spec_color': '' if parent else color,
            'lab_spec_style': design['style'], 'lab_spec_disclosure': DISCLOSURE,
            'wands_product_id': '', 'wands_product_class': design['product_class'],
            'wands_average_rating': '', 'wands_review_count': '', **specifications, **options}


def image_job(design, skus, *, reference=None):
    body = ('Photorealistic ecommerce studio photograph, complete product centered with generous margins. '
            'One ' + design['subject'] + '. ' + design['construction'] + '. '
            'Material: ' + design['material'] + '. Color: ' + design['color'] + '. '
            'Warm-white seamless background, soft natural light, realistic joints and surface texture. '
            'No extra products, people or clipped edges.')
    if reference:
        body = ('Edit the reference photograph. Preserve the exact product silhouette, construction, '
                'piece count, pattern, viewpoint and background. Change only ' + reference['axis'] +
                ' to ' + reference['value'] + '. No additional objects.')
    prompt = product_prompt(body)
    validate_prompt(prompt)
    identity = digest({'design': design, 'prompt': prompt, 'reference': reference})
    return {'schema': 1, 'job_id': identity, 'sku': skus[0], 'skus': skus,
            'lane': design['lane'], 'profile': design['profile'], 'department': design['department'],
            'design': design, 'design_sha256': digest(design), 'prompt': prompt,
            'seed': int(identity[:8], 16), 'output_file': skus[0] + '-' + identity[:12] + '.jpg',
            'image_policy_version': IMAGE_POLICY, 'reference': reference, 'visual_acceptance': 'pending'}


def update_option_description(row, groups):
    values = defaultdict(set)
    for group in groups:
        for key, value in group.items():
            if key != 'sku': values[key].add(value)
    labels = dict(field.split('=', 1) for field in row['configurable_variation_labels'].split(','))
    text = '; '.join(labels.get(key, key) + ': ' + ', '.join(sorted(options)) for key, options in sorted(values.items()))
    description = re.sub(r'<p>Available options:.*?</p>', '', row.get('description', ''), flags=re.S)
    return description + '<p>Available options: ' + html.escape(text) + '.</p>'


def extension_candidates(parent, rows, lineage):
    groups = variations(parent)
    if len(groups) >= 12:
        return []
    axis = next((a for a in ('color', 'wands_finish') if a in groups[0]), None)
    if axis is None:
        return []
    used = {g[axis] for g in groups}
    if axis == 'color':
        palette = PALETTE
    elif used & {'Brass', 'Chrome', 'Brushed Nickel', 'Bronze'}:
        palette = ('Matte Black', 'Brushed Nickel', 'Bronze', 'Brass', 'Chrome', 'White')
    else:
        palette = ('Walnut', 'Oak', 'Black', 'White', 'Cream', 'Espresso', 'Natural')
    unique_bases = {}
    for g in groups:
        key = tuple(sorted((k, v) for k, v in g.items() if k not in ('sku', axis)))
        unique_bases.setdefault(key, g)
    candidates = []
    for color in palette:
        if color in used: continue
        for key, base in sorted(unique_bases.items()):
            if base['sku'] not in lineage: continue
            options = {k: v for k, v in base.items() if k != 'sku'}
            options[axis] = color
            sku = 'WANDS-SYN-V-' + digest([parent['sku'], options])[:16].upper()
            row = copy.deepcopy(rows[base['sku']])
            old = row[axis]
            for field in ('name', 'description', 'short_description', 'meta_title', 'meta_description'):
                row[field] = re.sub(r'(?<!\w)' + re.escape(old) + r'(?!\w)', color, row.get(field, ''), flags=re.I)
                if field in ('name','meta_title','meta_description'):row[field]=row[field][:255]
            row.update({'sku': sku, axis: color, 'lab_spec_color' if axis == 'color' else 'lab_spec_finish': color,
                        'url_key': slug(sku.lower() + '-' + row['name'])[:240], 'categories': '',
                        'wands_product_id': '', 'wands_average_rating': '', 'wands_review_count': '',
                        'lab_spec_disclosure': DISCLOSURE, 'lab_price_version': VERSION,
                        'visibility': 'Not Visible Individually', 'product_type': 'simple', 'product_online': '1'})
            design = {'sku': sku, 'recipe': VERSION, 'lane': 'existing-family-children',
                      'profile': parent['wands_product_class'], 'department': parent['categories'].split('/')[1],
                      'parent_sku': parent['sku'], 'source_child_sku': base['sku'], 'options': options,
                      'subject': row['name'], 'material': row.get('lab_spec_material', ''), 'color': color,
                      'construction': 'preserve the accepted source-child reference', 'reference_required': True,
                      'dimensions_cm': {k: v for k, v in row.items() if k.startswith('lab_spec_') and k.endswith('_cm') and v}}
            reference = {**lineage[base['sku']], 'sku': base['sku'], 'axis': axis, 'value': color}
            candidates.append((row, {'sku': sku, **options}, image_job(design, [sku], reference=reference)))
    return candidates[:12-len(groups)]


def validate_catalog(rows, baseline, new_skus, counts):
    if len(rows) != EXPECTED['products'] or len(new_skus) != EXPECTED['new_products']:
        raise ValueError('Expansion product count mismatch')
    types = Counter(r['product_type'] for r in rows.values())
    for kind in ('simple', 'configurable', 'bundle'):
        if types[kind] != EXPECTED[kind]: raise ValueError('Product type count mismatch: ' + kind)
    urls = [r['url_key'] for r in rows.values()]
    if len(urls) != len(set(urls)): raise ValueError('Duplicate URL key')
    links = {}; total = 0
    for row in rows.values():
        if row['product_type'] != 'configurable': continue
        seen = set()
        for group in variations(row):
            child = rows[group['sku']]; options = tuple(sorted((k, v) for k, v in group.items() if k != 'sku'))
            if options in seen or group['sku'] in links: raise ValueError('Duplicate configurable combination or parent')
            if child['product_type'] != 'simple' or child['visibility'] != 'Not Visible Individually':
                raise ValueError('Invalid configurable child: ' + child['sku'])
            if any(child[k] != v for k, v in options): raise ValueError('Option mismatch: ' + child['sku'])
            seen.add(options); links[group['sku']] = row['sku']; total += 1
    if total != EXPECTED['configurable_links']: raise ValueError('Configurable link count mismatch')
    for sku in new_skus:
        row = rows[sku]
        if not sku.startswith('WANDS-SYN-') or row.get('wands_product_id') or row.get('wands_review_count') or row.get('wands_average_rating'):
            raise ValueError('Invented source identity or rating: ' + sku)
        if row['visibility'] == 'Not Visible Individually' and sku not in links: raise ValueError('Orphan new child')
    for sku, old in baseline.items():
        current = rows[sku]
        allowed = {'configurable_variations', 'description'} if old['product_type'] == 'configurable' else set()
        if {k: v for k, v in old.items() if k not in allowed} != {k: v for k, v in current.items() if k not in allowed}:
            raise ValueError('Protected baseline record changed: ' + sku)
    counts.update({'products': len(rows), 'product_types': dict(types), 'configurable_links': total,
                   'enabled_visible': sum(r['product_online']=='1' and r['visibility']=='Catalog, Search' for r in rows.values()),
                   'disabled_products': sum(r['product_online']=='2' for r in rows.values())})


def build(data, baseline_manifest, output):
    if output.exists(): raise ValueError('Use a new immutable output directory')
    baseline = load_baseline(data, baseline_manifest)
    rows = copy.deepcopy(baseline)
    category_index, existing_paths = category_map(rows)
    lineage = json.loads((data/'media-lineage.json').read_text())['assignments']
    jobs, definitions, new_skus, category_records = [], [], set(), {}
    counts = {'added_by_area': {}, 'added_by_lane': Counter()}
    profile_index = Counter()
    physical_designs = set()

    def add_row(row):
        if row['sku'] in rows: raise ValueError('SKU collision')
        rows[row['sku']] = row; new_skus.add(row['sku'])

    def add_area(area, department, profiles, standalone_count, parent_count, children_per_parent, parent_path=None):
        before = len(new_skus)
        lane = 'expanded-categories' if parent_path else 'existing-categories'
        for number in range(standalone_count + parent_count):
            profile = profiles[number % len(profiles)]
            counter_key = (area, profile.key)
            index = profile_index[counter_key]; profile_index[counter_key] += 1
            if parent_path:
                proposed = 'WANDS Catalog/' + parent_path + '/' + profile.category
                category = existing_paths.get(normalize_category(proposed), proposed)
                category_records[category] = {'path': category, 'existing': normalize_category(category) in existing_paths, 'area': area}
            else:
                category = resolve_category(profile, department, category_index)
            family = number < parent_count
            sku = 'WANDS-SYN-' + ('P-' if family else 'S-') + area.upper().replace(' ', '-')[:20] + '-' + f'{number+1:05d}'
            design = make_design(profile, index, department, category, sku, lane)
            physical = digest({k:design[k] for k in ('subject','material','construction','dimensions_cm')})
            if physical in physical_designs: raise ValueError('Duplicate physical design: ' + sku)
            physical_designs.add(physical)
            definitions.append(design)
            if not family:
                add_row(product_row(design)); jobs.append(image_job(design, [sku]))
                continue
            parent = product_row(design, parent=True)
            parent['qty'] = '1'; parent['is_in_stock'] = '1'; parent['lab_stock_scenario'] = 'family'
            colors = PALETTE[(index % 5):(index % 5)+3]
            groups = []
            family_reference = None
            for color_number, color in enumerate(colors):
                image_skus = []
                sizes = [('Small', .85), ('Large', 1.15)] if children_per_parent == 6 else [(None, 1)]
                for size, scale in sizes:
                    child_sku = sku.replace('WANDS-SYN-P-', 'WANDS-SYN-C-') + '-' + str(color_number+1) + ('-'+size.upper() if size else '')
                    child_design = {**design, 'sku': child_sku, 'color': color, 'parent_sku': sku}
                    options = {'color': color, **({'wands_size': size} if size else {})}
                    child = product_row(child_design, options=options, scale=scale)
                    add_row(child); groups.append({'sku': child_sku, **options}); image_skus.append(child_sku)
                if color_number == 0: image_skus.append(sku)
                image_design = {**design, 'sku': image_skus[0], 'color': color, 'parent_sku': sku,
                                'uniform_size_variants': len(sizes)>1}
                # Every color retains the first accepted family's construction.
                reference = ({'job_id': family_reference, 'axis': 'color', 'value': color}
                             if family_reference else None)
                job = image_job(image_design, image_skus, reference=reference)
                jobs.append(job)
                if family_reference is None: family_reference = job['job_id']
            parent['configurable_variations'] = encode_variations(groups)
            parent['configurable_variation_labels'] = 'color=Color' + (',wands_size=Size' if children_per_parent==6 else '')
            parent['description'] = update_option_description(parent, groups)
            parent['price'] = min((rows[g['sku']]['price'] for g in groups), key=float)
            add_row(parent)
        added = len(new_skus)-before
        counts['added_by_area'][area] = added; counts['added_by_lane'][lane] += added

    for department, (total, parents) in EXISTING_QUOTAS.items():
        add_area(slug(department), department, EXISTING[department], total-7*parents, parents, 6)
    for area, (path, standalone, parents, profiles) in EXPANSIONS.items():
        add_area(area, path.split('/')[0], profiles, standalone, parents, 3, path)

    # Round-robin extension avoids exhausting a few families before broad coverage.
    candidate_lists = {}
    for sku, parent in sorted(baseline.items()):
        if parent['product_type']=='configurable':
            candidates = extension_candidates(parent, rows, lineage)
            if candidates: candidate_lists[sku] = candidates
    remaining = 8000
    changed_groups = {}
    for depth in range(12):
        for sku, candidates in candidate_lists.items():
            if not remaining: break
            if depth >= len(candidates): continue
            row, group, job = candidates[depth]
            add_row(row); jobs.append(job); definitions.append(job['design'])
            changed_groups.setdefault(sku, variations(rows[sku])).append(group)
            remaining -= 1
        if not remaining: break
    if remaining: raise ValueError(f'Only {8000-remaining} valid family extensions, expected 8000')
    for sku, groups in changed_groups.items():
        rows[sku]['configurable_variations'] = encode_variations(groups)
        rows[sku]['description'] = update_option_description(rows[sku], groups)
    counts['added_by_lane']['existing-family-children'] = 8000
    counts['extended_existing_families'] = len(changed_groups)
    counts['new_products'] = len(new_skus)
    validate_catalog(rows, baseline, new_skus, counts)
    covered = [sku for job in jobs for sku in job['skus']]
    if len(covered)!=len(set(covered)) or set(covered)!=new_skus:
        raise ValueError('New media assignments must cover each new product exactly once')
    counts['new_image_jobs'] = len(jobs)
    counts['new_categories'] = sum(not r['existing'] for r in category_records.values())
    output.mkdir(parents=True)
    (output/'data').mkdir()
    for number, kind in enumerate(('simple', 'configurable', 'bundle'), 1):
        write_csv(output/'data'/f'{number}-{kind}.csv', [r for sku, r in sorted(rows.items()) if r['product_type']==kind])
    write_csv(output/'new-products.csv', [rows[sku] for sku in sorted(new_skus)])
    write_csv(output/'existing-parent-updates.csv', [{'sku': sku, 'configurable_variations': rows[sku]['configurable_variations'], 'description': rows[sku]['description']} for sku in sorted(changed_groups)])
    for filename, records in [('image-jobs.jsonl', jobs), ('designs.jsonl', definitions), ('categories.jsonl', list(category_records.values()))]:
        with (output/filename).open('x') as stream:
            for record in records: stream.write(canonical(record)+'\n')
    # Select 120 roots/designs including all authored profiles, standalone goods,
    # and existing-family extensions. Retain complete selected new-family media.
    by_area = defaultdict(list)
    for job in jobs:
        if job['lane'] != 'existing-family-children': by_area[(job['lane'], job['department'], job['profile'])].append(job)
    first = [values[0] for _, values in sorted(by_area.items())]
    extensions = [j for j in jobs if j['lane']=='existing-family-children']
    extension_groups = {}
    for j in extensions: extension_groups.setdefault((j['department'],j['profile']),j)
    first += list(extension_groups.values())[:24]
    seen = {j['job_id'] for j in first}
    extras = [j for j in jobs if j['job_id'] not in seen and not j['design'].get('parent_sku')]
    pilot = (first + extras)[:120]
    parent_keys = {j['design'].get('parent_sku') for j in pilot if j['design'].get('parent_sku')}
    pilot += [j for j in jobs if j['design'].get('parent_sku') in parent_keys and j['job_id'] not in {p['job_id'] for p in pilot}]
    write_json(output/'pilot.json', {'job_ids': [j['job_id'] for j in pilot], 'count': len(pilot), 'status': 'pending generation and review'})
    write_json(output/'counts.json', counts)
    inputs = {str(p.relative_to(data)): sha256(p) for p in sorted(data.iterdir()) if p.is_file()}
    outputs = {str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}
    write_json(output/'manifest.json', {'schema':1, 'recipe':VERSION, 'baseline_manifest_sha256':BASE_PIN,
               'status':'data candidate; all new media pending; not importable', 'counts':counts,
               'source_files': {p.name:sha256(p) for p in [Path(__file__), Path(__file__).with_name('expansion_profiles.py'), Path(__file__).with_name('image_policy.py')]},
               'inputs':inputs, 'outputs':outputs, 'image_policy':IMAGE_POLICY})
    return counts


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-data', type=Path, required=True)
    parser.add_argument('--baseline-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.baseline_data, args.baseline_manifest, args.output), indent=2))
