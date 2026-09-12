import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_bulk_completion import image_case
from generate_reference_images import fingerprint
from prepare_catalog import sha256
from prepare_bulk_import import preserve_urls
from run_bulk_completion_images import CONFIG, pending
from test_reconcile_catalog_media import fixture


class BulkCompletionTest(unittest.TestCase):
    def test_native_updates_preserve_existing_urls_and_reject_missing_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory)
            (snapshot/'eav_attribute.jsonl').write_text(json.dumps({'attribute_id': 12, 'attribute_code': 'url_key'})+'\n')
            (snapshot/'catalog_product_entity.jsonl').write_text(json.dumps({'sku': 'WANDS-000001', 'entity_id': 1})+'\n')
            value = {'entity_id': 1, 'attribute_id': 12, 'store_id': 0, 'value': 'original-product-url'}
            (snapshot/'catalog_product_entity_varchar.jsonl').write_text(json.dumps(value)+'\n')
            rows = preserve_urls([{'sku': 'WANDS-000001', 'name': 'New synthetic name'}], snapshot)
            self.assertEqual(rows[0]['url_key'], 'original-product-url')
            value['store_id'] = 2
            (snapshot/'catalog_product_entity_varchar.jsonl').write_text(json.dumps(value)+'\n')
            with self.assertRaisesRegex(ValueError, 'URL key missing'):
                preserve_urls([{'sku': 'WANDS-000001'}], snapshot)

    def test_every_variant_gets_its_current_definition_not_historical_sku_options(self):
        root, children, _ = fixture()
        original = copy.deepcopy(root)
        cases = [image_case(root, child) for child in children]
        self.assertEqual(len({case['output_file'] for case in cases}), len(children))
        self.assertEqual(root, original)
        for case, child in zip(cases, children):
            self.assertEqual(case['contract']['selected_options'], child['variant_options'])
            self.assertIn(child['variant_options']['wands_finish'], case['prompt'])
            self.assertNotIn('Selected: Walnut', case['prompt'])
            self.assertNotIn('reference_images', case)

    def test_simple_conversion_generates_root_not_disabled_children(self):
        root, children, _ = fixture('WANDS-003817', {'wands_size': ['Toddler', 'Twin', 'Full', 'Queen']})
        case = image_case(root, root)
        self.assertEqual(case['sku'], root['sku'])
        self.assertEqual(case['contract']['selected_options'], {})
        self.assertIn('No crib', case['prompt'])

    def test_resume_requires_matching_job_and_image_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory)
            events = media/'events.jsonl'
            job = {'sku': 'WANDS-000001', 'output_file': 'one.jpg', 'prompt': 'one chair', 'seed': 1}
            self.assertEqual(pending([job], media, events), [job])
            image = media/'one.jpg'
            image.write_bytes(b'image fixture')
            with self.assertRaisesRegex(ValueError, 'Untracked'):
                pending([job], media, events)
            events.write_text(json.dumps({'status': 'generated', 'output_file': 'one.jpg', 'request_sha256': fingerprint(job, CONFIG), 'image_sha256': sha256(image)})+'\n')
            self.assertEqual(pending([job], media, events), [])
            image.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'changed'):
                pending([job], media, events)

    def test_reject_duplicate_and_escaping_destinations(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory)
            job = {'output_file': 'one.jpg'}
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                pending([job, job], media, media/'events.jsonl')
            with self.assertRaises(ValueError):
                pending([{'output_file': '../one.jpg'}], media, media/'events.jsonl')
