import json
from pathlib import Path
import subprocess
import unittest

PHP=Path('/opt/homebrew/Cellar/php@8.4/8.4.24/bin/php')


class CatalogSchemaScopeTest(unittest.TestCase):
    @unittest.skipUnless(PHP.is_file(),'Local PHP runtime unavailable')
    def test_catalog_inventory_is_allowed_but_customer_and_order_data_are_not(self):
        script=Path(__file__).resolve().parents[1]/'snapshot_rehearsal_schema.php'
        names=['catalog_product_entity','cataloginventory_stock_item','eav_attribute','store','inventory_source_item',
               'sales_order','quote','customer_entity','core_config_data','store_secret']
        code='require '+json.dumps(str(script))+'; echo json_encode(array_map("isCatalogRehearsalTable",json_decode('+json.dumps(json.dumps(names))+',true)));'
        result=subprocess.run([str(PHP),'-r',code],check=True,capture_output=True,text=True)
        self.assertEqual(json.loads(result.stdout),[True]*5+[False]*5)
