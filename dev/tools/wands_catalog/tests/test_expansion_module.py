import json
import re
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import expansion_module as module


class ModuleInverseTest(unittest.TestCase):
    def test_importer_constructor_dependencies_ship_with_the_module_update(self):
        source=Path(__file__).resolve().parents[4]/'app/code/RocketWeb/LabCatalog'
        constructor=(source/'Model/Catalog/ProductImporter.php').read_text().split('public function __construct(',1)[1].split(') {',1)[0]
        for kind in re.findall(r'private readonly ([\\\w]+) \$',constructor):
            name='Model/Catalog/'+kind.rsplit('\\',1)[-1]+'.php'
            if (source/name).is_file():self.assertIn(name,module.FILES)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.live=self.root/'app/code/RocketWeb/LabCatalog'
        self.live.mkdir(parents=True);(self.live/'registration.php').write_text('existing')
        self.source=self.root/'reviewed';self.source.mkdir();self.stage=self.root/'var/stage'
        for name in module.FILES:
            p=self.source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('new '+name)
        p=self.live/module.FILES[0];p.parent.mkdir(parents=True);p.write_text('original')
        (self.live/'unrelated.php').write_text('user work')
        self.allow=patch.object(module,'ROOTS',{str(self.root)});self.allow.start();self.addCleanup(self.allow.stop)
        self.receipt=module.prepare(self.root,self.source,self.stage)

    def test_apply_and_exact_inverse_preserve_unrelated_work(self):
        module.apply(self.root,self.stage,self.receipt['manifest_sha256'])
        self.assertEqual((self.live/module.FILES[0]).read_text(),'new '+module.FILES[0])
        module.apply(self.root,self.stage,self.receipt['manifest_sha256'],reverse=True)
        self.assertEqual((self.live/module.FILES[0]).read_text(),'original')
        self.assertFalse((self.live/module.FILES[1]).exists())
        self.assertEqual((self.live/'unrelated.php').read_text(),'user work')

    def test_later_user_edit_aborts_before_changing_any_module_file(self):
        (self.live/module.FILES[0]).write_text('later edit')
        with self.assertRaisesRegex(ValueError,'drifted'):
            module.apply(self.root,self.stage,self.receipt['manifest_sha256'])
        self.assertFalse((self.live/module.FILES[1]).exists())

    def test_tampered_source_aborts_before_module_changes(self):
        (self.stage/'after'/module.FILES[-1]).write_text('changed')
        with self.assertRaisesRegex(ValueError,'Staged module'):
            module.apply(self.root,self.stage,self.receipt['manifest_sha256'])
        self.assertEqual((self.live/module.FILES[0]).read_text(),'original')

    def test_inverse_refuses_to_overwrite_later_user_work(self):
        module.apply(self.root,self.stage,self.receipt['manifest_sha256'])
        (self.live/module.FILES[-1]).write_text('later edit')
        with self.assertRaisesRegex(ValueError,'drifted'):
            module.apply(self.root,self.stage,self.receipt['manifest_sha256'],reverse=True)
        self.assertEqual((self.live/module.FILES[0]).read_text(),'new '+module.FILES[0])
