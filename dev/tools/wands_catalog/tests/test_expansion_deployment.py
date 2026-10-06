"""Deployment preparation rejects incomplete or changed image artifacts."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import sqlite3
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_expansion_deployment as deployment
from prepare_catalog import sha256


class ExportContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.candidate = self.root / 'candidate'
        self.package = self.root / 'accepted-export'
        (self.candidate / 'data').mkdir(parents=True)
        (self.package / 'data').mkdir(parents=True)
        (self.candidate / 'manifest.json').write_text('{"outputs": {}}')
        self.pin = sha256(self.candidate / 'manifest.json')
        patcher = patch.object(deployment, 'CANDIDATE_SHA256', self.pin)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ('1-simple.csv', '2-configurable.csv', '3-bundle.csv'):
            (self.candidate / 'data' / name).write_text('sku\n')
            (self.package / 'data' / name).write_text('sku\n')
        for name in ('4-media.csv', 'media-lineage.json', 'attribute-options.json'):
            (self.package / 'data' / name).write_text('{}')
        (self.package / 'visual-acceptance.json').write_text(json.dumps({
            'ready': True, 'pilot_accepted': True, 'accepted_new_images': 48844,
            'unresolved_new_images': {}, 'unresolved_retained_briefs': 0,
            'retained_conflicts': [], 'retained_images_resolved': 46602}))
        self.manifest = {'profile': 'expanded-measurement-free', 'products': 107688,
                         'source_candidate_sha256': self.pin, 'files': {}}
        self.repin()

    def repin(self):
        self.manifest['files'] = {str(p.relative_to(self.package)):
                                 {'bytes': p.stat().st_size, 'sha256': sha256(p)}
                                 for p in self.package.rglob('*') if p.is_file() and p.name != 'manifest.json'}
        (self.package / 'manifest.json').write_text(json.dumps(self.manifest))

    def verify(self):
        return deployment.verified_export(self.package, self.candidate)

    def test_current_contract(self):
        self.assertEqual(self.verify()['source_candidate_sha256'], self.pin)

    def test_export_must_disclose_its_actual_completion_policy(self):
        from build_expanded_catalog import digest
        from authorized_completion import AUTHORIZATION
        policy={'schema':1,'active':True,'authorization':AUTHORIZATION,'candidate_sha256':self.pin,
                'review_identity':'qa','advisory_component_counts':True}
        self.manifest['review_identity']='qa'
        p=self.package/'visual-acceptance.json';record=json.loads(p.read_text())
        record.update(completion_policy=policy,completion_policy_sha256=digest(policy));p.write_text(json.dumps(record))
        self.manifest['completion_policy_sha256']='incorrect';self.repin()
        with self.assertRaisesRegex(ValueError,'Completion policy'):
            self.verify()
        self.manifest['completion_policy_sha256']=digest(policy);self.repin()
        self.assertEqual(self.verify()['completion_policy_sha256'],digest(policy))
        record['completion_policy']['advisory_component_counts']=False;p.write_text(json.dumps(record));self.repin()
        with self.assertRaisesRegex(ValueError,'Completion policy'):
            self.verify()

    def test_incomplete_image_acceptance(self):
        p = self.package / 'visual-acceptance.json'
        record = json.loads(p.read_text())
        record['ready'] = False
        record['unresolved_retained_briefs'] = 1
        p.write_text(json.dumps(record))
        self.repin()
        with self.assertRaisesRegex(ValueError, 'Image acceptance incomplete'):
            self.verify()

    def test_changed_bytes(self):
        (self.package / 'data/4-media.csv').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'Export bytes changed'):
            self.verify()

    def test_product_data_must_match_frozen_candidate(self):
        (self.package / 'data/1-simple.csv').write_text('sku\nWANDS-CHANGED\n')
        self.repin()
        with self.assertRaisesRegex(ValueError, 'differs from frozen candidate'):
            self.verify()

    def test_path_traversal(self):
        self.manifest['files']['../escape'] = {'bytes': 0, 'sha256': '0' * 64}
        (self.package / 'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, 'escapes package'):
            self.verify()

    def test_missing_acceptance_file_from_inventory(self):
        del self.manifest['files']['visual-acceptance.json']
        (self.package / 'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, 'Incomplete export manifest'):
            self.verify()

    def test_no_third_destination_or_early_deployment(self):
        snapshot = self.root / 'snapshot.json'
        snapshot.write_text(json.dumps({'schema': 2, 'existing_wands_stock': {},
                                       'database_writes': False, 'shared_wands_skus': [], 'root': '/third/store'}))
        with self.assertRaisesRegex(ValueError, 'Unapproved destination'):
            deployment.prepare_deployment(self.package, self.candidate, snapshot, self.root / 'out')
        self.assertFalse((self.root / 'out').exists())

    def correction_run(self):
        from build_expanded_catalog import canonical, digest, write_csv
        self.run=self.root/'run';self.run.mkdir()
        (self.run/'run.json').write_text(json.dumps({'candidate':str(self.candidate),'candidate_sha256':self.pin}))
        self.manifest['source_run_sha256']=sha256(self.run/'run.json')
        self.manifest['human_correction_manifests']=['approved-correction']
        row={'sku':'WANDS-SYN-1','product_type':'simple','wands_material':'Glass'}
        (self.candidate/'data/1-simple.csv').unlink();(self.package/'data/1-simple.csv').unlink()
        write_csv(self.candidate/'data/1-simple.csv',[row])
        write_csv(self.package/'data/1-simple.csv',[{**row,'wands_material':'Ceramic'}])
        entry={'catalog_patches':{'WANDS-SYN-1':{'wands_material':{'before':'Glass','after':'Ceramic'}}}}
        with sqlite3.connect(self.run/'ledger.sqlite') as db:
            db.execute('CREATE TABLE feedback_reprocessing(entry,entry_sha256,manifest_sha256,active)')
            db.execute('INSERT INTO feedback_reprocessing VALUES(?,?,?,1)',(canonical(entry),digest(entry),'approved-correction'))
        self.repin()

    def test_exact_approved_product_correction_passes(self):
        self.correction_run()
        self.assertEqual(deployment.verified_export(self.package,self.candidate,self.run)['human_correction_manifests'],['approved-correction'])

    def test_correction_requires_trusted_run_and_matching_receipts(self):
        self.correction_run()
        with self.assertRaisesRegex(ValueError,'trusted run'):
            self.verify()
        self.manifest['human_correction_manifests']=['wrong-correction'];self.repin()
        with self.assertRaisesRegex(ValueError,'Correction receipts'):
            deployment.verified_export(self.package,self.candidate,self.run)

    def test_unapproved_field_change_is_rejected_even_with_correction(self):
        self.correction_run()
        path=self.package/'data/1-simple.csv'
        path.write_text(path.read_text().replace('Ceramic','Metal'));self.repin()
        with self.assertRaisesRegex(ValueError,'approved corrections'):
            deployment.verified_export(self.package,self.candidate,self.run)


if __name__ == '__main__':
    unittest.main()

class MediaCoverageTest(unittest.TestCase):
    def setUp(self):
        self.products = {'WANDS-OLD': {'product_online': '2', 'visibility': 'Not Visible Individually'},
                         'WANDS-SYN-NEW': {'product_online': '1', 'visibility': 'Catalog, Search'}}
        self.media = [{'sku': 'WANDS-SYN-NEW'}]

    def test_retained_disabled_imageless_record_is_explicitly_accounted_for(self):
        deployment.check_media_coverage(self.products, self.media, ['WANDS-OLD'])

    def test_enabled_product_cannot_be_excluded(self):
        self.products['WANDS-OLD']['product_online'] = '1'
        with self.assertRaises(ValueError):
            deployment.check_media_coverage(self.products, self.media, ['WANDS-OLD'])

    def test_unlisted_missing_image_is_rejected(self):
        with self.assertRaises(ValueError):
            deployment.check_media_coverage(self.products, self.media, [])

    def test_new_product_cannot_be_excluded_even_if_disabled(self):
        self.products['WANDS-SYN-NEW'] = self.products['WANDS-OLD']
        with self.assertRaises(ValueError):
            deployment.check_media_coverage(self.products, [{'sku': 'WANDS-OLD'}], ['WANDS-SYN-NEW'])
