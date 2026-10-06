#!/usr/bin/env python3
"""Build a private row inverse from exact before/after catalog journals."""
from contextlib import closing
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from bulk_expansion_images import atomic_json
from build_expanded_catalog import canonical
from prepare_catalog import sha256


def runtime_path(path,root):
    if root=='/var/www/html':
        host=Path('/opt/comtom/stores/relevance/src')
        if not path.is_relative_to(host/'var'):
            raise ValueError('Comtom journal must be inside its private store directory')
        return Path(root)/path.relative_to(host)
    return path


def build(before, after, output, *, evidence_paths=None):
    if output.exists():raise ValueError('Choose a fresh private inverse')
    snapshots=[json.loads((p/'manifest.json').read_text()) for p in (before,after)]
    for key in ('root','prefix','tool_sha256','env_sha256','database'):
        if snapshots[0].get(key)!=snapshots[1].get(key):raise ValueError('Journal destination or schema tool changed')
    if snapshots[0]['root'] not in {'/Users/matt/code/mageos-latest','/var/www/html'}:raise ValueError('Unsupported destination')
    paths=evidence_paths or (before,after)
    if len(paths)!=2:raise ValueError('Exact before and after evidence paths required')
    if evidence_paths and snapshots[0]['root']!='/var/www/html' and tuple(paths)!=(before,after):
        raise ValueError('Only private mirrored Comtom evidence may map to remote paths')
    runtime_paths=[runtime_path(p,snapshots[0]['root']) for p in paths]
    if snapshots[0]['tables'].keys()!=snapshots[1]['tables'].keys():raise ValueError('Database table schema changed')
    output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if output.parent.stat().st_mode&0o077:raise ValueError('Private inverse directory required')
    counts={}
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary,closing(sqlite3.connect(Path(temporary)/'rows.sqlite')) as db:
        db.executescript('CREATE TABLE rows(side INTEGER,key TEXT,row TEXT,selector TEXT,PRIMARY KEY(side,key));')
        with output.open('xb') as raw:
            os.chmod(output,0o600)
            with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0) as stream:
                for table,info in snapshots[0]['tables'].items():
                    db.execute('DELETE FROM rows')
                    if info['keys']!=snapshots[1]['tables'][table]['keys'] or info.get('columns')!=snapshots[1]['tables'][table].get('columns'):
                        raise ValueError('Catalog table schema changed')
                    for side,(directory,snapshot) in enumerate(zip((before,after),snapshots)):
                        path=directory/(table+'.jsonl.gz');meta=snapshot['tables'][table]
                        if path.stat().st_mode&0o077 or sha256(path)!=meta['sha256']:raise ValueError('Snapshot bytes or privacy changed')
                        h=hashlib.sha256();n=0
                        with gzip.open(path,'rb') as source,db:
                            for line in source:
                                h.update(line);n+=1;item=json.loads(line)
                                if set(item['selector'])!=set(meta['keys']):raise ValueError('Invalid primary-key snapshot')
                                selector=canonical(item['selector']);db.execute('INSERT INTO rows VALUES(?,?,?,?)',
                                    (side,selector,canonical(item['row']),selector))
                        if n!=meta['rows'] or h.hexdigest()!=meta['row_sha256']:raise ValueError('Snapshot rows changed')
                    changed=db.execute('''SELECT a.selector,a.row,b.row FROM rows a LEFT JOIN rows b ON b.side=1 AND a.key=b.key
                        WHERE a.side=0 AND (b.row IS NULL OR a.row!=b.row)
                        UNION ALL SELECT b.selector,NULL,b.row FROM rows b LEFT JOIN rows a ON a.side=0 AND a.key=b.key
                        WHERE b.side=1 AND a.row IS NULL ORDER BY 1''')
                    n=0
                    for selector,old,new in changed:
                        stream.write((canonical({'table':table,'selector':json.loads(selector),
                            'before':json.loads(old) if old is not None else None,
                            'after':json.loads(new) if new is not None else None})+'\n').encode());n+=1
                    counts[table]=n
            raw.flush();os.fsync(raw.fileno())
    receipt={'root':snapshots[0]['root'],'before':str(runtime_paths[0]),
        'after':str(runtime_paths[1]),
        'before_sha256':sha256(before/'manifest.json'),'after_sha256':sha256(after/'manifest.json'),
        'inverse_sha256':sha256(output),'operations':sum(counts.values()),'tables':counts,
        'scope':'Only exact changed primary-key rows; preserve every unchanged row. Refuse later drift before compensation.'}
    atomic_json(output.with_suffix(output.suffix+'.json'),receipt);os.chmod(output.with_suffix(output.suffix+'.json'),0o600)
    return receipt


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','after','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(build(a.before.resolve(),a.after.resolve(),a.output.resolve()),indent=2))
