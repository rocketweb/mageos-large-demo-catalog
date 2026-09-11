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
    def php_string(s):return "'"+str(s).replace('\\','\\\\').replace("'","\\'")+"'"
    root=a.output_dir.resolve();check(not root.exists(),'Choose a fresh isolated root')
    check(a.database.startswith('wands_rehearsal_') and a.database.replace('_','').isalnum(),'Unsafe database')
    source=a.source.resolve();check((source/'vendor/autoload.php').is_file(),'Installed vendor runtime missing')
    packages=json.loads((source/'composer.lock').read_text())['packages']
    versions={p['name']:p['version'] for p in packages if p['name'] in ('mage-os/product-community-edition','hyva-themes/magento2-default-theme')}
    check(versions.get('mage-os/product-community-edition')=='3.5.0','Runtime does not match observed demo')
    modules=json.loads(subprocess.run([a.php,'-r','$c=require $argv[1];echo json_encode($c["modules"]);',str(source/'app/etc/config.php')],check=True,capture_output=True,text=True).stdout)
    root.mkdir(parents=True)
    metadata_packages=[]
    for package in packages:
        if package['name'] in versions:
            metadata_packages.append({k:package[k] for k in ('name','version','type','extra') if k in package})
    write_json(root/'composer.json',{'name':'rocketweb/isolated-catalog-rehearsal','type':'project',
        'require':{'mage-os/product-community-edition':versions['mage-os/product-community-edition']},
        'config':{'allow-plugins':False},'repositories':[{'packagist.org':False}]})
    write_json(root/'composer.lock',{'packages':metadata_packages,'packages-dev':[],
        'aliases':[],'minimum-stability':'stable','stability-flags':{},'prefer-stable':False,'prefer-lowest':False,
        'platform':{},'platform-dev':{}})
    for d in ('app/etc','var','generated','pub/media','pub/static'): (root/d).mkdir(parents=True,exist_ok=True)
    for f in ('app/bootstrap.php','app/autoload.php','app/etc/di.xml','app/etc/vendor_path.php'):
        shutil.copyfile(source/f,root/f)
    (root/'vendor').symlink_to(source/'vendor',target_is_directory=True)
    helper=Path(__file__).with_name('isolate_rehearsal_autoloader.php')
    shutil.copyfile(helper,root/'app/rehearsal_autoloader.php')
    autoload=root/'app/autoload.php';content=autoload.read_text()
    marker='$composerAutoloader = include $vendorAutoload;'
    check(content.count(marker)==1,'Unsupported installed application autoload entrypoint')
    autoload.write_text(content.replace(marker,marker+'\nrequire __DIR__."/rehearsal_autoloader.php";\n'
        +'$composerAutoloader = isolateRehearsalAutoloader($composerAutoloader, '+php_string(source)+', BP);'))
    candidate_hashes={}
    if getattr(a,'candidate_label_plugin',False):
        module=Path(__file__).resolve().parents[3]/'app/code/RocketWeb/LabCatalog'
        fixture=root/'app/code/WandsRehearsal/CandidateLabel';(fixture/'etc/frontend').mkdir(parents=True)
        for relative in ('Plugin/ConfigurableFamilyLabel.php','etc/frontend/di.xml'):
            candidate_hashes[str(module/relative)]=sha256(module/relative)
        shutil.copyfile(module/'etc/frontend/di.xml',fixture/'etc/frontend/di.xml')
        (fixture/'etc/module.xml').write_text('<?xml version="1.0"?><config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="urn:magento:framework:Module/etc/module.xsd"><module name="WandsRehearsal_CandidateLabel"><sequence><module name="RocketWeb_LabCatalog"/></sequence></module></config>')
        autoload.write_text(autoload.read_text()+'\nrequire_once '+php_string(module/'Plugin/ConfigurableFamilyLabel.php')+';\n'
            +'\\Magento\\Framework\\Component\\ComponentRegistrar::register("module", "WandsRehearsal_CandidateLabel", BP."/app/code/WandsRehearsal/CandidateLabel");\n')
        modules['WandsRehearsal_CandidateLabel']=1
    # Module enablement is metadata, not the source environment or system configuration.
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
               'source_generated_code_excluded':True,'autoload_isolation_sha256':sha256(helper),
               'candidate_label_plugin':bool(candidate_hashes),'candidate_hashes':candidate_hashes,
               'runtime_verified':False,'live_writes':False})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','output-dir'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--database',required=True);p.add_argument('--php',required=True)
    p.add_argument('--candidate-label-plugin',action='store_true');a=p.parse_args()
    import logging
    a.output_dir.parent.mkdir(parents=True,exist_ok=True);logging.basicConfig(filename=a.output_dir.with_suffix('.log'),level=logging.INFO)
    try:build(a);logging.info('Isolated root prepared; no live configuration read')
    except Exception:logging.exception('Isolation preparation failed');raise SystemExit(1)
