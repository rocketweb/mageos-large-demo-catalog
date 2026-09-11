import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_mageos_rehearsal import build

PHP=Path('/opt/homebrew/Cellar/php@8.4/8.4.24/bin/php')


class IsolatedRootTest(unittest.TestCase):
    @unittest.skipUnless(PHP.is_file(),'Local PHP unavailable')
    def test_magento_host_format_and_no_source_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';out=Path(tmp)/'isolated'
            (source/'app/etc').mkdir(parents=True);(source/'vendor').mkdir()
            (source/'composer.lock').write_text(json.dumps({'packages':[{'name':'mage-os/product-community-edition','version':'3.5.0'}]}))
            for f in ('vendor/autoload.php','app/bootstrap.php','app/autoload.php','app/etc/di.xml','app/etc/vendor_path.php'):(source/f).write_text('<?php // fixture')
            (source/'app/etc/config.php').write_text('<?php return ["modules"=>["Magento_Catalog"=>1],"system"=>["secret"=>"do-not-copy"]];')
            (source/'app/etc/env.php').write_text('SOURCE-CREDENTIALS-MUST-NOT-BE-READ')
            build(argparse.Namespace(source=source,output_dir=out,database='wands_rehearsal_test',php=str(PHP)))
            env=json.loads(subprocess.run([str(PHP),'-r','echo json_encode(require $argv[1]);',str(out/'app/etc/env.php')],check=True,capture_output=True,text=True).stdout)
            self.assertEqual(env['db']['connection']['default']['host'],'127.0.0.1:13380')
            self.assertNotIn('port',env['db']['connection']['default'])
            self.assertNotIn('do-not-copy',(out/'app/etc/config.php').read_text())
            self.assertNotIn('SOURCE-CREDENTIALS',(out/'app/etc/env.php').read_text())
            self.assertEqual((out/'vendor').resolve(),(source/'vendor').resolve())
