import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'distribution'))
from publish_prepared_release import local_plan, remote_assets


class PreparedPublicationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);(self.root / 'assets').mkdir()
        (self.root / 'assets/public.tar').write_bytes(b'archive')
        (self.root / 'release-notes.md').write_bytes(b'reviewed notes')
        self.sha = hashlib.sha256(b'archive').hexdigest()
        self.plan = {'assets': {'public.tar': {'bytes': 7, 'sha256': self.sha}},
                     'release_notes_sha256': hashlib.sha256(b'reviewed notes').hexdigest()}
        (self.root / 'publication-plan.json').write_text(json.dumps(self.plan))

    def test_unplanned_files_and_changed_assets_cannot_enter_publication(self):
        self.assertEqual(local_plan(self.root), self.plan)
        (self.root / 'assets/private-backup.txt').write_text('fixture')
        with self.assertRaisesRegex(ValueError, 'differs'):
            local_plan(self.root)
        (self.root / 'assets/private-backup.txt').unlink()
        (self.root / 'assets/public.tar').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'asset changed'):
            local_plan(self.root)

    def test_reviewed_notes_are_bound_to_the_plan(self):
        (self.root / 'release-notes.md').write_text('other notes')
        with self.assertRaisesRegex(ValueError, 'notes changed'):
            local_plan(self.root)

    def test_superseded_catalog_cannot_be_published(self):
        (self.root / 'PUBLICATION_BLOCKED.json').write_text(json.dumps({'reason': 'Catalog exclusions require a rebuilt package'}))
        with self.assertRaisesRegex(ValueError, 'blocked'):
            local_plan(self.root)

    def test_only_complete_matching_remote_assets_can_be_published(self):
        remote = {'assets': []}
        self.assertEqual(remote_assets(remote, self.plan), ['public.tar'])
        with self.assertRaisesRegex(ValueError, 'missing assets'):
            remote_assets(remote, self.plan, complete=True)
        remote['assets'] = [{'name': 'public.tar', 'size': 7, 'digest': 'sha256:' + self.sha}]
        self.assertEqual(remote_assets(remote, self.plan, complete=True), [])
        remote['assets'][0]['digest'] = 'sha256:different'
        with self.assertRaisesRegex(ValueError, 'differs'):
            remote_assets(remote, self.plan, complete=True)


if __name__ == '__main__':
    unittest.main()
