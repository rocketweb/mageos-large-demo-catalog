import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'distribution'))
from build_expanded_release import acceptance_summary, media_archives, product_inventory, verified_files
from release import digest, verify_release


class ExpandedReleaseTest(unittest.TestCase):
    def test_explicit_public_inventory_rejects_changed_and_escaping_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'accepted.csv'
            source.write_bytes(b'sku\noriginal\n')
            inventory = {'accepted.csv': {'bytes': source.stat().st_size, 'sha256': digest(source)}}
            (root / 'private-backup.sql').write_text('DO NOT SHIP')
            files = verified_files(root, inventory, ['accepted.csv'])
            self.assertEqual(set(files), {'accepted.csv'})
            source.write_bytes(b'sku\nmodified\n')
            with self.assertRaisesRegex(ValueError, 'changed'):
                verified_files(root, inventory, ['accepted.csv'])
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                verified_files(root, inventory, ['../secret'])
            source.unlink()
            source.symlink_to(root / 'private-backup.sql')
            with self.assertRaisesRegex(ValueError, 'changed'):
                verified_files(root, inventory, ['accepted.csv'])

    def test_chunked_archives_round_trip_deterministically_with_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {}
            for index, suffix in enumerate(('jpg', 'jpg', 'pdf', 'zip')):
                path = root / f'{index}.{suffix}'
                path.write_bytes(bytes([index]) * 600000)
                files['media/wands-qa/' + path.name] = path
            one, two = root / 'one', root / 'two'
            one.mkdir(); two.mkdir()
            first = media_archives(one, files, 1)
            second = media_archives(two, files, 1)
            self.assertEqual(len(first), 4)
            self.assertEqual(first, second)
            self.assertTrue(all(item['bytes'] <= 1024 ** 2 for item in first))
            content = (json.dumps({'schema': 1, 'artifacts': first}) + '\n').encode()
            (one / 'manifest.json').write_bytes(content)
            out = root / 'extracted'
            result = verify_release(one, hashlib.sha256(content).hexdigest(), out)
            self.assertEqual(result['files'], 4)
            for name, path in files.items():
                self.assertEqual((out / name).read_bytes(), path.read_bytes())

    def test_combined_inventory_checks_dependencies_duplicates_and_update_sentinels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'products.csv'
            fields = ['sku', 'product_type', 'product_online', 'visibility', 'configurable_variations', 'price']
            rows = [dict(zip(fields, ['child', 'simple', '1', 'Not Visible Individually', '', '10'])),
                    dict(zip(fields, ['parent', 'configurable', '1', 'Catalog, Search', 'sku=child,color=Black', ''])),
                    dict(zip(fields, ['virtual', 'virtual', '0', 'Catalog, Search', '', '0'])),
                    dict(zip(fields, ['legacy-disabled', 'simple', '2', 'Catalog, Search', '', '10']))]
            def write():
                with path.open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
            write()
            result = product_inventory([path])
            self.assertEqual(result['products'], 4)
            self.assertEqual(result['configurable_links'], 1)
            self.assertEqual(result['disabled_products'], 2)
            self.assertEqual(result['enabled_visible_products'], 1)
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                product_inventory([path, path])
            rows[1]['configurable_variations'] = 'sku=missing,color=Black'
            write()
            with self.assertRaisesRegex(ValueError, 'dependency'):
                product_inventory([path])
            rows[1]['price'] = '__EMPTY__VALUE__'
            write()
            with self.assertRaisesRegex(ValueError, 'sentinel'):
                product_inventory([path])

    def test_acceptance_cannot_leak_private_receipts_or_qualify_another_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            row = {'database': {'passed': True, 'wands_products': 107815, 'product_types': {}},
                   'row_preservation': {'passed': True, 'existing_product_rows_changed': 0, 'existing_stock_rows_changed': 0},
                   'runtime': {'passed': True, 'product_checks': 934, 'cart_cases': 202, 'cart_compositions': 4, 'quotes_saved': 0, 'orders_created': 0},
                   'browser': {'passed': True, 'products_checked': 97, 'excluded_products_checked': 30},
                   'backup': {'path': '/private/customer.sql', 'password': 'DO NOT SHIP'}}
            receipt = {'passed': True, 'manifest_sha256': 'accepted', 'wands_products_per_store': 107815,
                       'tooling_tests': {'tests': 882, 'passed': True, 'skips': 0}, 'studio': row, 'comtom': row}
            path.write_text(json.dumps(receipt))
            summary = acceptance_summary(path, 'accepted')
            self.assertNotIn('/private/', json.dumps(summary))
            self.assertNotIn('DO NOT SHIP', json.dumps(summary))
            with self.assertRaisesRegex(ValueError, 'identity'):
                acceptance_summary(path, 'other')
            receipt['comtom']['browser']['passed'] = False
            path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                acceptance_summary(path, 'accepted')


if __name__ == '__main__':
    unittest.main()
