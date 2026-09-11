import json
from pathlib import Path
import subprocess
import unittest

PHP=Path('/opt/homebrew/Cellar/php@8.4/8.4.24/bin/php')


class GuestPricingScopeTest(unittest.TestCase):
    @unittest.skipUnless(PHP.is_file(),'Local PHP unavailable')
    def test_only_guest_group_and_tax_metadata(self):
        script=Path(__file__).resolve().parents[1]/'snapshot_rehearsal_schema.php'
        rows=[['customer_group',{'customer_group_id':0}],['customer_group',{'customer_group_id':1}],
              ['customer_entity',{'customer_group_id':0}],['tax_class',{'class_id':2}],
              ['customer_group_excluded_website',{'customer_group_id':'0'}]]
        code='require '+json.dumps(str(script))+';echo json_encode(array_map(fn($r)=>isGuestPricingRow($r[0],$r[1]),json_decode('+json.dumps(json.dumps(rows))+',true)));'
        result=subprocess.run([str(PHP),'-r',code],check=True,capture_output=True,text=True)
        self.assertEqual(json.loads(result.stdout),[True,False,False,True,True])
