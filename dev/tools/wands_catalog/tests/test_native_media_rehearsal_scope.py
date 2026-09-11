from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_native_media_rehearsal import validate_fields


class NativeMediaScopeTest(unittest.TestCase):
    def fixture(self):
        fields={'sku':'WANDS-000056','store_view_code':''}
        for role in ('base_image','small_image','thumbnail'):
            fields[role]='/wands/pilot-media-v1/example.jpg';fields[role+'_label']='Example - synthetic lab assortment'
        return {'target_sku':'WANDS-000056','image':{'file':'example.jpg'},'fields':fields}

    def test_exact_media_columns_and_destination(self):
        self.assertEqual(validate_fields(self.fixture()),'pub/media/import/wands/pilot-media-v1/example.jpg')

    def test_extra_price_path_escape_or_parent_assignment_rejected(self):
        row=self.fixture();row['fields']['price']='1'
        with self.assertRaises(ValueError):validate_fields(row)
        row=self.fixture();row['image']['file']='../../example.jpg'
        with self.assertRaises(ValueError):validate_fields(row)
        row=self.fixture();row['target_sku']=row['fields']['sku']='WANDS-030335'
        with self.assertRaises(ValueError):validate_fields(row)
        row=self.fixture();row['fields']['thumbnail']='/other/file.jpg'
        with self.assertRaises(ValueError):validate_fields(row)
