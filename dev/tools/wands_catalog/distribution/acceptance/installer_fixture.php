<?php
declare(strict_types=1);

$request = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
$root = realpath($request['root']);
$env = require $root . '/app/etc/env.php';
if (!str_starts_with($env['db']['connection']['default']['dbname'], 'wands_installer_')) {
    throw new RuntimeException('This fixture accepts only a disposable wands_installer_ database.');
}
require $root . '/app/bootstrap.php';
$manager = \Magento\Framework\App\Bootstrap::create(BP, $_SERVER)->getObjectManager();
$manager->get(\Magento\Framework\App\State::class)->setAreaCode('adminhtml');
$resource = $manager->get(\Magento\Framework\App\ResourceConnection::class);
$db = $resource->getConnection();
if ($request['action'] === 'seed-old') {
    $category = $manager->get(\Magento\Catalog\Model\CategoryFactory::class)->create();
    $category->setName('Old fixture category')->setParentId(2)->setPath('1/2')->setIsActive(true);
    $manager->get(\Magento\Catalog\Api\CategoryRepositoryInterface::class)->save($category);
    $product = $manager->get(\Magento\Catalog\Model\ProductFactory::class)->create();
    $product->setSku('OLD-TEST')->setName('Old fixture product')->setTypeId('simple')->setAttributeSetId(4)
        ->setPrice(17)->setStatus(1)->setVisibility(4)->setWebsiteIds([1])->setCategoryIds([$category->getId()])
        ->setStockData(['qty' => 2, 'is_in_stock' => true]);
    $manager->get(\Magento\Catalog\Api\ProductRepositoryInterface::class)->save($product);
} elseif ($request['action'] === 'stock') {
    $registry = $manager->get(\Magento\CatalogInventory\Api\StockRegistryInterface::class);
    $item = $registry->getStockItemBySku($request['sku']);
    $item->setQty($request['qty']);
    $registry->updateStockItemBySku($request['sku'], $item);
    $source = $manager->get(\Magento\InventoryApi\Api\Data\SourceItemInterfaceFactory::class)->create();
    $source->setSku($request['sku']);
    $source->setSourceCode('default');
    $source->setQuantity($request['qty']);
    $source->setStatus(1);
    $manager->get(\Magento\InventoryApi\Api\SourceItemsSaveInterface::class)->execute([$source]);
    $builder = $manager->get(\Magento\InventoryReservationsApi\Model\ReservationBuilderInterface::class);
    $builder->setStockId(1);
    $builder->setSku($request['sku']);
    $builder->setQuantity(-3.0);
    $builder->setMetadata(json_encode(['event_type' => 'order_placed', 'object_type' => 'order', 'object_id' => 'synthetic-fixture']));
    $manager->get(\Magento\InventoryReservationsApi\Model\AppendReservationsInterface::class)->execute([$builder->build()]);
} elseif ($request['action'] === 'name') {
    $product = $manager->get(\Magento\Catalog\Api\ProductRepositoryInterface::class)->get($request['sku'], false, 0);
    $product->setName($request['name']);
    $manager->get(\Magento\Catalog\Model\ResourceModel\Product::class)->saveAttribute($product, 'name');
} elseif ($request['action'] === 'gallery-caption') {
    $product = $manager->get(\Magento\Catalog\Api\ProductRepositoryInterface::class)->get($request['sku']);
    $storeId = (int)$manager->get(\Magento\Store\Model\StoreManagerInterface::class)->getStore('wands')->getId();
    $table = $resource->getTableName('catalog_product_entity_media_gallery_value');
    $condition = ['entity_id = ?' => (int)$product->getId(), 'store_id = ?' => $storeId];
    if ($request['caption'] === null) {
        $db->delete($table, [...$condition, 'label = ?' => 'Synthetic installer guard caption']);
    } else {
        if ($db->fetchOne($db->select()->from($table, ['COUNT(*)'])->where('entity_id = ?', $product->getId())->where('store_id = ?', $storeId))) {
            throw new RuntimeException('The disposable gallery already has a store override.');
        }
        $row = $db->fetchRow($db->select()->from($table)->where('entity_id = ?', $product->getId())->where('store_id = 0')->limit(1));
        if (!$row) {
            throw new RuntimeException('The disposable gallery has no default image.');
        }
        $row['store_id'] = $storeId;
        $row['label'] = 'Synthetic installer guard caption';
        unset($row['record_id']);
        $db->insert($table, $row);
    }
} elseif ($request['action'] !== 'observe') {
    throw new RuntimeException('Unknown fixture action.');
}
echo json_encode(['products' => (int)$db->fetchOne($db->select()->from($resource->getTableName('catalog_product_entity'), ['COUNT(*)'])),
    'queued_reservation_cleanup' => (int)$db->fetchOne($db->select()->from($resource->getTableName('queue_message'), ['COUNT(*)'])->where('topic_name = ?', 'inventory.reservations.cleanup')),
    'stock_rows' => $db->fetchAll($db->select()->from(['s' => $resource->getTableName('cataloginventory_stock_item')], ['qty'])
        ->join(['p' => $resource->getTableName('catalog_product_entity')], 'p.entity_id=s.product_id', ['sku'])),
    'source_rows' => $db->fetchAll($db->select()->from($resource->getTableName('inventory_source_item'), ['sku', 'quantity', 'status']))], JSON_THROW_ON_ERROR) . PHP_EOL;
