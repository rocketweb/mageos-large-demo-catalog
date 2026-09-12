import json
from pathlib import Path
import subprocess
import unittest

PHP=Path('/opt/homebrew/Cellar/php@8.4/8.4.24/bin/php')


class PricingIndexScopeTest(unittest.TestCase):
    @unittest.skipUnless(PHP.is_file(),'Local PHP unavailable')
    def test_index_only_allowlist(self):
        script=Path(__file__).resolve().parents[1]/'probe_mageos_pricing.php'
        names=['catalog_product_index_price','catalog_product_index_price_tmp','catalog_product_index_website',
               'cataloginventory_stock_status','catalog_product_entity_decimal','inventory_source_item','sales_order','customer_entity']
        code='require '+json.dumps(str(script))+';echo json_encode(array_map("isRehearsalPriceIndex",json_decode('+json.dumps(json.dumps(names))+',true)));'
        result=subprocess.run([str(PHP),'-r',code],check=True,capture_output=True,text=True)
        self.assertEqual(json.loads(result.stdout),[True]*4+[False]*4)
