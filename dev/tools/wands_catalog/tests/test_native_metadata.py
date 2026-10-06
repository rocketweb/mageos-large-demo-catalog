import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from native_metadata import normalize
class MetadataTest(unittest.TestCase):
    def test_final_variant_substitution_is_bounded_without_truncating_descriptions(self):
        rows={'SKU':{'meta_description':'x'*257,'description':'x'*3000,'name':'valid'}}
        changes=normalize(rows)
        self.assertEqual(len(rows['SKU']['meta_description']),255)
        self.assertEqual(len(rows['SKU']['description']),3000)
        self.assertEqual(changes[0]['characters_removed'],2)
        self.assertEqual(normalize(rows),[])
    def test_unicode_limit_is_in_characters(self):
        rows={'SKU':{'meta_title':'é'*256}};normalize(rows)
        self.assertEqual(rows['SKU']['meta_title'],'é'*255)

class MediaLabelTest(unittest.TestCase):
    def test_annotation_disclosure_fits_with_long_product_name(self):
        import native_metadata
        label=native_metadata.media_label('é'*255)
        self.assertLessEqual(len(label),255)
        self.assertTrue(label.endswith('(synthetic illustration; no displayed measurements)'))
