<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Model\Catalog;

use Magento\Bundle\Model\Product\Type as BundleType;
use Magento\Framework\App\Filesystem\DirectoryList;

class BundleAssortmentReconciler
{
    private const MAX_BUNDLES = 50;

    public function __construct(
        private readonly \Magento\Framework\App\ResourceConnection $resourceConnection,
        private readonly \Magento\Framework\Filesystem $filesystem,
        private readonly \Magento\Framework\Filesystem\Driver\File $filesystemDriver,
    ) {
    }

    public function deleteExisting(string $sourceFile): array
    {
        return $this->analyze($sourceFile, true);
    }

    public function inspectExisting(string $sourceFile): array
    {
        return $this->analyze($sourceFile, false);
    }

    private function analyze(string $sourceFile, bool $delete): array
    {
        $skus = $this->bundleSkus($sourceFile);
        $connection = $this->resourceConnection->getConnection();
        $entityTable = $this->resourceConnection->getTableName('catalog_product_entity');
        $select = $connection->select()
            ->from($entityTable, ['entity_id', 'sku', 'type_id'])
            ->where('sku IN (?)', $skus);
        if ($delete) {
            $select->forUpdate(true);
        }
        $products = $connection->fetchAll($select);
        if (count($products) !== count($skus)) {
            throw new \RuntimeException('One or more bundle SKUs do not exist.');
        }
        foreach ($products as $product) {
            if ((string)$product['type_id'] !== BundleType::TYPE_CODE) {
                throw new \RuntimeException(sprintf('Product %s is not a bundle.', $product['sku']));
            }
        }

        $parentIds = array_map('intval', array_column($products, 'entity_id'));
        $counts = [
            'bundle_products' => count($parentIds),
            'options_removed' => $this->count('catalog_product_bundle_option', 'parent_id', $parentIds),
            'option_values_removed' => $this->count(
                'catalog_product_bundle_option_value',
                'parent_product_id',
                $parentIds
            ),
            'selections_removed' => $this->count(
                'catalog_product_bundle_selection',
                'parent_product_id',
                $parentIds
            ),
            'selection_prices_removed' => $this->count(
                'catalog_product_bundle_selection_price',
                'parent_product_id',
                $parentIds
            ),
            'relations_removed' => $this->count('catalog_product_relation', 'parent_id', $parentIds),
        ];
        $counts['write_performed'] = $delete;
        if ($delete) {
            $connection->delete(
                $this->resourceConnection->getTableName('catalog_product_relation'),
                ['parent_id IN (?)' => $parentIds]
            );
            $connection->delete(
                $this->resourceConnection->getTableName('catalog_product_bundle_option'),
                ['parent_id IN (?)' => $parentIds]
            );
        }
        return $counts;
    }

    private function count(string $table, string $column, array $parentIds): int
    {
        $connection = $this->resourceConnection->getConnection();
        return (int)$connection->fetchOne(
            $connection->select()
                ->from($this->resourceConnection->getTableName($table), ['records' => 'COUNT(*)'])
                ->where($column . ' IN (?)', $parentIds)
        );
    }

    private function bundleSkus(string $sourceFile): array
    {
        $absolutePath = $this->filesystemDriver->getRealPath($sourceFile);
        if ($absolutePath === false || !$this->filesystemDriver->isFile($absolutePath)) {
            throw new \RuntimeException('Bundle import CSV does not exist: ' . $sourceFile);
        }
        $rootDirectory = $this->filesystem->getDirectoryRead(DirectoryList::ROOT);
        $rootPath = rtrim($rootDirectory->getAbsolutePath(), DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR;
        if (!str_starts_with($absolutePath, $rootPath)) {
            throw new \RuntimeException('Bundle import CSV must be inside the Mage-OS project root.');
        }

        $file = new \SplFileObject($absolutePath, 'r');
        $file->setFlags(\SplFileObject::READ_CSV | \SplFileObject::SKIP_EMPTY);
        $file->setCsvControl(',', '"', '');
        $header = $file->fgetcsv();
        if (!is_array($header) || !in_array('sku', $header, true) || !in_array('product_type', $header, true)) {
            throw new \RuntimeException('Bundle import CSV is missing required columns.');
        }
        $skuIndex = array_search('sku', $header, true);
        $typeIndex = array_search('product_type', $header, true);
        $skus = [];
        while (!$file->eof()) {
            $row = $file->fgetcsv();
            if (!is_array($row) || $row === [null]) {
                continue;
            }
            $sku = (string)($row[$skuIndex] ?? '');
            if (($row[$typeIndex] ?? '') !== BundleType::TYPE_CODE
                || preg_match('/^WANDS-BUNDLE-\d{3}$/', $sku) !== 1
            ) {
                throw new \RuntimeException('Reconciliation accepts only bounded WANDS bundle rows.');
            }
            if (isset($skus[$sku])) {
                throw new \RuntimeException('Bundle import CSV repeats SKU ' . $sku . '.');
            }
            $skus[$sku] = true;
        }
        if ($skus === [] || count($skus) > self::MAX_BUNDLES) {
            throw new \RuntimeException('Bundle reconciliation requires between 1 and 50 unique bundles.');
        }
        return array_keys($skus);
    }
}
