"""Apply the approved, frozen enrichment delta to the existing internal demo only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/opt/comtom/stores/relevance/catalog-enriched-20260913-v2')
APP = Path('/opt/comtom/stores/relevance/src')
WORK = APP/'var/catalog-enriched-20260913-v2'
CLI = ['docker', 'exec', '--user', 'www-data', 'farm-relevance-php-1', 'php', '-d', 'memory_limit=3G']
PREFIX = 'var/catalog-enriched-20260913-v2/'
FILES = ['Model/Catalog/ProductImporter.php', 'Setup/Patch/Data/AddDepthAttributes.php',
         'Setup/Patch/Data/AddSpecificationDisclosure.php', 'etc/depth_attributes.json']


def run(stage, command, output=None):
    (ROOT/'update-state.json').write_text(json.dumps({'stage': stage, 'status': 'running'}))
    with (ROOT/(stage+'.log')).open('ab') as log:
        result = subprocess.run(command, stdout=output or log, stderr=log)
    (ROOT/'update-state.json').write_text(json.dumps({'stage': stage, 'status': 'complete' if result.returncode == 0 else 'failed'}))
    if result.returncode:
        raise RuntimeError('Stopped at '+stage+'; inspect receipts and rollback instructions')


def main():
    if Path.cwd().resolve() != ROOT or ROOT.is_symlink() or APP.is_symlink():
        raise RuntimeError('Wrong target root')
    plan = json.loads((WORK/'plan.json').read_text())
    assert plan['products'] == 55044 and plan['source_products'] == 53844
    assert plan['existing_links'] == 0 and plan['desired_links'] == 65375
    assert plan['search_engine'] == 'mageos_opensearch_hybrid'
    assert hashlib.sha256((WORK/'attributes.csv').read_bytes()).hexdigest() == plan['csv_sha256']
    module = APP/'app/code/RocketWeb/LabCatalog'
    assert hashlib.sha256((module/FILES[0]).read_bytes()).hexdigest() == 'cb3401af2219100dd6d60e3a3c95a80759a2dd90b36b7a1aa5eddc9992e7ea1a'
    assert all(not (module/name).exists() for name in FILES[1:])
    (ROOT/'update-started').touch(exist_ok=False)
    with os.fdopen(os.open(ROOT/'before.sql', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as output:
        run('database-backup', CLI+[PREFIX+'demo_database.php', 'backup'], output)
    assert (ROOT/'before.sql').stat().st_size > 1000000
    with (ROOT/'before.sql').open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    (ROOT/'backup-sha256.txt').write_text(digest+'  before.sql\n')
    shutil.copytree(module, ROOT/'module-before')
    for name in FILES:
        destination = module/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/'staged/module'/name, destination)
        os.chown(destination, 33, 33)
    # Apply only the two named catalog data patches, not pending patches in other modules.
    patch_code = r'''require 'app/bootstrap.php';
$o=Magento\Framework\App\Bootstrap::create(BP,$_SERVER)->getObjectManager();
$history=$o->get(Magento\Framework\Setup\Patch\PatchHistory::class);
foreach([RocketWeb\LabCatalog\Setup\Patch\Data\AddDepthAttributes::class,
RocketWeb\LabCatalog\Setup\Patch\Data\AddSpecificationDisclosure::class] as $class) {
if($history->isApplied($class)){throw new RuntimeException('Unexpected previously applied patch');}
$o->create($class)->apply();$history->fixPatch($class);
}'''
    run('catalog-schema', CLI+['-r', patch_code])
    run('eav-cache', CLI+['bin/magento', 'cache:clean', 'config', 'eav'])
    run('attribute-import', CLI+['bin/magento', 'lab:wands:import', '--file='+PREFIX+'attributes.csv'])
    run('link-import', CLI+['bin/magento', 'lab:wands:import', '--file='+PREFIX+'data/5-merchandising.csv'])
    run('canonical-verification', CLI+[PREFIX+'demo_scope.php', 'verify'])
    run('reindex', CLI+['bin/magento', 'indexer:reindex'])
    run('cache-clean', CLI+['bin/magento', 'cache:clean'])
    (ROOT/'update-complete').touch(exist_ok=False)


if __name__ == '__main__':
    main()
