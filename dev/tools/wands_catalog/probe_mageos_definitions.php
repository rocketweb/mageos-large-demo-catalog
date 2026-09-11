<?php
declare(strict_types=1);

$a=getopt('',['root:','output:']);
function copyFields($product): array {
    $fields=[];
    foreach(['name','description','short_description','meta_title','meta_description','lab_sale_unit'] as $field){$fields[$field]=$product->getData($field);}
    return $fields;
}
try {
    $root=realpath($a['root']);$isolation=json_decode(file_get_contents($root.'/isolation.json'),true,512,JSON_THROW_ON_ERROR);
    $env=require $root.'/app/etc/env.php';$db=$env['db']['connection']['default'];
    if ($root!==$isolation['root'] || $db['host']!=='127.0.0.1:13380' || isset($db['port']) || $db['dbname']!==$isolation['database'] || !str_starts_with($db['dbname'],'wands_rehearsal_')) {throw new RuntimeException('Isolation guard failed');}
    putenv('WANDS_REHEARSAL_CRYPT_KEY='.bin2hex(random_bytes(16)));
    require $root.'/app/bootstrap.php';
    $bootstrap=\Magento\Framework\App\Bootstrap::create($root,['MAGE_MODE'=>'developer']);
    $om=$bootstrap->getObjectManager();$om->get(\Magento\Framework\App\State::class)->setAreaCode('frontend');
    $om->get(\Magento\Store\Model\StoreManagerInterface::class)->setCurrentStore(2);
    $resource=$om->get(\Magento\Framework\App\ResourceConnection::class);
    $connection=$resource->getConnection();
    if ($connection->fetchOne('SELECT DATABASE()')!==$isolation['database']) {throw new RuntimeException('Runtime connected to wrong database');}
    $nurseryId=$connection->fetchOne('SELECT entity_id FROM catalog_product_entity WHERE sku=?',['WANDS-000056']);
    $skus=['WANDS-000056','WANDS-003897','WANDS-017842','WANDS-030335','WANDS-035295'];$result=[];
    foreach($skus as $sku){
        $product=$om->create(\Magento\Catalog\Model\Product::class)->setStoreId(2);
        $id=$product->getIdBySku($sku);$product->load($id);
        if ($product->getSku()!==$sku) {throw new RuntimeException('Wrong product loaded');}
        $children=[];$optionLabels=[];
        if ($product->getTypeId()==='configurable') {
            foreach($product->getTypeInstance()->getConfigurableAttributes($product) as $attribute){$optionLabels[]=$attribute->getLabel();}
            foreach($product->getTypeInstance()->getUsedProducts($product) as $child){
                // Used-product collections deliberately select only some EAV attributes.
                // Verify copy through a complete product load, retaining the native relationship result.
                $full=$om->create(\Magento\Catalog\Model\Product::class)->setStoreId(2);$full->load($child->getId());
                $children[]=['sku'=>$child->getSku(),'name'=>$full->getName(),'sale_unit'=>$full->getData('lab_sale_unit'),'catalog_fields'=>copyFields($full),'type'=>$full->getTypeId(),'price'=>$full->getPrice(),'status'=>$full->getStatus(),'piece_count'=>$child->getAttributeText('wands_piece_count'),'finish'=>$child->getAttributeText('wands_finish')];
            }
        }
        $result[]=['sku'=>$sku,'type'=>$product->getTypeId(),'name'=>$product->getName(),'sale_unit'=>$product->getData('lab_sale_unit'),'catalog_fields'=>copyFields($product),
                   'price'=>$product->getPrice(),'special_price'=>$product->getSpecialPrice(),'weight'=>$product->getWeight(),'children'=>$children,'option_labels'=>$optionLabels,
                   'nursery_final_price'=>$sku==='WANDS-000056'&&$product->getTypeId()==='simple'?$product->getFinalPrice():null];
    }
    $retained=[];
    foreach(['WANDS-000056-TODDLER-56FF','WANDS-000056-TWIN-EAC9','WANDS-000056-FULL-008D','WANDS-000056-QUEEN-153F'] as $sku){
        $product=$om->create(\Magento\Catalog\Model\Product::class)->setStoreId(2);$product->load($product->getIdBySku($sku));
        if($product->getSku()!==$sku){throw new RuntimeException('Retained child missing');}
        $retained[]=['sku'=>$sku,'entity_id'=>$product->getId(),'status'=>$product->getStatus()];
    }
    if(file_exists($a['output'])) {throw new RuntimeException('Choose fresh evidence output');}
    file_put_contents($a['output'],json_encode(['versions'=>$isolation['versions'],'products'=>$result,'retained_children'=>$retained,'database'=>$isolation['database'],
        'probe_sha256'=>hash_file('sha256',__FILE__),'isolation_sha256'=>hash_file('sha256',$root.'/isolation.json'),
        'nursery_stock'=>$connection->fetchAll('SELECT qty,manage_stock,use_config_manage_stock,is_in_stock FROM cataloginventory_stock_item WHERE product_id=?',[$nurseryId]),
        'nursery_sources'=>$connection->fetchAll('SELECT source_code,quantity,status FROM inventory_source_item WHERE sku=?',['WANDS-000056']),
        'magento_models_loaded'=>true,'storefront_verified'=>false,'salability_verified'=>false,'live_writes'=>false],JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR).PHP_EOL);
    file_put_contents($a['output'].'.log',gmdate('c')." Isolated product-model probe passed\n");
} catch(Throwable $e) {
    file_put_contents($a['output'].'.log',gmdate('c').' Probe failed: '.$e->getMessage().PHP_EOL,FILE_APPEND);exit(1);
}
