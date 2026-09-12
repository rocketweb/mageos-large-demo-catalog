<?php
declare(strict_types=1);
require __DIR__.'/rehearsal_runtime.php';

function isRehearsalPriceIndex(string $table):bool
{
    return str_starts_with($table,'catalog_product_index_price') || in_array($table,['catalog_product_index_website','catalog_product_index_tier_price','cataloginventory_stock_status'],true);
}
if(realpath($_SERVER['SCRIPT_FILENAME']??'')!==__FILE__){return;}
$a=getopt('',['root:','output:','plan:','reindex']);
try{
    [$om,$connection,$isolation,$entities]=openRehearsal($a);
    requireRehearsal($connection->fetchCol('SELECT customer_group_id FROM customer_group')===[0] || $connection->fetchCol('SELECT customer_group_id FROM customer_group')===['0'],'Only guest pricing is supported');
    $before=rehearsalTableHashes($connection);
    if(isset($a['reindex'])){
        $ids=array_map('intval',array_column($entities,'entity_id'));
        $om->get(\Magento\CatalogInventory\Model\Indexer\Stock::class)->executeList($ids);
        $om->get(\Magento\Catalog\Model\Indexer\Product\Price::class)->executeList($ids);
    }
    $products=[];
    foreach($entities as $entity){
        $product=$om->create(\Magento\Catalog\Model\Product::class)->setStoreId(2)->setCustomerGroupId(0);$product->load($entity['entity_id']);
        $record=['sku'=>$entity['sku'],'entity_id'=>$entity['entity_id'],'type'=>$product->getTypeId(),'status'=>(int)$product->getStatus(),
            'base_price'=>$product->getData('price'),'special_price'=>$product->getSpecialPrice(),'checks'=>[],'errors'=>[]];
        if($record['status']===1){
            foreach(['model_final'=>static fn()=>$product->getFinalPrice(),
                'pricing_final'=>static fn()=>$product->getPriceInfo()->getPrice('final_price')->getValue(),
                'pricing_regular'=>static fn()=>$product->getPriceInfo()->getPrice('regular_price')->getValue()] as $key=>$call){
                try{$record['checks'][$key]=$call();}catch(Throwable $e){$record['errors'][$key]=get_class($e).': '.$e->getMessage();}
            }
        }
        $products[]=$record;
    }
    $after=rehearsalTableHashes($connection);$changed=[];
    foreach(array_unique([...array_keys($before),...array_keys($after)]) as $table){
        if(($before[$table]??null)!==($after[$table]??null)){$changed[]=$table;requireRehearsal(isset($a['reindex']) && isRehearsalPriceIndex($table),'Unexpected non-index write: '.$table);}
    }
    saveRehearsal($a['output'],['versions'=>$isolation['versions'],'database'=>$isolation['database'],'products'=>$products,
        'price_index'=>$connection->fetchAll('SELECT p.sku,i.* FROM catalog_product_index_price i JOIN catalog_product_entity p ON p.entity_id=i.entity_id ORDER BY i.entity_id,i.website_id,i.customer_group_id'),
        'before_table_hashes'=>$before,'after_table_hashes'=>$after,'changed_tables'=>$changed,'reindexed'=>isset($a['reindex']),
        'probe_sha256'=>hash_file('sha256',__FILE__),'runtime_sha256'=>hash_file('sha256',__DIR__.'/rehearsal_runtime.php'),'plan_sha256'=>hash_file('sha256',$a['plan']),
        'configuration'=>'isolated USD defaults, guest group zero, captured product prices and scoped catalog-rule price rows',
        'live_writes'=>false,'storefront_verified'=>false,'cart_verified'=>false]);
}catch(Throwable $e){rehearsalFailure($a,$e,isset($before,$connection)?['before_table_hashes'=>$before,'after_table_hashes'=>rehearsalTableHashes($connection),'accepted'=>false,'live_writes'=>false]:[]);}
