"""Separate append-only gallery phase for the approved internal demo update."""
import hashlib
import os
from pathlib import Path
import shutil
import sys

from demo_update import ROOT, APP, WORK, CLI, PREFIX, run


def main():
    if Path.cwd().resolve() != ROOT or ROOT.is_symlink() or not (ROOT/'update-complete').exists():
        raise RuntimeError('Wrong target or enrichment not verified')
    (ROOT/'gallery-started').touch(exist_ok=False)
    pin = '6c1f924b8e9f1e2048f48d0426a3e0e9de885b4e2cc004058a45fa3c08e60ce5'
    run('gallery-extract', [sys.executable, str(ROOT/'release.py'), str(ROOT/'packages'/pin),
        '--manifest-sha256', pin, '--extract', str(ROOT/'gallery-staged')])
    shutil.copytree(ROOT/'gallery-staged/data', WORK/'gallery/data')
    run('gallery-permissions', ['chown', '-R', '33:33', str(WORK/'gallery')])
    run('gallery-before', CLI+[PREFIX+'verify_gallery.php', 'before', '--demo'])
    with os.fdopen(os.open(ROOT/'before-gallery.sql', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as output:
        run('gallery-database-backup', CLI+[PREFIX+'demo_database.php', 'backup'], output)
    assert (ROOT/'before-gallery.sql').stat().st_size > 1000000
    with (ROOT/'before-gallery.sql').open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    (ROOT/'before-gallery.sha256').write_text(digest+'  before-gallery.sql\n')
    destination = APP/'pub/media/import/wands-lab/galleries'
    if destination.exists():
        raise RuntimeError('Gallery import destination already exists; no files overwritten')
    shutil.copytree(ROOT/'gallery-staged/media/wands-lab/galleries', destination)
    run('gallery-media-permissions', ['chown', '-R', '33:33', str(destination)])
    run('gallery-import', CLI+['bin/magento', 'lab:wands:import',
        '--file='+PREFIX+'gallery/data/gallery-additions.csv'])
    run('gallery-after', CLI+[PREFIX+'verify_gallery.php', 'after', '--demo'])
    run('gallery-canonical-verification', CLI+[PREFIX+'demo_scope.php', 'verify', '--after-gallery'])
    run('gallery-cache', CLI+['bin/magento', 'cache:clean'])
    (ROOT/'gallery-complete').touch(exist_ok=False)


if __name__ == '__main__':
    main()
