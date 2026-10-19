import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import catalog_exclusions as exclusions


class CatalogExclusionsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.job = self.root / 'job';self.job.mkdir()
        self.source = self.root / 'source';self.source.mkdir()
        self.selection = self.root / 'selection';self.selection.mkdir()
        self.media = self.selection / 'selected-media/wands-expanded';self.media.mkdir(parents=True)
        (self.media / 'good.jpg').write_bytes(b'retained image')
        self.fields = ['sku', 'name', 'product_type', 'related_skus', 'base_image']
        rows = [{'sku': 'WANDS-1', 'name': 'Table', 'product_type': 'simple', 'related_skus': 'WANDS-2,WANDS-3'},
                {'sku': 'WANDS-2', 'name': 'Star Wars light', 'product_type': 'simple'},
                {'sku': 'WANDS-3', 'name': 'R2-D2 bag', 'product_type': 'simple'}]
        for name in ['1-simple.csv', '2-configurable.csv', '3-bundle.csv', '4-media.csv', '5-merchandising.csv', '6-qa.csv']:
            self.csv(self.source / name, rows if name == '1-simple.csv' else [])
        self.csv(self.selection / 'media.csv', [{'sku': 'WANDS-1', 'base_image': '/wands-expanded/good.jpg'},
                                                {'sku': 'WANDS-2', 'base_image': '/wands-expanded/removed.jpg'}])
        self.policy = self.root / 'policy.json';self.policy.write_text(json.dumps({'products': exclusions.discover(self.source)}))
        self.config = {'policy': str(self.policy), 'policy_sha256': exclusions.sha(self.policy),
                       'source_data': str(self.source), 'source_hashes': {p.name: exclusions.sha(p) for p in self.source.iterdir()},
                       'qa_media': str(self.root / 'qa')}
        (self.job / 'catalog-exclusions.json').write_text(json.dumps(self.config))
        self.verification = self.selection / 'verification.json'
        self.verification.write_text(json.dumps({'media_csv_sha256': exclusions.sha(self.selection / 'media.csv')}))
        self.latest = {'verification': str(self.verification), 'verification_sha256': exclusions.sha(self.verification),
                       'media_csv': str(self.selection / 'media.csv'), 'media': str(self.media)}

    def csv(self, path, rows):
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=self.fields);writer.writeheader();writer.writerows(rows)

    def test_products_assignments_and_links_removed_without_changing_sources(self):
        result = exclusions.refresh(self.job, self.root, self.latest)
        self.assertEqual(result['counts']['products'], 1)
        self.assertEqual(result['counts']['excluded_products'], 2)
        self.assertEqual(result['changes']['1-simple.csv']['pruned_links'], 2)
        with (Path(result['data']) / '1-simple.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([r['sku'] for r in rows], ['WANDS-1'])
        self.assertEqual(rows[0]['related_skus'], '')
        with (Path(result['data']) / '4-media.csv').open() as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 1)
        self.assertEqual(exclusions.refresh(self.job, self.root, self.latest), result)
        for name, expected in self.config['source_hashes'].items():
            self.assertEqual(exclusions.sha(self.source / name), expected)

    def test_changed_exclusion_scope_cannot_replace_current_catalog(self):
        self.policy.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'approval changed'):
            exclusions.refresh(self.job, self.root, self.latest)
        self.assertFalse((self.job / 'local-catalog.json').exists())

    def test_changed_baseline_cannot_replace_current_catalog(self):
        (self.source / '1-simple.csv').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            exclusions.refresh(self.job, self.root, self.latest)

    def test_missing_retained_image_cannot_become_current(self):
        (self.media / 'good.jpg').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing catalog media'):
            exclusions.refresh(self.job, self.root, self.latest)
        self.assertFalse((self.job / 'local-catalog.json').exists())

    def test_bundle_reference_removed_and_remaining_choice_becomes_default(self):
        value = 'name=Decor,type=dropdown,required=1,sku=WANDS-2,default=1|name=Decor,type=dropdown,required=1,sku=WANDS-1,default=0'
        value, removed = exclusions.prune_bundle(value, {'WANDS-2'})
        self.assertEqual(removed, 1)
        self.assertEqual(value, 'name=Decor,type=dropdown,required=1,sku=WANDS-1,default=1')
        with self.assertRaisesRegex(ValueError, 'no retained products'):
            exclusions.prune_bundle(value, {'WANDS-1'})

    def test_renaming_refreshes_current_export_and_retains_previous_artifact(self):
        path = self.source / '1-simple.csv'
        path.write_text(path.read_text().replace('Table', 'Disney Table'))
        options = self.source / 'attribute-options.json'
        options.write_text(json.dumps({'brands': ['Disney', 'DISNEY', 'disney']}))
        self.config['source_hashes'].update({p.name: exclusions.sha(p) for p in [path, options]})
        (self.job / 'catalog-exclusions.json').write_text(json.dumps(self.config))
        previous = exclusions.refresh(self.job, self.root, self.latest)
        text_policy = self.root / 'rename.json'
        text_policy.write_text(json.dumps({'replacements': [{'from': 'Disney', 'to': 'Datney'}]}))
        self.config.update(text_policy=str(text_policy), text_policy_sha256=exclusions.sha(text_policy))
        (self.job / 'catalog-exclusions.json').write_text(json.dumps(self.config))
        current = exclusions.refresh(self.job, self.root, self.latest)
        self.assertNotEqual(previous['data'], current['data'])
        self.assertIn('Disney Table', (Path(previous['data']) / '1-simple.csv').read_text())
        self.assertIn('Datney Table', (Path(current['data']) / '1-simple.csv').read_text())
        self.assertEqual(json.loads((Path(current['data']) / 'attribute-options.json').read_text()), {'brands': ['Datney', 'DATNEY', 'datney']})
        self.assertEqual(current['text_replacements'], 4)


if __name__ == '__main__':
    unittest.main()
