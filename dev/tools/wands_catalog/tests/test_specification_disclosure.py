import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('WANDS_TEST_PHP'), 'Set WANDS_TEST_PHP to PHP 8.4')
class SpecificationDisclosureTest(unittest.TestCase):
    def test_patch_adds_visible_notice_is_idempotent_and_rejects_conflicts(self):
        patch = Path(__file__).resolve().parents[4]/'app/code/RocketWeb/LabCatalog/Setup/Patch/Data/AddSpecificationDisclosure.php'
        fixture=r'''<?php
namespace Magento\Framework\Setup\Patch { interface DataPatchInterface {} }
namespace Magento\Framework\Setup { interface ModuleDataSetupInterface {} }
namespace Magento\Catalog\Model { class Product { const ENTITY='catalog_product'; } }
namespace Magento\Eav\Model\Entity\Attribute { class ScopedAttributeInterface { const SCOPE_GLOBAL=1; } }
namespace Magento\Eav\Setup { class EavSetupFactory {
    public function __construct(public $setup) {}
    public function create($args) { return $this->setup; }
} }
namespace {
    class Connection { public $started=0; public $ended=0;
        public function startSetup() { $this->started++; }
        public function endSetup() { $this->ended++; }
    }
    class ModuleSetup implements \Magento\Framework\Setup\ModuleDataSetupInterface {
        public $connection;
        public function __construct() { $this->connection=new Connection; }
        public function getConnection() { return $this->connection; }
    }
    class Eav { public $existing=[]; public $added=[];
        public function getAttribute($entity,$code) { return $this->existing; }
        public function addAttribute($entity,$code,$config) { $this->added=[$code,$config]; }
    }
    require $argv[1];
    $module=new ModuleSetup; $eav=new Eav;
    $patch=new \RocketWeb\LabCatalog\Setup\Patch\Data\AddSpecificationDisclosure(
        $module,new \Magento\Eav\Setup\EavSetupFactory($eav));
    $patch->apply();
    if ($eav->added[0]!=='lab_spec_disclosure' || !$eav->added[1]['visible_on_front']
        || !$eav->added[1]['comparable'] || $eav->added[1]['searchable']
        || $module->connection->started!==1 || $module->connection->ended!==1) {
        throw new \RuntimeException('Disclosure setup differs');
    }
    $eav->existing=['attribute_id'=>1,'backend_type'=>'text','frontend_input'=>'textarea'];
    $eav->added=[]; $patch->apply();
    if ($eav->added!==[]) { throw new \RuntimeException('Existing attribute changed'); }
    $eav->existing['backend_type']='varchar';
    try { $patch->apply(); } catch (\RuntimeException $error) { echo 'passed'; exit(0); }
    throw new \RuntimeException('Conflict accepted');
}
'''
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory)/'check.php';script.write_text(fixture)
            result=subprocess.run([os.environ['WANDS_TEST_PHP'],str(script),str(patch)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'passed')

    def test_attribute_option_check_accepts_depth_and_rejects_unknown_options(self):
        tool=Path(__file__).resolve().parents[1]/'distribution/test_attribute_options.php'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'options.json'
            for value,code in [('Modern',0),('Imaginary Unknown Style',255)]:
                path.write_text(json.dumps({'lab_spec_style':[value]}))
                result=subprocess.run([os.environ['WANDS_TEST_PHP'],str(tool),str(path)],capture_output=True,text=True)
                self.assertEqual(result.returncode,code,result.stderr)


if __name__=='__main__':
    unittest.main()
