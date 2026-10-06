import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_expansion_update import prepare


class ExistingContentTest(unittest.TestCase):
    def test_comtom_refreshes_legacy_simple_content_as_well_as_changed_parents(self):
        # The real destination retained 164.99 while its approved export says
        # 69.99. Importing only changed parents cannot align an existing simple.
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);candidate=root/'candidate';candidate.mkdir()
            (candidate/'manifest.json').write_text(json.dumps({'outputs':{}}))
            desired=[{'sku':'WANDS-'+str(i).zfill(6),'product_type':'simple','price':'69.99'} for i in range(107688)]
            current={r['sku']:{'wands':True,'type':'simple'} for r in desired[:53844]}
            snapshot=root/'store.json';snapshot.write_text(json.dumps({'root':'/var/www/html','database_writes':False,
                'shared_wands_skus':[],'products':current,'other_products':1200,'protected':{},'website_id':2,'store_id':2}))
            def rows(path):return desired if path.name=='1-simple.csv' else []
            with patch('prepare_expansion_update.csv_rows',side_effect=rows):
                result=prepare(candidate,snapshot,root/'delta')
            self.assertEqual(result['existing_content_updates'],53844)
            self.assertTrue((root/'delta/existing-simple.csv').is_file())
            self.assertIn('WANDS-000001',(root/'delta/existing-simple.csv').read_text())
            self.assertEqual(result['products_deleted'],0)
            self.assertEqual(result['unrelated_products_preserved'],1200)
