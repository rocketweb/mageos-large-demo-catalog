import csv
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'distribution'))
from build_media_release import (check_media_csv, check_references, extract_subset,
                                read_mapping, rewrite_inventory, rewrite_lineage)
from release import write_archive


class MediaReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = hashlib.sha256(b'original').hexdigest()
        self.new = hashlib.sha256(b'white').hexdigest()
        self.mapping = {'original_file': self.old + '.jpg', 'original_sha256': self.old,
                        'selected_file': self.new + '.jpg', 'selected_sha256': self.new,
                        'action': 'white_reused', 'reason': 'approved'}
        self.mappings = {self.mapping['original_file']: self.mapping}

    def csv(self, name, rows):
        path = self.root / name
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
        return path

    def media_row(self, sha):
        return {'sku': 'product', 'base_image': '/wands-expanded/' + sha + '.jpg',
                'small_image': '/wands-expanded/' + sha + '.jpg',
                'thumbnail': '/wands-expanded/' + sha + '.jpg', 'base_image_label': 'Product label'}

    def test_all_image_roles_change_and_labels_and_row_coverage_stay_exact(self):
        original = self.csv('original.csv', [self.media_row(self.old)])
        row = self.media_row(self.new)
        selected = self.csv('selected.csv', [row])
        self.assertEqual(check_media_csv(original, selected, self.mappings), 1)
        row['thumbnail'] = '/wands-expanded/' + self.old + '.jpg'
        self.csv('selected.csv', [row])
        with self.assertRaisesRegex(ValueError, 'thumbnail'):
            check_media_csv(original, selected, self.mappings)
        row = self.media_row(self.new);row['base_image_label'] = 'Changed product'
        self.csv('selected.csv', [row])
        with self.assertRaisesRegex(ValueError, 'base_image_label'):
            check_media_csv(original, selected, self.mappings)
        self.csv('selected.csv', [self.media_row(self.new), self.media_row(self.new)])
        with self.assertRaisesRegex(ValueError, 'row count'):
            check_media_csv(original, selected, self.mappings)

    def test_mapping_rejects_duplicate_and_modified_original(self):
        path = self.csv('selection.csv', [self.mapping])
        self.assertEqual(len(read_mapping(path, expected=1)), 1)
        self.csv('selection.csv', [self.mapping, self.mapping])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            read_mapping(path, expected=1)
        changed = {**self.mapping, 'action': 'original'}
        self.csv('selection.csv', [changed])
        with self.assertRaisesRegex(ValueError, 'preserve exact bytes'):
            read_mapping(path, expected=1)

    def test_inventory_binds_selected_bytes_to_baseline_source(self):
        file = self.root / (self.new + '.jpg');file.write_bytes(b'white')
        source = {'media/wands-expanded/' + self.old + '.jpg': {'sha256': self.old}}
        inventory, images = rewrite_inventory(source, self.mappings, self.root, 'verification')
        key = 'media/wands-expanded/' + self.new + '.jpg'
        self.assertEqual(inventory[key]['sha256'], self.new)
        self.assertEqual(inventory[key]['source_sha256s'], [self.old])
        self.assertEqual(images[key], file)
        file.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'JPEG changed'):
            rewrite_inventory(source, self.mappings, self.root, 'verification')

    def test_lineage_tracks_new_files_and_preserves_source_provenance(self):
        before = {'assignments': {'product': {'file': 'media/wands-expanded/' + self.old + '.jpg', 'sha256': self.old}},
                  'excluded_disabled_skus': ['disabled']}
        after = rewrite_lineage(before, self.mappings)
        row = after['assignments']['product']
        self.assertEqual(row['file'], 'media/wands-expanded/' + self.new + '.jpg')
        self.assertEqual(row['source_sha256'], self.old)
        self.assertEqual(after['excluded_disabled_skus'], ['disabled'])
        row['sha256'] = 'bad'
        row['file'] = 'media/wands-expanded/' + self.old + '.jpg'
        with self.assertRaisesRegex(ValueError, 'lineage disagrees'):
            rewrite_lineage(after, self.mappings)

    def test_role_references_include_native_qa_thumbnail_image(self):
        media = self.csv('media.csv', [self.media_row(self.new)])
        qa = self.csv('qa.csv', [{'sku': 'qa', 'thumbnail_image': '/wands-qa/qa.jpg'}])
        files = {'media/wands-expanded/' + self.new + '.jpg': self.root / 'unused',
                 'media/wands-qa/qa.jpg': self.root / 'unused'}
        data = {'data/4-media.csv': media, 'data/6-qa.csv': qa}
        self.assertEqual(check_references(data, files), {'media_assignments': 2, 'media_roles': 4})
        files.pop('media/wands-qa/qa.jpg')
        with self.assertRaisesRegex(ValueError, 'missing release media'):
            check_references(data, files)

    def test_extraction_copies_only_explicit_declared_public_members(self):
        artifact = write_archive(self.root / 'baseline.tar', {'data/public.csv': b'public', 'private.txt': b'excluded'})
        files = extract_subset(self.root, {'artifacts': [artifact]}, self.root / 'stage', lambda n: n.startswith('data/'))
        self.assertEqual(set(files), {'data/public.csv'})
        self.assertFalse((self.root / 'stage/private.txt').exists())
        self.assertEqual(files['data/public.csv'].read_bytes(), b'public')


if __name__ == '__main__':
    unittest.main()
