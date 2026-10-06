import hashlib
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import signal
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import finish_expansion_project as finish


class ExpansionFinishTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=self.root/'existing-store';self.store.mkdir()
        self.package=self.root/'accepted';self.package.mkdir()
        self.run=self.root/'run';self.run.mkdir()
        (self.run/'run.json').write_text(json.dumps({'candidate':'/approved-candidate','candidate_sha256':finish.CANDIDATE_SHA256}))

    def test_unfinished_images_never_contact_or_mutate_a_store(self):
        with patch.object(finish,'Destination') as store,patch.object(finish,'verified_export') as verify:
            result=finish.finish(self.run,self.package,self.root/'receipts',apply=True)
        self.assertFalse(result['store_imports_started']);store.assert_not_called();verify.assert_not_called()

    def test_an_invalid_export_cannot_begin_deployment(self):
        (self.package/'manifest.json').write_text('{}')
        with patch.object(finish,'verified_export',side_effect=ValueError('Image acceptance incomplete')),patch.object(finish,'Destination') as store:
            with self.assertRaisesRegex(ValueError,'acceptance'):finish.finish(self.run,self.package,self.root/'receipts',apply=True)
        store.assert_not_called()

    def test_no_third_installation_is_accepted(self):
        with self.assertRaises(ValueError):finish.Destination(self.root/'third-store',self.root,'fixture')
        self.assertFalse((self.root/'third-store').exists())

    def test_stage_images_reuses_immutable_bytes_and_refuses_changed_existing_files(self):
        data=b'approved-image';pin=hashlib.sha256(data).hexdigest();name='media/wands-expanded/'+pin+'.jpg'
        source=self.package/name;source.parent.mkdir(parents=True);source.write_bytes(data)
        manifest={'files':{name:{'sha256':pin}}}
        with patch.object(finish,'LOCAL',self.store):
            self.assertEqual(finish.stage_images(self.package,self.store,manifest),1)
            self.assertEqual(finish.stage_images(self.package,self.store,manifest),1)
            dest=self.store/'pub/media/import/wands-expanded'/source.name
            self.assertEqual(dest.stat().st_ino,source.stat().st_ino)
            dest.unlink();dest.write_bytes(b'user-edit')
            with self.assertRaisesRegex(ValueError,'no overwrite'):finish.stage_images(self.package,self.store,manifest)
            self.assertEqual(dest.read_bytes(),b'user-edit')

    def test_staging_rejects_nested_and_unbound_images(self):
        with patch.object(finish,'LOCAL',self.store):
            for name in ['media/../escape.jpg','media/wands-expanded/nested/file.jpg','media/wands-expanded/wrong.jpg']:
                with self.assertRaises(ValueError):finish.stage_images(self.package,self.store,{'files':{name:{'sha256':'approved'}}})
        self.assertFalse((self.store/'pub/media/import/escape.jpg').exists())

    def test_file_symlinks_never_override_the_accepted_media_contract(self):
        data=b'approved';pin=hashlib.sha256(data).hexdigest();name='media/wands-expanded/'+pin+'.jpg'
        source=self.package/name;source.parent.mkdir(parents=True);source.write_bytes(data)
        dest=self.store/'pub/media/import/wands-expanded'/source.name;dest.parent.mkdir(parents=True);dest.symlink_to(source)
        with patch.object(finish,'LOCAL',self.store),self.assertRaisesRegex(ValueError,'no overwrite'):
            finish.stage_images(self.package,self.store,{'files':{name:{'sha256':pin}}})

    def test_private_evidence_never_becomes_world_readable(self):
        p=self.root/'receipt.json';finish.private_json(p,{'protected_hash':'only hashes'})
        self.assertEqual(p.stat().st_mode&0o077,0)

    def test_only_one_coordinator_can_install_the_same_run(self):
        from bulk_expansion_images import lock
        with lock(self.run,'installation'),patch.object(finish,'Destination') as store:
            with self.assertRaises(BlockingIOError):
                finish.finish(self.run,self.package,self.root/'duplicate-receipts',apply=True)
        store.assert_not_called()

    def test_symlinked_staging_directory_cannot_write_elsewhere(self):
        data=b'approved';pin=hashlib.sha256(data).hexdigest();name='media/wands-expanded/'+pin+'.jpg'
        source=self.package/name;source.parent.mkdir(parents=True);source.write_bytes(data)
        outside=self.root/'unrelated-media';outside.mkdir()
        target=self.store/'pub/media/import/wands-expanded';target.parent.mkdir(parents=True);target.symlink_to(outside)
        with patch.object(finish,'LOCAL',self.store),self.assertRaisesRegex(ValueError,'staging directory'):
            finish.stage_images(self.package,self.store,{'files':{name:{'sha256':pin}}})
        self.assertFalse(list(outside.iterdir()))

    def test_remote_media_transfer_never_overwrites_existing_accepted_files(self):
        target=finish.Destination(finish.REMOTE,self.root,'fixture')
        with patch.object(finish.subprocess,'run') as command:
            command.return_value.returncode=0
            target.sync(self.package,target.root/'pub/media/import/wands-expanded',immutable=True)
        self.assertIn('--ignore-existing',command.call_args.args[0])

    def test_private_remote_stage_is_readable_by_php_before_the_first_snapshot(self):
        target=finish.Destination(finish.REMOTE,self.root,'fixture');owned=False
        def command(args,**kwargs):
            nonlocal owned
            if [str(a) for a in args]==['chown','-R','33:33',str(target.stage)]:owned=True
        def snapshot(name):
            self.assertTrue(owned,'Private staging belongs to root and PHP cannot read the first snapshot tool')
            raise RuntimeError('fixture stops before database writes')
        with patch.object(target,'command',side_effect=command),patch.object(target,'sync'),\
                patch.object(target,'snapshot',side_effect=snapshot),patch.object(finish,'verify_module'):
            with self.assertRaisesRegex(RuntimeError,'fixture stops'):
                finish.complete_store(target,self.package,self.root,self.run,{'files':{}},[])


if __name__=='__main__':unittest.main()

class PrivateStagingTest(unittest.TestCase):
    def test_interrupted_immutable_transfer_resumes_without_accepting_a_partial_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.jpg';source.write_bytes(b'accepted-image-bytes'*30000)
            destination=root/'staged'/'accepted.jpg';destination.parent.mkdir()
            receipts=root/'receipts';receipts.mkdir();target=finish.Destination(finish.REMOTE,receipts,'fixture')
            attempts=0
            def local_rsync(argv,**kwargs):
                nonlocal attempts
                attempts+=1
                # Exercise real rsync interruption and resume, with only the SSH transport removed.
                args=[a for i,a in enumerate(argv) if i not in (argv.index('-e'),argv.index('-e')+1)]
                args[-1]=str(destination);args.insert(1,'--bwlimit=256')
                process=subprocess.Popen(args,**kwargs)
                if attempts==1:
                    deadline=time.monotonic()+5
                    while time.monotonic()<deadline:
                        temporary=list(destination.parent.glob('.accepted.jpg.*'))
                        if temporary and temporary[0].stat().st_size>0:break
                        time.sleep(.01)
                    if process.poll() is None:process.send_signal(signal.SIGINT)
                return subprocess.CompletedProcess(args,process.wait())
            with patch.object(finish.subprocess,'run',side_effect=local_rsync):
                with self.assertRaisesRegex(RuntimeError,'transfer failed'):
                    target.sync(source,destination,immutable=True)
                target.sync(source,destination,immutable=True)
            self.assertEqual(destination.read_bytes(),source.read_bytes())

    def test_local_sync_preserves_private_rollback_recipe_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store=root/'store';store.mkdir();output=root/'receipts';output.mkdir()
            source=root/'inverse.json';finish.private_json(source,{'operation':'inverse'})
            with patch.object(finish,'LOCAL',store):
                target=finish.Destination(store,output,'fixture')
                destination=store/'inverse.json';target.sync(source,destination)
            self.assertEqual(destination.read_bytes(),source.read_bytes())
            self.assertEqual(destination.stat().st_mode&0o777,0o600)
