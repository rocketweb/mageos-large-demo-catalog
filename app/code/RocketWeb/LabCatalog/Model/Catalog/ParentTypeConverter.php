<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Model\Catalog;

use Magento\Catalog\Api\Data\ProductInterface;
use Magento\Catalog\Model\Product\Type as ProductType;
use Magento\ConfigurableProduct\Model\Product\Type\Configurable;
use Magento\Framework\App\Filesystem\DirectoryList;

class ParentTypeConverter
{
    private const MAX_BATCH_SIZE = 500;

    public function __construct(
        private readonly \Magento\Framework\App\ResourceConnection $resourceConnection,
        private readonly \Magento\Framework\Filesystem $filesystem,
        private readonly \Magento\Framework\Filesystem\Driver\File $filesystemDriver,
        private readonly \Magento\Catalog\Api\ProductRepositoryInterface $productRepository,
        private readonly \Magento\Framework\EntityManager\MetadataPool $metadataPool,
    ) {
    }

    public function execute(
        string $sourceFile,
        int $offset,
        int $limit,
        bool $dryRun,
        bool $reverse,
    ): array {
        if ($offset < 0) {
            throw new \InvalidArgumentException('Offset must be zero or greater.');
        }
        if ($limit < 1 || $limit > self::MAX_BATCH_SIZE) {
            throw new \InvalidArgumentException(sprintf('Limit must be between 1 and %d.', self::MAX_BATCH_SIZE));
        }

        $records = $this->readRecords($sourceFile, $offset, $limit);
        $result = [
            'offset' => $offset,
            'requested_limit' => $limit,
            'selected_records' => count($records),
            'dry_run' => $dryRun,
            'reverse' => $reverse,
            'converted' => 0,
            'already_target_type' => 0,
            'validated_children' => 0,
            'next_offset' => $offset + count($records),
        ];

        foreach ($records as $record) {
            $recordResult = $this->convertRecord($record, $dryRun, $reverse);
            $result['converted'] += $recordResult['converted'];
            $result['already_target_type'] += $recordResult['already_target_type'];
            $result['validated_children'] += $recordResult['validated_children'];
        }

        return $result;
    }

    private function convertRecord(array $record, bool $dryRun, bool $reverse): array
    {
        $expectedType = $reverse ? $record['target_type'] : $record['expected_type'];
        $targetType = $reverse ? $record['expected_type'] : $record['target_type'];
        $connection = $this->resourceConnection->getConnection();
        $entityTable = $this->resourceConnection->getTableName('catalog_product_entity');
        $metadata = $this->metadataPool->getMetadata(ProductInterface::class);
        $identifierField = $metadata->getIdentifierField();
        $linkField = $metadata->getLinkField();

        if (!$dryRun) {
            $connection->beginTransaction();
        }

        try {
            $select = $connection->select()
                ->from($entityTable)
                ->where('sku = ?', $record['sku']);
            if (!$dryRun) {
                $select->forUpdate(true);
            }
            $parent = $connection->fetchRow($select);
            if (!is_array($parent)) {
                throw new \RuntimeException(sprintf('Parent SKU %s does not exist.', $record['sku']));
            }

            $product = $this->productRepository->get($record['sku'], false, null, true);
            if ((string)$product->getData('wands_product_id') !== (string)$record['source_product_id']) {
                throw new \RuntimeException(sprintf(
                    'Parent SKU %s has an unexpected WANDS product ID.',
                    $record['sku']
                ));
            }

            $currentType = (string)$parent['type_id'];
            if ($currentType === $targetType) {
                $children = $reverse ? [] : $this->loadChildren($record['child_skus']);
                if (!$dryRun) {
                    $connection->commit();
                }
                return [
                    'converted' => 0,
                    'already_target_type' => 1,
                    'validated_children' => count($children),
                ];
            }
            if ($currentType !== $expectedType) {
                throw new \RuntimeException(sprintf(
                    'Parent SKU %s has type %s; expected %s.',
                    $record['sku'],
                    $currentType,
                    $expectedType
                ));
            }

            $children = $this->loadChildren($record['child_skus']);
            if (!$dryRun) {
                if ($reverse) {
                    $this->removeConfigurableRelations((int)$parent[$linkField], $children);
                }
                $connection->update(
                    $entityTable,
                    ['type_id' => $targetType],
                    [$identifierField . ' = ?' => (int)$parent[$identifierField]]
                );
                $connection->commit();
            }

            return [
                'converted' => $dryRun ? 0 : 1,
                'already_target_type' => 0,
                'validated_children' => count($children),
            ];
        } catch (\Throwable $exception) {
            if (!$dryRun && $connection->getTransactionLevel() > 0) {
                $connection->rollBack();
            }
            throw $exception;
        }
    }

    private function loadChildren(array $childSkus): array
    {
        if ($childSkus === []) {
            throw new \RuntimeException('A configurable parent record must contain child SKUs.');
        }

        $connection = $this->resourceConnection->getConnection();
        $select = $connection->select()
            ->from(
                $this->resourceConnection->getTableName('catalog_product_entity'),
                ['entity_id', 'sku', 'type_id']
            )
            ->where('sku IN (?)', $childSkus);
        $children = $connection->fetchAll($select);

        if (count($children) !== count($childSkus)) {
            throw new \RuntimeException('One or more planned configurable children do not exist.');
        }
        foreach ($children as $child) {
            if ((string)$child['type_id'] !== ProductType::TYPE_SIMPLE) {
                throw new \RuntimeException(sprintf(
                    'Configurable child %s is not a simple product.',
                    $child['sku']
                ));
            }
        }

        return $children;
    }

    private function removeConfigurableRelations(int $parentLinkId, array $children): void
    {
        $connection = $this->resourceConnection->getConnection();
        $connection->delete(
            $this->resourceConnection->getTableName('catalog_product_super_link'),
            ['parent_id = ?' => $parentLinkId]
        );
        if ($children !== []) {
            $connection->delete(
                $this->resourceConnection->getTableName('catalog_product_relation'),
                [
                    'parent_id = ?' => $parentLinkId,
                    'child_id IN (?)' => array_column($children, 'entity_id'),
                ]
            );
        }
        $connection->delete(
            $this->resourceConnection->getTableName('catalog_product_super_attribute'),
            ['product_id = ?' => $parentLinkId]
        );
    }

    private function readRecords(string $sourceFile, int $offset, int $limit): array
    {
        $absolutePath = $this->filesystemDriver->getRealPath($sourceFile);
        if ($absolutePath === false || !$this->filesystemDriver->isFile($absolutePath)) {
            throw new \RuntimeException('Parent conversion manifest does not exist: ' . $sourceFile);
        }

        $rootDirectory = $this->filesystem->getDirectoryRead(DirectoryList::ROOT);
        $rootPath = rtrim($rootDirectory->getAbsolutePath(), DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR;
        if (!str_starts_with($absolutePath, $rootPath)) {
            throw new \RuntimeException('Parent conversion manifest must be inside the Mage-OS project root.');
        }

        $records = [];
        $seenSkus = [];
        $stream = new \SplFileObject($absolutePath, 'r');
        $recordNumber = 0;
        while (!$stream->eof() && count($records) < $limit) {
            $line = trim((string)$stream->fgets());
            if ($line === '') {
                continue;
            }
            if ($recordNumber++ < $offset) {
                continue;
            }
            try {
                $record = json_decode($line, true, 512, JSON_THROW_ON_ERROR);
            } catch (\JsonException $exception) {
                throw new \RuntimeException(
                    sprintf('Invalid JSON on manifest record %d.', $recordNumber),
                    0,
                    $exception
                );
            }
            $this->validateRecord($record, $recordNumber);
            if (isset($seenSkus[$record['sku']])) {
                throw new \RuntimeException(sprintf(
                    'Duplicate parent SKU %s in selected manifest batch.',
                    $record['sku']
                ));
            }
            $seenSkus[$record['sku']] = true;
            $records[] = $record;
        }

        return $records;
    }

    private function validateRecord(mixed $record, int $recordNumber): void
    {
        if (!is_array($record)) {
            throw new \RuntimeException(sprintf('Manifest record %d is not an object.', $recordNumber));
        }
        foreach (['sku', 'source_product_id', 'expected_type', 'target_type', 'child_skus'] as $field) {
            if (!array_key_exists($field, $record)) {
                throw new \RuntimeException(sprintf(
                    'Manifest record %d is missing %s.',
                    $recordNumber,
                    $field
                ));
            }
        }
        if ($record['expected_type'] !== ProductType::TYPE_SIMPLE
            || $record['target_type'] !== Configurable::TYPE_CODE
            || !is_array($record['child_skus'])
            || !in_array(count($record['child_skus']), [4, 6], true)
        ) {
            throw new \RuntimeException(sprintf(
                'Manifest record %d has an unsupported type conversion.',
                $recordNumber
            ));
        }
        if (!is_string($record['sku'])
            || preg_match('/^WANDS-\d{6}$/', $record['sku']) !== 1
            || !is_string($record['source_product_id'])
            || !ctype_digit($record['source_product_id'])
        ) {
            throw new \RuntimeException(sprintf('Manifest record %d has an invalid parent identity.', $recordNumber));
        }
        if (count($record['child_skus']) !== count(array_unique($record['child_skus']))) {
            throw new \RuntimeException(sprintf('Manifest record %d repeats a child SKU.', $recordNumber));
        }
        foreach ($record['child_skus'] as $childSku) {
            if (!is_string($childSku) || !str_starts_with($childSku, $record['sku'] . '-')) {
                throw new \RuntimeException(sprintf('Manifest record %d has an invalid child SKU.', $recordNumber));
            }
        }
    }
}
