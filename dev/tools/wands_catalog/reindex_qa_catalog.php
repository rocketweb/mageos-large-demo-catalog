<?php
declare(strict_types=1);
$a = getopt('', ['root:']); $root = realpath($a['root'] ?? '');
if (!in_array($root, ['/Users/matt/code/mageos-latest', '/var/www/html'], true)) { throw new RuntimeException('Existing store required'); }
require $root . '/app/bootstrap.php';
$om = \Magento\Framework\App\Bootstrap::create($root, $_SERVER)->getObjectManager();
$om->get(\Magento\Framework\App\State::class)->setAreaCode('adminhtml');
$r = $om->get(\Magento\Framework\App\ResourceConnection::class); $db = $r->getConnection();
$ids = array_map('intval', $db->fetchCol('SELECT entity_id FROM ' . $r->getTableName('catalog_product_entity') . " WHERE LEFT(sku,9)='WANDS-QA-'") );
if (count($ids) !== 127) { throw new RuntimeException('Exactly 127 QA records required'); }
$registry = $om->get(\Magento\Framework\Indexer\IndexerRegistry::class); $done = [];
foreach (['cataloginventory_stock', 'catalog_product_price', 'catalog_product_attribute', 'catalog_product_category', 'catalogsearch_fulltext'] as $name) {
    $registry->get($name)->reindexList($ids); $done[] = $name;
    fwrite(STDERR, 'Updated QA rows: ' . $name . "\n");
}
echo json_encode(['root' => $root, 'product_ids' => $ids, 'products' => 127, 'indexes' => $done], JSON_THROW_ON_ERROR) . "\n";
