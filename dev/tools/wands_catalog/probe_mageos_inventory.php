<?php
declare(strict_types=1);

/** Local-only inventory lifecycle probe. Never creates a quote or reservation. */
$a=getopt('',['root:','output:','plan:','reindex']);
try {
    if(file_exists($a['output'])) {throw new RuntimeException('Choose fresh evidence output');}
    $root=realpath($a['root']);$isolation=json_decode(file_get_contents($root.'/isolation.json'),true,512,JSON_THROW_ON_ERROR);
    $env=require $root.'/app/etc/env.php';$db=$env['db']['connection']['default'];
    if($root!==$isolation['root'] || $db['host']!=='127.0.0.1:13380' || isset($db['port']) || $db['dbname']!==$isolation['database'] || !preg_match('/^wands_rehearsal_[a-z0-9_]+$/',$db['dbname'])) {throw new RuntimeException('Isolation guard failed');}
    if(hash_file('sha256',$a['plan'])!=='91cff3d0c405006285921e6f7e90d3499fb60a8e23e91def55ef840ebc121828') {throw new RuntimeException('Unapproved plan');}
    $plan=json_decode(file_get_contents($a['plan']),true,512,JSON_THROW_ON_ERROR);
    putenv('WANDS_REHEARSAL_CRYPT_KEY='.bin2hex(random_bytes(16)));
    require $root.'/app/bootstrap.php';
    $om=\Magento\Framework\App\Bootstrap::create($root,['MAGE_MODE'=>'developer'])->getObjectManager();
    $om->get(\Magento\Framework\App\State::class)->setAreaCode('frontend');
    $stores=$om->get(\Magento\Store\Model\StoreManagerInterface::class);$stores->setCurrentStore(2);
    $connection=$om->get(\Magento\Framework\App\ResourceConnection::class)->getConnection();
    if($connection->fetchOne('SELECT DATABASE()')!==$isolation['database']) {throw new RuntimeException('Wrong database');}
    $entities=$connection->fetchAll('SELECT entity_id,sku FROM catalog_product_entity ORDER BY entity_id');
    $actual=array_column($entities,'sku');sort($actual);$expected=$plan['approved_products'];sort($expected);
    if(count($actual)!==17 || $actual!==$expected) {throw new RuntimeException('Fixture escaped seventeen-product scope');}
    $normalize=static function(array $rows):array {
        $result=[];
        foreach($rows as $row){ksort($row);$result[]=json_encode(array_map(static fn($v)=>$v===null?null:(string)$v,$row),JSON_THROW_ON_ERROR);}
        sort($result);return $result;
    };
    $hashes=static function() use($connection,$normalize):array {
        $result=[];
        foreach($connection->fetchCol('SHOW TABLES') as $table){$result[$table]=hash('sha256',json_encode($normalize($connection->fetchAll('SELECT * FROM '.$connection->quoteIdentifier($table))),JSON_THROW_ON_ERROR));}
        ksort($result);return $result;
    };
    $beforeHashes=$hashes();
    $beforeIndex=$connection->fetchAll('SELECT * FROM cataloginventory_stock_status ORDER BY product_id,website_id,stock_id');
    if(isset($a['reindex'])) {
        // Native partial indexer only, never executeFull. All fixture entities are in the approved scope.
        $om->get(\Magento\CatalogInventory\Model\Indexer\Stock::class)->executeList(array_map('intval',array_column($entities,'entity_id')));
    }
    $website=$stores->getStore()->getWebsite()->getCode();
    $stock=(int)$om->get(\Magento\InventorySalesApi\Api\StockResolverInterface::class)->execute('website',$website)->getStockId();
    if($website!=='wands' || $stock!==1) {throw new RuntimeException('Wrong sales channel');}
    $products=[];
    foreach($entities as $entity) {
        $sku=$entity['sku'];$product=$om->create(\Magento\Catalog\Model\Product::class)->setStoreId(2);$product->load($entity['entity_id']);
        $item=['sku'=>$sku,'type'=>$product->getTypeId(),'status'=>(int)$product->getStatus(),'checks'=>[],'errors'=>[]];
        $calls=['model_is_salable'=>static fn()=>$product->isSalable(),
            'inventory_is_salable'=>static fn()=>$om->get(\Magento\InventorySalesApi\Api\IsProductSalableInterface::class)->execute($sku,$stock)];
        if($product->getTypeId()==='simple') {
            $calls['salable_quantity']=static fn()=>$om->get(\Magento\InventorySalesApi\Api\GetProductSalableQtyInterface::class)->execute($sku,$stock);
            foreach([1,47,48] as $qty){
                $calls['requested_'.$qty]=static function() use($om,$sku,$stock,$qty):array {
                    $result=$om->get(\Magento\InventorySalesApi\Api\IsProductSalableForRequestedQtyInterface::class)->execute($sku,$stock,(float)$qty);
                    return ['salable'=>$result->isSalable(),'error_codes'=>array_map(static fn($e)=>$e->getCode(),$result->getErrors())];
                };
            }
        }
        foreach($calls as $name=>$call){try{$item['checks'][$name]=$call();}catch(Throwable $e){$item['errors'][$name]=get_class($e).': '.$e->getMessage();}}
        $products[]=$item;
    }
    $afterHashes=$hashes();$changed=[];
    foreach(array_unique([...array_keys($beforeHashes),...array_keys($afterHashes)]) as $table){if(($beforeHashes[$table]??null)!==($afterHashes[$table]??null)){$changed[]=$table;}}
    if(array_diff($changed,isset($a['reindex'])?['cataloginventory_stock_status']:[])) {throw new RuntimeException('Unexpected database writes during inventory check');}
    $result=['versions'=>$isolation['versions'],'database'=>$isolation['database'],'website'=>$website,'stock_id'=>$stock,
        'products'=>$products,'reindexed'=>isset($a['reindex']),'index_before'=>$beforeIndex,
        'index_after'=>$connection->fetchAll('SELECT * FROM cataloginventory_stock_status ORDER BY product_id,website_id,stock_id'),
        'before_table_hashes'=>$beforeHashes,'after_table_hashes'=>$afterHashes,'changed_tables'=>$changed,
        'probe_sha256'=>hash_file('sha256',__FILE__),'plan_sha256'=>hash_file('sha256',$a['plan']),'isolation_sha256'=>hash_file('sha256',$root.'/isolation.json'),
        'configuration'=>'isolated defaults plus captured product stock settings; not complete live configuration',
        'live_writes'=>false,'cart_verified'=>false,'storefront_verified'=>false];
    $f=fopen($a['output'],'x');if(!$f){throw new RuntimeException('Output exists');}chmod($a['output'],0600);
    fwrite($f,json_encode($result,JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR).PHP_EOL);fclose($f);
    file_put_contents($a['output'].'.log',gmdate('c')." Local inventory observations captured; inspect result for acceptance\n");
}catch(Throwable $e){
    $messages=[];
    do{$messages[]=get_class($e).': '.$e->getMessage();$e=$e->getPrevious();}while($e);
    file_put_contents($a['output'].'.log',gmdate('c').' Inventory probe failed: '.implode(' caused by ',$messages).PHP_EOL,FILE_APPEND);
    if(isset($beforeHashes,$hashes)){
        file_put_contents($a['output'].'.failed.json',json_encode(['before_table_hashes'=>$beforeHashes,'after_table_hashes'=>$hashes(),'accepted'=>false,'live_writes'=>false],JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR).PHP_EOL);
    }
    exit(1);
}
