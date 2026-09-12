import json
from pathlib import Path
import subprocess
import unittest

PHP=Path('/opt/homebrew/Cellar/php@8.4/8.4.24/bin/php')


class StorefrontScopeTest(unittest.TestCase):
    @unittest.skipUnless(PHP.is_file(),'Local PHP unavailable')
    def test_theme_metadata_does_not_export_other_configuration(self):
        script=Path(__file__).resolve().parents[1]/'snapshot_rehearsal_schema.php'
        config={'path':'design/theme/theme_id','scope':'stores','scope_id':2,'value':'5'}
        cases=[['theme',{}],['theme_file',{'content':'private'}],['design_change',{'store_id':2}],
            ['design_change',{'store_id':3}],['directory_currency_rate',{'currency_from':'USD','currency_to':'USD'}],
            ['core_config_data',config],['core_config_data',{**config,'path':'payment/api_key'}],
            ['core_config_data',{**config,'scope_id':1}],['core_config_data',{**config,'value':'not-a-theme-id'}],
            ['customer_entity',{}]]
        code='require $argv[1];echo json_encode(array_map(fn($r)=>isStorefrontMetadataRow($r[0],$r[1]),json_decode($argv[2],true)));'
        result=subprocess.run([str(PHP),'-r',code,str(script),json.dumps(cases)],check=True,capture_output=True,text=True)
        self.assertEqual(json.loads(result.stdout),[True,False,True,False,True,True,False,False,False,False])
