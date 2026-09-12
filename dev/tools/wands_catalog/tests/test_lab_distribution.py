import hashlib
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'distribution'))
from release import closure, dependencies, write_archive, verify_release


class DistributionTest(unittest.TestCase):
    def test_dependency_closure_includes_entire_family_and_bundle(self):
        rows = {
            'parent': {'product_type': 'configurable', 'configurable_variations': 'sku=a,color=Blue|sku=b,color=Red'},
            'a': {'product_type': 'simple'}, 'b': {'product_type': 'simple'},
            'bundle': {'product_type': 'bundle', 'bundle_values': 'name=Chair,sku=a|name=Table,sku=c'},
            'c': {'product_type': 'simple'},
        }
        self.assertEqual(closure(rows, ['bundle']), {'bundle', 'a', 'b', 'c', 'parent'})
        del rows['c']
        with self.assertRaisesRegex(ValueError, 'Missing dependency'):
            closure(rows, ['bundle'])

    def test_archive_is_reproducible_and_verifies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {'data/example.json': b'{"hello": 1}\n'}
            first = write_archive(root / 'one.tar', files)
            second = write_archive(root / 'two.tar', files)
            self.assertEqual(first['sha256'], second['sha256'])
            manifest = {'schema': 1, 'artifacts': [first]}
            data = json.dumps(manifest).encode()
            (root / 'manifest.json').write_bytes(data)
            pin = hashlib.sha256(data).hexdigest()
            self.assertEqual(verify_release(root, pin)['files'], 1)
            with self.assertRaisesRegex(ValueError, 'manifest'):
                verify_release(root, '0' * 64)
            (root / 'one.tar').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                verify_release(root, pin)

    def test_rejects_traversal_symlinks_duplicates_and_undeclared_members(self):
        for kind in ['traversal', 'symlink', 'duplicate', 'undeclared']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                name = '../escape' if kind == 'traversal' else 'data/file.txt'
                with tarfile.open(root / 'bad.tar', 'w') as archive:
                    member = tarfile.TarInfo(name)
                    member.size = 1
                    if kind == 'symlink':
                        member.type = tarfile.SYMTYPE
                        member.linkname = '/etc/passwd'
                        member.size = 0
                    archive.addfile(member, io.BytesIO(b'x'))
                    if kind == 'duplicate':
                        archive.addfile(member, io.BytesIO(b'x'))
                content = (root / 'bad.tar').read_bytes()
                item = {'path': 'bad.tar', 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
                        'unpacked_bytes': 1, 'files': {} if kind == 'undeclared' else {name: {'bytes': 1, 'sha256': hashlib.sha256(b'x').hexdigest()}}}
                data = json.dumps({'schema': 1, 'artifacts': [item]}).encode()
                (root / 'manifest.json').write_bytes(data)
                with self.assertRaises(ValueError):
                    verify_release(root, hashlib.sha256(data).hexdigest())


    @unittest.skipUnless(os.environ.get('WANDS_TEST_PHP'), 'Set WANDS_TEST_PHP to the intended native PHP binary')
    def test_empty_destination_passes_and_collisions_fail_without_writes(self):
        bootstrap = '''<?php
namespace Magento\\Framework\\App;
define('BP', __DIR__);
class Bootstrap {
    public static function create($root, $server) { return new self; }
    public function getObjectManager() { return $this; }
    public function get($class) { return new ResourceConnection; }
}
class ResourceConnection {
    public function getConnection() { return new ReadOnlyConnection; }
    public function getTableName($table) { return $table; }
}
class ReadOnlyConnection {
    private $index = 0;
    public function select() { return $this; }
    public function from($table, $columns) { return $this; }
    public function where($condition, $value) { return $this; }
    public function fetchOne($query) { return explode(',', getenv('WANDS_TEST_COUNTS'))[$this->index++]; }
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'app').mkdir()
            (root / 'app/bootstrap.php').write_text(bootstrap)
            data = root / 'data'
            data.mkdir()
            (data / 'counts.json').write_text(json.dumps({'products': 1, 'media_roles': 3}))
            for index, kind in enumerate(['simple', 'configurable', 'bundle'], 1):
                (data / f'{index}-{kind}.csv').write_text('sku\n' + ('example\n' if index == 1 else ''))
            for counts in ['0,0,0,0', '7,0,0,0', '0,1,0,0', '0,0,1,0', '0,0,0,1']:
                log = root / f'{counts}.log'
                result = subprocess.run([os.environ['WANDS_TEST_PHP'],
                    str(Path(__file__).resolve().parents[1] / 'distribution/preflight.php'),
                    '--magento-root=' + str(root), '--data-dir=' + str(data), '--log-file=' + str(log)],
                    env={**os.environ, 'WANDS_TEST_COUNTS': counts}, capture_output=True, text=True)
                with self.subTest(counts=counts):
                    self.assertEqual(result.returncode, 0 if counts == '0,0,0,0' else 1)
                    self.assertEqual(result.stdout + result.stderr, '')
                    self.assertIn('"database_writes": false', log.read_text())

    @unittest.skipUnless(os.environ.get('WANDS_TEST_PHP'), 'Set WANDS_TEST_PHP to the intended native PHP binary')
    def test_missing_preflight_inputs_fail_quietly_before_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'app').mkdir()
            (root / 'app/bootstrap.php').write_text('<?php throw new RuntimeException("BOOTSTRAP_CALLED");')
            data = root / 'data'
            data.mkdir()
            for missing in ['counts.json', '1-simple.csv']:
                if missing == '1-simple.csv':
                    (data / 'counts.json').write_text('{"products": 1, "media_roles": 3}')
                log = root / (missing + '.log')
                result = subprocess.run([os.environ['WANDS_TEST_PHP'],
                    str(Path(__file__).resolve().parents[1] / 'distribution/preflight.php'),
                    '--magento-root=' + str(root), '--data-dir=' + str(data), '--log-file=' + str(log)],
                    capture_output=True, text=True)
                with self.subTest(missing=missing):
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout + result.stderr, '')
                    self.assertIn('FAILED:', log.read_text())
                    self.assertNotIn('BOOTSTRAP_CALLED', log.read_text())

    def test_archive_writer_rejects_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ['../secret', '/absolute', 'a/../b', 'a\\b']:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    write_archive(Path(directory) / 'bad.tar', {name: b'x'})

    def test_extract_only_to_new_directory_and_reject_missing_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = write_archive(root / 'catalog.tar', {'data/item.csv': b'sku\nexample\n'})
            data = json.dumps({'schema': 1, 'artifacts': [artifact]}).encode()
            (root / 'manifest.json').write_bytes(data)
            pin = hashlib.sha256(data).hexdigest()
            output = root / 'staging'
            verify_release(root, pin, output)
            self.assertEqual((output / 'data/item.csv').read_bytes(), b'sku\nexample\n')
            with self.assertRaises(FileExistsError):
                verify_release(root, pin, output)
            (root / 'catalog.tar').unlink()
            with self.assertRaisesRegex(ValueError, 'checksum'):
                verify_release(root, pin)

    def test_corrupt_member_hash_and_duplicate_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = write_archive(root / 'catalog.tar', {'data/item.csv': b'sku\nexample\n'})
            original = artifact['files']['data/item.csv']['sha256']
            for case in ['member', 'artifact']:
                artifact['files']['data/item.csv']['sha256'] = '0' * 64 if case == 'member' else original
                data = json.dumps({'schema': 1, 'artifacts': [artifact] * (2 if case == 'artifact' else 1)}).encode()
                (root / 'manifest.json').write_bytes(data)
                with self.subTest(case=case), self.assertRaises(ValueError):
                    verify_release(root, hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    unittest.main()
