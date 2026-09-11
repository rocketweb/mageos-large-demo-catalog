#!/usr/bin/env python3
"""Create an isolated application root; reuse installed code without copying its credentials."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from build_realism_review import write_json
from prepare_catalog import sha256
from verify_catalog_repairs import check


def build(a):
    root=a.output_dir.resolve();check(not root.exists(),'Choose a fresh isolated root')
    check(a.database.startswith('wands_rehearsal_') and a.database.replace('_','').isalnum(),'Unsafe database')
    source=a.source.resolve();check((source/'vendor/autoload.php').is_file(),'Installed vendor runtime missing')
    packages=json.loads((source/'composer.lock').read_text())['packages']
    versions={p['name']:p['version'] for p in packages if p['name'] in ('mage-os/product-community-edition','hyva-themes/magento2-default-theme')}
    check(versions.get('mage-os/product-community-edition')=='3.5.0','Runtime does not match observed demo')
    modules=json.loads(subprocess.run([a.php,'-r','$c=require $argv[1];echo json_encode($c["modules"]);',str(source/'app/etc/config.php')],check=True,capture_output=True,text=True).stdout)
    root.mkdir(parents=True)
    for d in ('app/etc','var','generated','pub/media','pub/static'): (root/d).mkdir(parents=True,exist_ok=True)
    for f in ('app/bootstrap.php','app/autoload.php','app/etc/di.xml','app/etc/vendor_path.php'):
        shutil.copyfile(source/f,root/f)
    (root/'vendor').symlink_to(source/'vendor',target_is_directory=True)
    # Module enablement is metadata, not the source environment or system configuration.
    def php_string(s):return "'"+str(s).replace('\\','\\\\').replace("'","\\'")+"'"
    (root/'app/etc/config.php').write_text('<?php return ["modules"=>['+','.join(php_string(k)+'=>'+str(int(v)) for k,v in modules.items())+']];\n')
    (root/'app/etc/env.php').write_text('''<?php
return [
 'install'=>['date'=>'Fri, 11 Sep 2026 00:00:00 +0000'],
 'MAGE_MODE'=>'developer',
 'crypt'=>['key'=>getenv('WANDS_REHEARSAL_CRYPT_KEY')],
 'db'=>['connection'=>['default'=>['host'=>'127.0.0.1:13380','dbname'=>'''+php_string(a.database)+''','username'=>'root','password'=>'','active'=>1,'model'=>'mysql4','engine'=>'innodb','initStatements'=>'SET NAMES utf8mb4;']]],
 'resource'=>['default_setup'=>['connection'=>'default']],
 'cache'=>['frontend'=>['default'=>['backend'=>'Magento\\\\Framework\\\\Cache\\\\Backend\\\\File'],'page_cache'=>['backend'=>'Magento\\\\Framework\\\\Cache\\\\Backend\\\\File']]],
 'session'=>['save'=>'files'],
 'system'=>['default'=>['web'=>['unsecure'=>['base_url'=>'http://127.0.0.1:18880/'],'secure'=>['base_url'=>'http://127.0.0.1:18880/']],
 'catalog'=>['search'=>['engine'=>'opensearch','opensearch_server_hostname'=>'127.0.0.1','opensearch_server_port'=>19999]],
 'currency'=>['options'=>['base'=>'USD','default'=>'USD','allow'=>'USD']]]]
];
''')
    (root/'app/etc/env.php').chmod(0o600)
    write_json(root/'isolation.json',{'source':str(source),'root':str(root),'database':a.database,'host':'127.0.0.1','port':13380,
               'source_env_read':False,'source_config_copied':'modules only','source_vendor_sha256':sha256(source/'composer.lock'),'versions':versions,
               'runtime_verified':False,'live_writes':False})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','output-dir'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--database',required=True);p.add_argument('--php',required=True);a=p.parse_args()
    import logging
    a.output_dir.parent.mkdir(parents=True,exist_ok=True);logging.basicConfig(filename=a.output_dir.with_suffix('.log'),level=logging.INFO)
    try:build(a);logging.info('Isolated root prepared; no live configuration read')
    except Exception:logging.exception('Isolation preparation failed');raise SystemExit(1)
