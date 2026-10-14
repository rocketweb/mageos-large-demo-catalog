import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'distribution'))
from navigation import canonical_categories, canonical_csv, canonical_row, canonical_value


class NavigationReleaseTest(unittest.TestCase):
    def test_json_inventory_keys_and_lineage_use_the_same_generated_identities(self):
        source = {'WANDS-SYN-P-HOME-IMPROVEMENT-00001': {'department': 'Home Improvement',
                  'path': 'WANDS Catalog/Home Improvement/Hardware', 'image': 'wands-expanded/abc.jpg', 'qty': 12}}
        self.assertEqual(canonical_value(source), {'WANDS-SYN-P-DIY-00001': {'department': 'DIY',
                         'path': 'WANDS Catalog/DIY/Hardware', 'image': 'wands-expanded/abc.jpg', 'qty': 12}})

    def test_generated_skus_urls_and_variant_references_change_together(self):
        row = {'sku': 'WANDS-SYN-P-HOME-IMPROVEMENT-00001',
               'url_key': 'wands-syn-p-home-improvement-00001-handle',
               'configurable_variations': 'sku=WANDS-SYN-C-HOME-IMPROVEMENT-00001-1-SMALL,color=Black',
               'related_skus': 'WANDS-123,WANDS-SYN-S-HOME-IMPROVEMENT-00061',
               'description': 'Original description', 'qty': '12.5000', 'categories': 'WANDS Catalog/Home Improvement/Hardware'}
        expected = {**row, 'sku': 'WANDS-SYN-P-DIY-00001', 'url_key': 'wands-syn-p-diy-00001-handle',
                    'configurable_variations': 'sku=WANDS-SYN-C-DIY-00001-1-SMALL,color=Black',
                    'related_skus': 'WANDS-123,WANDS-SYN-S-DIY-00061', 'categories': 'WANDS Catalog/DIY/Hardware'}
        self.assertEqual(canonical_row(row), expected)
        self.assertEqual(canonical_row(expected), expected)

    def test_paths_preserve_commas_and_multiple_assignments(self):
        self.assertEqual(canonical_categories(
            'WANDS Catalog/Home Improvement/Hardware,WANDS Catalog/Kitchen & Tabletop/Vases, Urns, Jars & Bottles,WANDS Catalog/Lighting/Lamps'),
            'WANDS Catalog/DIY/Hardware,WANDS Catalog/Kitchen/Vases, Urns, Jars & Bottles,WANDS Catalog/Decor/Lighting/Lamps')
        self.assertEqual(canonical_categories('Other Catalog/Home Improvement'), 'Other Catalog/Home Improvement')
        self.assertEqual(canonical_categories('WANDS Catalog/DIY/Hardware'), 'WANDS Catalog/DIY/Hardware')

    def test_canonical_export_changes_only_categories_and_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / 'source.csv', root / 'canonical.csv'
            fields = ['sku', 'categories', 'description', 'qty', 'configurable_variations']
            rows = [{'sku': 'WANDS-1', 'categories': 'WANDS Catalog/Home Improvement/Fixtures',
                     'description': 'A description, with commas\nand a newline.', 'qty': '12.5000',
                     'configurable_variations': 'sku=WANDS-2,color=Red|sku=WANDS-3,color=Blue'}]
            with source.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            original = source.read_bytes()
            self.assertEqual(canonical_csv(source, destination), 1)
            with destination.open(newline='') as stream:
                actual = list(csv.DictReader(stream))
            self.assertEqual(actual, [{**rows[0], 'categories': 'WANDS Catalog/DIY/Fixtures'}])
            self.assertEqual(source.read_bytes(), original)
            with self.assertRaises(ValueError):
                canonical_csv(source, destination)
