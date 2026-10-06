import copy
import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / 'build_qa_catalog.py'
spec = importlib.util.spec_from_file_location('qa_catalog', SCRIPT)
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


def source_export(root):
    (root / 'data').mkdir(parents=True)
    (root / 'media/wands-expanded').mkdir(parents=True)
    rows = []
    for i in range(12):
        rows.append({'sku': f'WANDS-{i:06}', 'name': f'Source {i}', 'product_online': '1',
                     'visibility': 'Catalog, Search', 'wands_product_class': f'class-{i}',
                     'color': ('Black', 'White')[i // 2 % 2],
                     'wands_finish': ('Matte', 'Satin')[i % 2]})
    groups = [{'sku': r['sku'], 'color': r['color'], 'wands_finish': r['wands_finish']} for r in rows[:4]]
    parent = {'sku': 'WANDS-PARENT', 'configurable_variations': '|'.join(qa.key_values(g) for g in groups)}
    media = []
    for i, row in enumerate(rows):
        # Accepted export hashes are the authority; no renderer is invoked here.
        image = root / f'media/wands-expanded/{i:02}.jpg'
        image.write_bytes(b'\xff\xd8' + str(i).encode() + b'\xff\xd9')
        media.append({'sku': row['sku'], 'base_image': f'/wands-expanded/{i:02}.jpg'})
    for name, data in [('1-simple.csv', rows), ('2-configurable.csv', [parent]), ('4-media.csv', media)]:
        with (root / 'data' / name).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0]))
            writer.writeheader(); writer.writerows(data)
    files = {p.relative_to(root).as_posix(): {'sha256': qa.sha(p), 'bytes': p.stat().st_size}
             for p in root.rglob('*') if p.is_file()}
    qa.write_json(root / 'manifest.json', {'profile': 'expanded-measurement-free', 'products': 107688, 'files': files})
    return qa.sha(root / 'manifest.json')


class QACatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'accepted'
        self.pin = source_export(self.source)
        _, selected, family, assets = qa.load_sources(self.source, self.pin)
        self.fixtures = qa.make_suite(selected, family, assets)
        self.by_sku = {f['product']['sku']: f for f in self.fixtures}

    def test_suite_counts_and_closed_dependency_graph(self):
        qa.validate(self.fixtures)
        self.assertEqual(len(self.fixtures), 127)
        self.assertEqual(dict(qa.Counter(f['product']['product_type'] for f in self.fixtures)), qa.EXPECTED_TYPES)

    def test_required_and_optional_variants_cover_every_custom_option(self):
        cases = [f for f in self.fixtures if 'custom_options' in f['product']]
        self.assertEqual(len(cases), 20)
        self.assertEqual({(f['expected']['option_type'], f['expected']['required']) for f in cases},
                         {(kind, required) for kind in qa.OPTION_TYPES for required in (False, True)})
        file_option = self.by_sku['WANDS-QA-OPTION-FILE-1']['product']['custom_options']
        self.assertIn('file_extension=pdf,txt', file_option)
        self.assertEqual(self.by_sku['WANDS-QA-OPTION-FIELD-1']['product']['price'], '200')
        self.assertEqual(self.by_sku['WANDS-QA-OPTION-FIELD-1']['expected']['first_option_price_delta'], 20)
        self.assertEqual(self.by_sku['WANDS-QA-OPTION-FIELD-0']['expected']['first_option_price_delta'], 10)

    def test_configurable_completeness_sparse_and_nonphysical_children(self):
        full = qa.variations(self.by_sku['WANDS-QA-CONFIG-FULL-THREE']['product'])
        sparse = qa.variations(self.by_sku['WANDS-QA-CONFIG-SPARSE-THREE']['product'])
        self.assertEqual(len(full), 8)
        self.assertEqual(len(sparse), 5)
        self.assertEqual(set(full[0]), {'sku', 'color', 'wands_finish', 'wands_size'})
        for g in qa.variations(self.by_sku['WANDS-QA-CONFIG-VIRTUAL']['product']):
            child = self.by_sku[g['sku']]['product']
            self.assertEqual(child['product_type'], 'virtual')
            self.assertFalse(child['weight'])

    def test_bundle_controls_pricing_and_shipping_modes(self):
        cases = [f for f in self.fixtures if f['product']['product_type'] == 'bundle']
        self.assertEqual({(f['expected']['control'], f['expected']['price_type']) for f in cases},
                         {(control, price) for control in ('select', 'radio', 'checkbox', 'multi') for price in ('fixed', 'dynamic')})
        self.assertEqual(sum(not f['expected']['shipping_required'] for f in cases), 2)
        for f in cases:
            if f['expected']['control'] in {'checkbox', 'multi'}:
                self.assertFalse(f['expected']['customer_qty'])

    def test_download_controls_have_all_limit_sharing_selection_combinations(self):
        cases = [f for f in self.fixtures if f['product']['product_type'] == 'downloadable']
        self.assertEqual({(int(f['product']['links_purchased_separately']), f['expected']['downloads_per_link'],
                           f['expected']['shareable']) for f in cases},
                         {(separate, limit, share) for separate in (0, 1) for limit in (0, 3) for share in (0, 1, 2)})
        for f in cases:
            row = f['product']
            self.assertIn('purchased_separately=' + row['links_purchased_separately'], row['downloadable_links'])
            self.assertIn('group_title=QA Downloads', row['downloadable_links'])

    def test_grouped_associations_include_downloadable_and_virtual_products(self):
        kinds = set()
        for f in self.fixtures:
            if f['product']['product_type'] == 'grouped':
                kinds.update(self.by_sku[sku]['product']['product_type'] for sku in f['expected']['associated_skus'])
        self.assertEqual(kinds, {'simple', 'virtual', 'downloadable'})

    def test_rejects_duplicate_sku_and_external_dependencies(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate QA SKU'):
            qa.validate(self.fixtures + [self.fixtures[0]])
        broken = copy.deepcopy(self.fixtures)
        next(f for f in broken if f['product']['product_type'] == 'grouped')['product']['associated_skus'] = 'WANDS-ORIGINAL=1'
        with self.assertRaisesRegex(ValueError, 'Invalid grouped dependency'):
            qa.validate(broken)

    def test_rejects_repeated_configurable_combination(self):
        broken = copy.deepcopy(self.fixtures)
        row = next(f['product'] for f in broken if f['product']['product_type'] == 'configurable')
        row['configurable_variations'] += '|' + row['configurable_variations'].split('|')[0]
        with self.assertRaisesRegex(ValueError, 'Duplicate configurable'):
            qa.validate(broken)

    def test_downloads_cannot_escape_or_use_remote_urls(self):
        for member in ('title=Bad,file=../private.txt', 'title=Bad,url=https://example.com/file.pdf'):
            broken = copy.deepcopy(self.fixtures)
            next(f['product'] for f in broken if f['product']['product_type'] == 'downloadable')['downloadable_links'] = member
            with self.assertRaises(ValueError):
                qa.validate(broken)

    def test_download_assets_are_deterministic_and_readable(self):
        pdf = qa.pdf_bytes('QA Test')
        xref = int(pdf.split(b'startxref\n')[1].splitlines()[0])
        self.assertEqual(pdf[xref:xref+4], b'xref')
        with zipfile.ZipFile(io.BytesIO(qa.zip_bytes())) as z:
            self.assertIsNone(z.testzip())
            self.assertTrue(json.loads(z.read('materials.json'))['synthetic'])
        self.assertEqual(qa.zip_bytes(), qa.zip_bytes())

    def test_tier_prices_use_wands_currency_scope(self):
        for sku in ('WANDS-QA-PRICE-TIER-ALL', 'WANDS-QA-PRICE-GROUP-GUEST'):
            self.assertEqual(self.by_sku[sku]['product']['_tier_price_website'], 'wands')

    def test_build_is_reproducible_and_csv_preserves_options(self):
        first = self.root / 'first'; second = self.root / 'second'
        qa.build(self.source, self.pin, first); qa.build(self.source, self.pin, second)
        self.assertEqual(qa.sha(first / 'manifest.json'), qa.sha(second / 'manifest.json'))
        csv_by_sku = {r['sku']: r for r in qa.csv_rows(first / 'data/products.csv')}
        for fixture in self.fixtures:
            for field, value in fixture['product'].items():
                self.assertEqual(csv_by_sku[fixture['product']['sku']][field], value)
        self.assertEqual(qa.verify_package(first)['counts']['products'], 127)

    def test_refuses_existing_destination(self):
        with self.assertRaisesRegex(ValueError, 'Fresh independent output'):
            qa.build(self.source, self.pin, self.source)

    def test_tampered_source_and_package_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'pin differs'):
            qa.build(self.source, '0' * 64, self.root / 'wrong-pin')
        output = self.root / 'output'; qa.build(self.source, self.pin, output)
        (output / 'fixtures.json').write_text('[]')
        with self.assertRaisesRegex(ValueError, 'member changed'):
            qa.verify_package(output)
        (self.source / 'media/wands-expanded/00.jpg').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'image differs'):
            qa.build(self.source, self.pin, self.root / 'bad-image')


if __name__ == '__main__':
    unittest.main()
