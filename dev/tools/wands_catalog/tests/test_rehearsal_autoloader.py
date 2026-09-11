import json
from pathlib import Path
import subprocess
import tempfile
import unittest

PHP=Path('/opt/homebrew/Cellar/php@8.4/8.4.24/bin/php')
COMPOSER=Path('/Users/matt/code/mageos-latest/vendor/composer/ClassLoader.php')
HELPER=Path(__file__).resolve().parents[1]/'isolate_rehearsal_autoloader.php'


class AutoloaderIsolationTest(unittest.TestCase):
    @unittest.skipUnless(PHP.is_file() and COMPOSER.is_file(),'Installed PHP/Composer unavailable')
    def test_generated_fallbacks_and_classmap_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';root=Path(tmp)/'isolated'
            for base in (source/'generated/code',source/'vendor/example',root/'generated/code'):
                base.mkdir(parents=True)
            (source/'generated/code/Stale.php').write_text('<?php class Stale {}')
            (source/'vendor/example/Library.php').write_text('<?php class Library {}')
            (root/'generated/code/Fresh.php').write_text('<?php class Fresh {}')
            code=r'''
require $argv[1];require $argv[2];$source=$argv[3];$root=$argv[4];
$old=new Composer\Autoload\ClassLoader();
$old->add('',[$source.'/vendor/../generated/code',$source.'/vendor/example']);
$old->addPsr4('',[$source.'/generated/code']);
$old->addPsr4('Bad\\',[$source.'/generated/code']);
$old->addClassMap(['Stale'=>$source.'/generated/code/Stale.php']);$old->register();
$new=isolateRehearsalAutoloader($old,$source,$root);
echo json_encode([$new->findFile('Stale'),$new->findFile('Fresh'),$new->findFile('Library'),$new->getClassMap(),$new->getPrefixesPsr4()]);
'''
            result=subprocess.run([str(PHP),'-r',code,str(COMPOSER),str(HELPER),str(source),str(root)],capture_output=True,text=True,check=True)
            actual=json.loads(result.stdout)
            self.assertFalse(actual[0])
            self.assertEqual(actual[1],str(root/'generated/code/Fresh.php'))
            self.assertEqual(actual[2],str(source/'vendor/example/Library.php'))
            self.assertEqual(actual[3],[])
            self.assertEqual(actual[4],{'Bad\\':[]})
