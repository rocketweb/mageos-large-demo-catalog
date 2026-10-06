import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build_expansion_inverse
from build_expansion_inverse import build
from prepare_catalog import sha256


class ExpansionInverseTest(unittest.TestCase):
    def test_comtom_inverse_uses_container_paths_for_runtime_evidence(self):
        path=Path('/opt/comtom/stores/relevance/src/var/completion/catalog-before')
        self.assertEqual(str(build_expansion_inverse.runtime_path(path,'/var/www/html')),
                         '/var/www/html/var/completion/catalog-before')
        with self.assertRaises(ValueError):
            build_expansion_inverse.runtime_path(Path('/tmp/not-the-store'),'/var/www/html')

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.before=self.root/'before';self.after=self.root/'after'
        self.old=[{'entity_id':'1','sku':'WANDS-ONE','type_id':'simple'}, {'entity_id':'2','sku':'unrelated','type_id':'simple'}]
        self.new=[{**self.old[0],'type_id':'configurable'},self.old[1],{'entity_id':'3','sku':'WANDS-SYN-NEW','type_id':'simple'}]
        self.capture(self.before,self.old);self.capture(self.after,self.new)

    def capture(self,path,rows):
        path.mkdir(mode=0o700);body=b''.join((json.dumps({'selector':{'entity_id':r['entity_id']},'row':r})+'\n').encode() for r in rows)
        file=path/'catalog_product_entity.jsonl.gz'
        with gzip.open(file,'wb') as stream:stream.write(body)
        file.chmod(0o600)
        meta={'root':'/Users/matt/code/mageos-latest','prefix':'','database':'fixture','env_sha256':'env','tool_sha256':'tool',
            'tables':{'catalog_product_entity':{'rows':len(rows),'row_sha256':hashlib.sha256(body).hexdigest(),
                'sha256':sha256(file),'keys':['entity_id'],'columns':['entity_id','sku','type_id']}}}
        (path/'manifest.json').write_text(json.dumps(meta))

    def test_inverse_contains_only_exact_changed_rows(self):
        file=self.root/'inverse.jsonl.gz';receipt=build(self.before,self.after,file)
        with gzip.open(file,'rt') as stream:ops=[json.loads(line) for line in stream]
        self.assertEqual(receipt['operations'],2)
        self.assertEqual([r['selector'] for r in ops],[{'entity_id':'1'},{'entity_id':'3'}])
        self.assertEqual(ops[0]['before'],self.old[0]);self.assertEqual(ops[0]['after'],self.new[0])
        self.assertIsNone(ops[1]['before']);self.assertEqual(ops[1]['after'],self.new[2])
        self.assertEqual(file.stat().st_mode&0o077,0)

    def test_tampered_snapshot_aborts_before_inverse_rows(self):
        (self.after/'catalog_product_entity.jsonl.gz').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Snapshot bytes'):build(self.before,self.after,self.root/'inverse.jsonl.gz')

    def test_credentials_or_schema_change_aborts(self):
        p=self.after/'manifest.json';value=json.loads(p.read_text());value['env_sha256']='changed';p.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'destination'):build(self.before,self.after,self.root/'inverse.jsonl.gz')

    def test_unchanged_rows_need_no_compensation(self):
        for p in self.after.iterdir():p.unlink()
        self.after.rmdir();self.capture(self.after,self.old)
        self.assertEqual(build(self.before,self.after,self.root/'inverse.jsonl.gz')['operations'],0)

    def test_private_mirrored_comtom_evidence_retains_exact_remote_restore_paths(self):
        for path in (self.before,self.after):
            file=path/'manifest.json';value=json.loads(file.read_text());value['root']='/var/www/html';file.write_text(json.dumps(value))
        host=Path('/opt/comtom/stores/relevance/src/var/approved-install')
        receipt=build(self.before,self.after,self.root/'inverse.jsonl.gz',
                      evidence_paths=(host/'catalog-before',host/'catalog-after'))
        self.assertEqual(receipt['before'],'/var/www/html/var/approved-install/catalog-before')
        self.assertEqual(receipt['operations'],2)
        with self.assertRaises(ValueError):
            build(self.before,self.after,self.root/'wrong-inverse.jsonl.gz',
                  evidence_paths=(Path('/tmp/wrong'),host/'catalog-after'))
