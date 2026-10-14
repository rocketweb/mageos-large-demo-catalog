<?php

declare(strict_types=1);

$root = realpath($argv[1] ?? '');
if ($root === false || !is_file($root . '/app/etc/env.php')) {
    throw new RuntimeException('Pass the root of a disposable Mage-OS navigation fixture.');
}
$env = require $root . '/app/etc/env.php';
if (!str_starts_with($env['db']['connection']['default']['dbname'], 'wands_navigation_')) {
    throw new RuntimeException('This check requires a disposable wands_navigation_ database.');
}
require $root . '/app/bootstrap.php';
$om = \Magento\Framework\App\Bootstrap::create(BP, $_SERVER)->getObjectManager();
$om->get(\Magento\Framework\App\State::class)->setAreaCode('adminhtml');
$resource = $om->get(\Magento\Catalog\Model\ResourceModel\Category::class);
$db = $resource->getConnection();
$rootId = (int)$db->fetchOne("SELECT g.root_category_id FROM store_group g JOIN store_website w ON w.website_id=g.website_id WHERE w.code='wands'");
$collectionFactory = $om->get(\Magento\Catalog\Model\ResourceModel\Category\CollectionFactory::class);
$child = static function (int $parentId, string $name) use ($collectionFactory) {
    $collection = $collectionFactory->create();
    $collection->setStoreId(0);
    return $collection->addAttributeToSelect('name')->addAttributeToFilter('name', $name)
        ->addFieldToFilter('parent_id', $parentId)->setPageSize(1)->getFirstItem();
};
$decor = $child($rootId, 'Decor');
$lighting = $child((int)$decor->getId(), 'Lighting');
$parent = $om->get(\Magento\Catalog\Model\CategoryFactory::class)->create()->setStoreId(0)->load($rootId);
if (!$decor->getId() || !$lighting->getId() || $parent->getName() !== 'WANDS Catalog') {
    throw new RuntimeException('The fixture must already have Lighting under Decor.');
}
$factory = $om->get(\Magento\CatalogImportExport\Model\Import\ProductFactory::class);
$first = $factory->create();
$db->beginTransaction();
try {
    $resource->changeParent($lighting, $parent, null);
    $expectedPath = $lighting->getPath();
    $second = $factory->create();
    $actualPath = $second->getCategoryProcessor()->getCategoryById($lighting->getId())->getPath();
    if ($actualPath !== $expectedPath) {
        throw new RuntimeException('Second import reused a stale parent path: ' . $actualPath . ', expected ' . $expectedPath);
    }
    echo "Second importer reads the current parent path; fixture changes rolled back.\n";
} finally {
    $db->rollBack();
}
