import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_medium_catalog import subset_data, csv_bytes, json_bytes


class MediumCatalogTest(unittest.TestCase):
    def fixture(self):
        a={'sku':'A','product_type':'simple','product_online':'1','related_skus':'B,C'}
        b={'sku':'B','product_type':'simple','product_online':'1','related_skus':'A'}
        c={'sku':'C','product_type':'simple','product_online':'1'}
        p={'sku':'P','product_type':'configurable','product_online':'1','configurable_variations':'sku=B,color=White'}
        bundle={'sku':'Z','product_type':'bundle','product_online':'1','bundle_values':'name=Seat,sku=B'}
        data={'data/1-simple.csv':csv_bytes([a,b,c]),'data/2-configurable.csv':csv_bytes([p]),
            'data/3-bundle.csv':csv_bytes([bundle]),'data/4-media.csv':csv_bytes([{'sku':s} for s in 'ABCPZ']),
            'data/media-lineage.json':json_bytes({'assignments':{s:{'file':s+'.jpg','origin':'synthetic'} for s in 'ABCPZ'}}),
            'data/media-inventory.json':json_bytes({s+'.jpg':{'sha256':'f'*64} for s in 'ABCPZ'}),
            'data/specification-provenance.jsonl':b'', 'data/merchandising-provenance.jsonl':b''}
        return data

    def test_medium_prunes_external_links_and_preserves_input(self):
        data=self.fixture();original=copy.deepcopy(data)
        result,counts,names=subset_data(data,['A','B','P','Z'])
        self.assertEqual(counts['products'],4)
        self.assertEqual(counts['configurable_links'],1)
        self.assertEqual(counts['bundle_selections'],1)
        self.assertEqual(names,{'A.jpg','B.jpg','P.jpg','Z.jpg'})
        self.assertNotIn(b'B,C',result['data/1-simple.csv'])
        self.assertEqual(data,original)

    def test_medium_refuses_missing_bundle_dependency(self):
        with self.assertRaises(ValueError):
            subset_data(self.fixture(),['A','P','Z'])

    def test_medium_refuses_enabled_missing_media(self):
        data=self.fixture();data['data/media-lineage.json']=json_bytes({'assignments':{}})
        with self.assertRaisesRegex(ValueError,'no media'):
            subset_data(data,['A','B','P','Z'])


if __name__=='__main__':
    unittest.main()
