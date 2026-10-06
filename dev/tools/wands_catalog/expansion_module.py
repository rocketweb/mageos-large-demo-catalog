"""Apply or reverse exact reviewed LabCatalog file changes in existing stores."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
from hashlib import file_digest

ROOTS={'/Users/matt/code/mageos-latest','/opt/comtom/stores/relevance/src'}
FILES=(
 'Console/Command/ImportProductsCommand.php','Model/Catalog/ProductImporter.php',
 'Model/Catalog/ParentTypeConverter.php','Model/Catalog/NavigationCurator.php',
 'Model/Catalog/StockPreservation.php','Model/Catalog/BundleAssortmentReconciler.php',
 'Plugin/PreserveExistingStock.php','etc/di.xml',
 'Setup/Patch/Data/AddRealismAttributes.php','Setup/Patch/Data/AddDepthAttributes.php',
 'Setup/Patch/Data/AddSpecificationDisclosure.php','etc/depth_attributes.json')


def sha(path):
    with path.open('rb') as stream:return file_digest(stream,'sha256').hexdigest()


def save(path,value):
    with path.open('x') as stream:
        os.chmod(path,0o600);json.dump(value,stream,sort_keys=True,indent=2);stream.write('\n')


def prepare(root,source,stage):
    if str(root) not in ROOTS or not stage.is_relative_to(root/'var') or stage.exists():
        raise ValueError('Fresh private stage in an existing installation required')
    module=root/'app/code/RocketWeb/LabCatalog'
    if module.is_symlink() or not (module/'registration.php').is_file():raise ValueError('Existing module required')
    stage.mkdir(mode=0o700,parents=True);records=[]
    for name in FILES:
        target=module/name;original=source/name
        if not original.is_file() or not target.resolve().is_relative_to(module):raise ValueError('Missing source or escaped module path')
        before=sha(target) if target.exists() else None;after=sha(original)
        if before==after:continue
        for kind,path in [('before',target),('after',original)]:
            if not path.exists():continue
            dest=stage/kind/name;dest.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            shutil.copyfile(path,dest);dest.chmod(0o600)
        records.append({'file':name,'before':before,'after':after,
            'mode':target.stat().st_mode&0o777 if target.exists() else 0o644})
    result={'root':str(root),'schema':1,'files':records,'scope':'Only the named WANDS catalog importer, stock protection, navigation and attribute definitions.'}
    save(stage/'manifest.json',result)
    return {'files':len(records),'manifest_sha256':sha(stage/'manifest.json'),'database_writes':False,'active_module_changed':False}


def apply(root,stage,pin,reverse=False):
    if str(root) not in ROOTS or not stage.is_relative_to(root/'var') or stage.stat().st_mode&0o077:
        raise ValueError('Exact private existing-installation stage required')
    if sha(stage/'manifest.json')!=pin:raise ValueError('Reviewed module manifest changed')
    plan=json.loads((stage/'manifest.json').read_text());module=root/'app/code/RocketWeb/LabCatalog'
    if plan['root']!=str(root) or plan['schema']!=1:raise ValueError('Wrong module destination')
    side,expected=('before','after') if reverse else ('after','before')
    if len({r['file'] for r in plan['files']})!=len(plan['files']):raise ValueError('Duplicate module operation')
    for r in plan['files']:
        path=module/r['file'];source=stage/side/r['file']
        if r['file'] not in FILES or not path.resolve().is_relative_to(module):raise ValueError('File outside module scope')
        if (sha(path) if path.exists() else None)!=r[expected]:raise ValueError('Module file drifted: '+r['file'])
        if r[side] is not None and sha(source)!=r[side]:raise ValueError('Staged module bytes changed')
    applied=[]
    try:
        for r in plan['files']:
            path=module/r['file'];path.parent.mkdir(parents=True,exist_ok=True)
            if r[side] is None:path.unlink()
            else:
                with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
                    stream.write((stage/side/r['file']).read_bytes());stream.flush();os.fsync(stream.fileno());temporary=Path(stream.name)
                temporary.chmod(r['mode'])
                if str(root).startswith('/opt/comtom/') and os.geteuid()==0:os.chown(temporary,33,33)
                os.replace(temporary,path)
            applied.append(r)
    except BaseException:
        # Restore only files changed by this invocation, retaining unrelated work.
        for r in reversed(applied):
            path=module/r['file']
            if r[expected] is None:path.unlink()
            else:
                shutil.copyfile(stage/expected/r['file'],path);path.chmod(r['mode'])
                if str(root).startswith('/opt/comtom/') and os.geteuid()==0:os.chown(path,33,33)
        raise
    for r in plan['files']:
        path=module/r['file']
        if (sha(path) if path.exists() else None)!=r[side]:raise ValueError('Installed module verification failed')
    return {'root':str(root),'files_changed':len(applied),'reverse':reverse,
            'state':'exact module bytes applied; configuration cache and DI compilation still required'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','apply','rollback'])
    for name in ('root','stage'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--manifest-sha256');a=p.parse_args()
    print(json.dumps(prepare(a.root.resolve(),a.source.resolve(),a.stage.resolve()) if a.action=='prepare'
        else apply(a.root.resolve(),a.stage.resolve(),a.manifest_sha256,a.action=='rollback'),indent=2))
