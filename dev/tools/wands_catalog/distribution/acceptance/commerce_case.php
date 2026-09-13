<?php
declare(strict_types=1);

require '/var/www/html/app/bootstrap.php';
$om = \Magento\Framework\App\Bootstrap::create(BP, $_SERVER)->getObjectManager();
$env = $om->get(\Magento\Framework\App\DeploymentConfig::class);
$database = $env->get('db/connection/default/dbname');
if (!in_array($database, ['lab_enriched_medium','lab_enriched_full'], true)
    || $env->get('db/connection/default/host') !== 'db') {
    throw new RuntimeException('Commerce cases require the isolated enriched database');
}
$om->get(\Magento\Framework\App\State::class)->setAreaCode('frontend');
$stores = $om->get(\Magento\Store\Model\StoreManagerInterface::class);
$store = $stores->getStore('wands');
$stores->setCurrentStore($store);
$priceWebsite = (int)$om->get(\Magento\Framework\App\Config\ScopeConfigInterface::class)
    ->getValue('catalog/price/scope') === 0 ? 0 : (int)$store->getWebsiteId();
$repository = $om->get(\Magento\Catalog\Api\ProductRepositoryInterface::class);
$stockRegistry = $om->get(\Magento\CatalogInventory\Api\StockRegistryInterface::class);
$attributeAction = $om->get(\Magento\Catalog\Model\ResourceModel\Product\Action::class);
$indexers = $om->get(\Magento\Framework\Indexer\IndexerRegistry::class);
$case = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
if (($case['apply_to'] ?? '') !== 'isolated disposable fixture only') {
    throw new RuntimeException('Unexpected fixture scope');
}
$report = ['id'=>$case['id'], 'kind'=>$case['kind'], 'database'=>$database, 'checks'=>[],
    'restored'=>false, 'host_clock_changed'=>false, 'orders_created'=>0];
$stockFields = ['manage_stock','use_config_manage_stock','qty','is_in_stock','backorders',
                'use_config_backorders','min_qty','use_config_min_qty'];
$productFields = ['special_price','special_from_date','special_to_date','tier_prices'];
$before = [];
$ids = [];
foreach ($case['changes'] as $sku => $changes) {
    if (array_diff(array_keys($changes), array_merge($stockFields,$productFields))) {
        throw new RuntimeException('Unsupported fixture fields');
    }
    $product = $repository->get($sku, false, 0, true);
    $stock = $stockRegistry->getStockItemBySku($sku);
    $ids[] = (int)$product->getId();
    $captureFields = array_keys($changes);
    // Whole-product saves can default an undated special price, including during a tier-price case.
    if (array_intersect($captureFields, $productFields)) {
        $captureFields = array_unique(array_merge($captureFields, $productFields));
    }
    foreach ($captureFields as $field) {
        $before[$sku][$field] = in_array($field,$stockFields,true) ? $stock->getData($field)
            : ($field === 'tier_prices' ? $product->getTierPrice() : $product->getData($field));
    }
}
$resource=$om->get(\Magento\Framework\App\ResourceConnection::class);
$connection=$resource->getConnection();
$inventorySnapshot=static function () use ($connection,$resource,$case): array {
    $result=[];
    $sourceTable=$resource->getTableName('inventory_source_item');
    if ($connection->isTableExists($sourceTable)) {
        $result['sources']=$connection->fetchAll($connection->select()->from($sourceTable)
            ->where('sku IN (?)',array_keys($case['changes']))->order(['sku','source_code']));
    }
    $reservationTable=$resource->getTableName('inventory_reservation');
    if ($connection->isTableExists($reservationTable)) {
        $result['reservations']=$connection->fetchAll($connection->select()->from($reservationTable)
            ->where('sku IN (?)',array_keys($case['changes']))->order('reservation_id'));
    }
    $result['orders']=(int)$connection->fetchOne('SELECT COUNT(*) FROM '.$resource->getTableName('sales_order'));
    return $result;
};
$inventoryBefore=$inventorySnapshot();
$receipt = BP . '/var/commerce/' . $database . '/' . preg_replace('/[^A-Za-z0-9_.-]/','_', $case['id']) . '.before.json';
if (!is_dir(dirname($receipt))) { mkdir(dirname($receipt), 0770, true); }
if (file_exists($receipt)) { throw new RuntimeException('Case already attempted; inspect before-state and recovery'); }
file_put_contents($receipt, json_encode(['fields'=>$before,'inventory'=>$inventoryBefore], JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR));
$apply = static function (array $changes, bool $restore) use ($repository,$stockRegistry,$stockFields,$priceWebsite,$attributeAction): void {
    foreach ($changes as $sku => $fields) {
        $product = $repository->get($sku, false, 0, true);
        $stock = $stockRegistry->getStockItemBySku($sku);
        $saveProduct = false;
        $saveStock = false;
        $restoredAttributes = [];
        foreach ($fields as $field => $value) {
            if (in_array($field,$stockFields,true)) {
                $stock->setData($field,$value); $saveStock=true;
            } elseif ($restore && $field !== 'tier_prices') {
                $restoredAttributes[$field] = $value;
            } else {
                if ($field === 'tier_prices') {
                    $value = $restore ? $value : array_map(static fn(array $tier): array => [
                        'website_id'=>$priceWebsite, 'cust_group'=>32000,
                        'price_qty'=>$tier['qty'], 'price'=>$tier['unit_price']], $value);
                    $product->setTierPrice($value);
                } else { $product->setData($field,$value === '' ? null : $value); }
                $saveProduct=true;
            }
        }
        if ($saveProduct) { $repository->save($product); }
        // Bypass SetSpecialPriceStartDate only for exact restoration of captured EAV values.
        // Run after tier-price saves so that their product-save observers cannot undo it.
        if ($restoredAttributes) {
            $attributeAction->updateAttributes([(int)$product->getId()], $restoredAttributes, 0);
        }
        if ($saveStock) { $stockRegistry->updateStockItemBySku($sku,$stock); }
    }
};
$reindex = static function () use ($indexers,$ids): void {
    foreach (['cataloginventory_stock','catalog_product_price'] as $id) {
        $indexers->get($id)->reindexList($ids);
    }
};
$check = static function (bool $valid, string $name) use (&$report): void {
    $report['checks'][]=['name'=>$name,'passed'=>$valid];
};
try {
    $changes=$case['changes'];
    $today=$om->get(\Magento\Framework\Stdlib\DateTime\TimezoneInterface::class)->date()->format('Y-m-d');
    foreach ($changes as &$fields) {
        if (isset($fields['special_from_date'])) {
            $fields['special_from_date']=date('Y-m-d 00:00:00',strtotime($today.' -14 days'));
            $fields['special_to_date']=date('Y-m-d 23:59:59',strtotime($today .
                ($case['kind']==='active-sale' ? ' +14 days' : ' -1 day')));
            $report['translated_dates']=['from'=>$fields['special_from_date'],'to'=>$fields['special_to_date'],
                'reference_clock'=>$case['clock'],'store_today'=>$today];
        }
    }
    unset($fields);
    $apply($changes,false);
    $reindex();
    $product=$repository->get($case['root_sku'],false,(int)$store->getId(),true);
    $expected=$case['expected'];
    if (isset($expected['unit_price_ex_tax'])) {
        $quantity=(float)($expected['quantity']??1);
        $price=(float)$product->getFinalPrice($quantity);
        $report['observed_unit_price']=$price;
        $check(abs($price-(float)$expected['unit_price_ex_tax'])<0.005,'native final price');
        if (isset($expected['line_total_ex_tax'])) {
            $check(abs($price*$quantity-(float)$expected['line_total_ex_tax'])<0.005,'quantity price total');
        }
    }
    if ($case['kind']==='out-of-stock') { $check(!$product->isSalable(),'product unavailable'); }
    if ($case['kind']==='unavailable-variant') {
        $child=$repository->get($expected['unavailable_child'],false,(int)$store->getId(),true);
        $check(!$child->isSalable(),'selected child unavailable');
    }
    if ($case['kind']==='required-bundle-option-unavailable') {
        $check(!$product->isSalable(),'required bundle option prevents purchase');
    }
    if ($case['kind']==='backorder-notify') {
        $result=$om->get(\Magento\CatalogInventory\Api\StockStateInterface::class)->checkQuoteItemQty(
            $product->getId(),1,1,1,$store->getWebsiteId());
        $report['backorder_result']=$result->getData();
        $check(!$result->getHasError() && (float)$result->getItemBackorders()>0,'quantity can backorder');
        $check((string)$result->getMessage()!=='','customer notification');
    }
} catch (Throwable $error) {
    $report['error_class']=get_class($error);
    $report['error']=$error->getMessage();
} finally {
    try {
        $apply($before,true);
        $reindex();
        $restored=true;
        foreach ($before as $sku=>$fields) {
            $product=$repository->get($sku,false,0,true);
            $stock=$stockRegistry->getStockItemBySku($sku);
            foreach ($fields as $field=>$value) {
                $actual=in_array($field,$stockFields,true) ? $stock->getData($field)
                    : ($field==='tier_prices' ? $product->getTierPrice() : $product->getData($field));
                $valid=$actual==$value;
                $check($valid,'restored '.$sku.':'.$field);
                $restored=$restored && $valid;
            }
        }
        $report['restored']=$restored;
        $inventoryAfter=$inventorySnapshot();
        $check($inventoryBefore===$inventoryAfter,'MSI source items and reservations restored; order count unchanged');
        $report['inventory_restored']=$inventoryBefore===$inventoryAfter;
        $report['orders_created']=$inventoryAfter['orders']-$inventoryBefore['orders'];
    } catch (Throwable $error) {
        $report['restore_error']=$error->getMessage();
    }
}
$report['status']=!isset($report['error']) && $report['restored']
    && !in_array(false,array_column($report['checks'],'passed'),true) ? 'passed' : 'failed';
echo json_encode($report, JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR), PHP_EOL;
exit($report['status']==='passed'?0:1);
