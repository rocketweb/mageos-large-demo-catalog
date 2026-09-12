import json
from pathlib import Path
import subprocess
import unittest

PHP=Path('/opt/homebrew/Cellar/php@8.4/8.4.24/bin/php')
HELPER=Path(__file__).resolve().parents[1]/'prepare_local_theme_fixture.php'


class ThemeFixtureDdlTest(unittest.TestCase):
    @unittest.skipUnless(PHP.is_file(),'Local PHP unavailable')
    def test_native_types_and_forbidden_reference(self):
        code=r'''
require $argv[1];
class Quoter {public function quoteIdentifier($v){return '`'.$v.'`';}public function quote($v){return "'".$v."'";}}
$xml='<table xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" name="theme"><column xsi:type="int" name="theme_id" unsigned="true" nullable="false" identity="true"/><column xsi:type="boolean" name="is_featured" default="false"/><constraint xsi:type="primary"><column name="theme_id"/></constraint></table>';
$sql=localThemeDdl(simplexml_load_string($xml),new Quoter());
$bad='<table xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" name="theme"><constraint xsi:type="foreign" referenceTable="customer_entity"/></table>';
try {localThemeDdl(simplexml_load_string($bad),new Quoter());$rejected=false;}catch(RuntimeException $e){$rejected=true;}
echo json_encode([$sql,$rejected]);
'''
        result=subprocess.run([str(PHP),'-r',code,str(HELPER)],capture_output=True,text=True,check=True)
        sql,rejected=json.loads(result.stdout)
        self.assertIn('`theme_id` INT UNSIGNED NOT NULL AUTO_INCREMENT',sql)
        self.assertIn("`is_featured` TINYINT(1) NULL DEFAULT '0'",sql)
        self.assertIn('PRIMARY KEY (`theme_id`)',sql)
        self.assertTrue(rejected)
