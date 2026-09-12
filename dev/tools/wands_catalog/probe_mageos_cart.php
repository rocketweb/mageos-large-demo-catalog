<?php
declare(strict_types=1);
require __DIR__.'/rehearsal_runtime.php';

$a=getopt('',['root:','output:','plan:','candidates:']);
try{
    [$om,$connection,$isolation,$entities]=openRehearsal($a);
    $candidates=json_decode(file_get_contents($a['candidates']),true,512,JSON_THROW_ON_ERROR);
    $ids=array_column($entities,'entity_id','sku');$cases=[];
    requireRehearsal(count($candidates['active'])===13 && count($candidates['retired'])===4,'Wrong candidate coverage');
    foreach($candidates['active'] as $candidate){
        if($candidate['kind']==='configurable'){continue;}
        $sku=$candidate['sku'];requireRehearsal(isset($ids[$sku]),'Unexpected candidate');
        $parent=$candidate['parent_sku']??$sku;$options=[];
        if($parent!==$sku){
            $child=$om->create(\Magento\Catalog\Model\Product::class)->setStoreId(2);$child->load($ids[$sku]);
            foreach($candidate['variant_options'] as $code=>$label){
                $attribute=$om->get(\Magento\Eav\Model\Config::class)->getAttribute('catalog_product',$code);
                requireRehearsal($child->getAttributeText($code)===$label,'Candidate/live option mismatch');
                $options[(string)$attribute->getAttributeId()]=$child->getData($code);
            }
        }
        $cases[]=['id'=>'valid-'.$sku,'sku'=>$parent,'selected_sku'=>$sku,'qty'=>1,'options'=>$options,'expected'=>true];
    }
    foreach($candidates['active'] as $candidate){
        if($candidate['kind']!=='configurable'){continue;}
        $code=$candidate['axes'][0]['attribute'];$attribute=$om->get(\Magento\Eav\Model\Config::class)->getAttribute('catalog_product',$code);
        $cases[]=['id'=>'missing-'.$candidate['sku'],'sku'=>$candidate['sku'],'qty'=>1,'options'=>[],'expected'=>false];
        $cases[]=['id'=>'invalid-'.$candidate['sku'],'sku'=>$candidate['sku'],'qty'=>1,'options'=>[(string)$attribute->getAttributeId()=>-999],'expected'=>false];
    }
    foreach($candidates['retired'] as $candidate){$cases[]=['id'=>'retired-'.$candidate['sku'],'sku'=>$candidate['sku'],'qty'=>1,'options'=>[],'expected'=>false];}
    foreach([47,48] as $qty){$cases[]=['id'=>'nursery-qty-'.$qty,'sku'=>'WANDS-000056','selected_sku'=>'WANDS-000056','qty'=>$qty,'options'=>[],'expected'=>$qty===47];}
    $before=rehearsalTableHashes($connection);$results=[];
    $store=$om->get(\Magento\Store\Model\StoreManagerInterface::class)->getStore(2);
    foreach($cases as $case){
        $quote=$om->create(\Magento\Quote\Model\Quote::class)->setStore($store)->setCustomerIsGuest(true)->setCustomerGroupId(0);
        $quote->setBaseCurrencyCode('USD')->setQuoteCurrencyCode('USD')->setStoreCurrencyCode('USD')->setBaseToQuoteRate(1)->setStoreToBaseRate(1);
        $product=$om->create(\Magento\Catalog\Model\Product::class)->setStoreId(2)->setCustomerGroupId(0);$product->load($ids[$case['sku']]);
        $result=$case+['accepted'=>false,'message'=>null,'exception'=>null,'items'=>[]];
        try{
            $item=$quote->addProduct($product,new \Magento\Framework\DataObject(['qty'=>$case['qty'],'super_attribute'=>$case['options']]));
            if(is_string($item)){$result['message']=$item;}
            else{
                $result['accepted']=true;
                foreach($quote->getAllItems() as $quoteItem){
                    $quoteItem->calcRowTotal();
                    $result['items'][]=['product_id'=>$quoteItem->getProductId(),'product_type'=>$quoteItem->getProductType(),'parent_product_id'=>$quoteItem->getParentItem()?->getProductId(),
                        'product_sku'=>$quoteItem->getProduct()->getSku(),'item_sku'=>$quoteItem->getSku(),'parent_sku'=>$quoteItem->getParentItem()?->getProduct()->getSku(),
                        'qty'=>$quoteItem->getQty(),'unit_price'=>$quoteItem->getCalculationPrice(),'row_total'=>$quoteItem->getRowTotal(),'has_error'=>$quoteItem->getHasError()];
                }
            }
        }catch(Throwable $e){$result['exception']=get_class($e);$result['message']=$e->getMessage();}
        requireRehearsal(!$quote->getId(),'A quote was unexpectedly persisted');
        $results[]=$result;
    }
    $after=rehearsalTableHashes($connection);
    requireRehearsal($before===$after,'Cart probe changed database rows');
    saveRehearsal($a['output'],['versions'=>$isolation['versions'],'database'=>$isolation['database'],'cases'=>$results,
        'before_table_hashes'=>$before,'after_table_hashes'=>$after,'database_unchanged'=>true,
        'probe_sha256'=>hash_file('sha256',__FILE__),'runtime_sha256'=>hash_file('sha256',__DIR__.'/rehearsal_runtime.php'),
        'candidates_sha256'=>hash_file('sha256',$a['candidates']),'plan_sha256'=>hash_file('sha256',$a['plan']),
        'cart_model_exercised'=>true,'quotes_saved'=>0,'orders_created'=>0,'reservations_created'=>0,
        'configuration'=>'unsaved guest quotes; isolated USD defaults; no address, shipping or total collection',
        'storefront_verified'=>false,'checkout_verified'=>false,'live_writes'=>false]);
}catch(Throwable $e){rehearsalFailure($a,$e,isset($before,$connection)?['before_table_hashes'=>$before,'after_table_hashes'=>rehearsalTableHashes($connection),'accepted'=>false,'live_writes'=>false]:[]);}
