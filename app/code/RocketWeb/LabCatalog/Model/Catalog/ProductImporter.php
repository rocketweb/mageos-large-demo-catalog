<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Model\Catalog;

use Magento\Framework\App\Area;
use Magento\Framework\App\Filesystem\DirectoryList;
use Magento\Framework\App\State;
use Magento\ImportExport\Model\Import;
use Magento\ImportExport\Model\Import\ErrorProcessing\ProcessingError;

class ProductImporter
{
    public function __construct(
        private readonly \Magento\ImportExport\Model\ImportFactory $importFactory,
        private readonly \Magento\ImportExport\Model\Import\Source\CsvFactory $csvFactory,
        private readonly \Magento\Framework\Filesystem $filesystem,
        private readonly State $appState,
        private readonly \Magento\Framework\App\ResourceConnection $resourceConnection,
        private readonly BundleAssortmentReconciler $bundleAssortmentReconciler,
        private readonly \RocketWeb\LabCatalog\Model\Catalog\StockPreservation $stockPreservation,
    ) {
    }

    public function execute(
        string $sourceFile,
        bool $validateOnly = false,
        bool $reconcileBundles = false,
        bool $preserveExistingStock = false,
    ): array
    {
        return $this->appState->emulateAreaCode(
            Area::AREA_ADMINHTML,
            fn(): array => $preserveExistingStock
                ? $this->stockPreservation->execute(
                    $this->existingWandsSkus($sourceFile),
                    fn(): array => $this->import($sourceFile, $validateOnly, $reconcileBundles)
                )
                : $this->import($sourceFile, $validateOnly, $reconcileBundles)
        );
    }

    private function existingWandsSkus(string $sourceFile): array
    {
        $root = rtrim($this->filesystem->getDirectoryRead(DirectoryList::ROOT)->getAbsolutePath(), '/') . '/';
        $path = realpath($sourceFile);
        if ($path === false || !is_file($path) || !str_starts_with($path, $root)) {
            throw new \RuntimeException('Product import CSV must be inside the Mage-OS project root.');
        }
        $stream = fopen($path, 'r');
        if ($stream === false) {
            throw new \RuntimeException('Cannot read product import CSV.');
        }
        $skus = [];
        try {
            $header = fgetcsv($stream, null, ',', '"', '');
            $column = is_array($header) ? array_search('sku', $header, true) : false;
            if ($column === false) {
                throw new \RuntimeException('Product import CSV has no SKU column.');
            }
            while (($row = fgetcsv($stream, null, ',', '"', '')) !== false) {
                if ($row === [null]) {
                    continue;
                }
                $sku = $row[$column] ?? '';
                if (!str_starts_with($sku, 'WANDS-')) {
                    throw new \RuntimeException('Stock preservation accepts only WANDS product rows.');
                }
                $skus[$sku] = true;
            }
        } finally {
            fclose($stream);
        }
        $db = $this->resourceConnection->getConnection();
        $existing = [];
        foreach (array_chunk(array_keys($skus), 1000) as $batch) {
            $select = $db->select()
                ->from(['p' => $this->resourceConnection->getTableName('catalog_product_entity')], ['sku'])
                ->joinLeft(['w' => $this->resourceConnection->getTableName('catalog_product_website')],
                    'w.product_id = p.entity_id', [])
                ->joinLeft(['s' => $this->resourceConnection->getTableName('store_website')],
                    's.website_id = w.website_id', ['code'])
                ->where('p.sku IN (?)', $batch);
            foreach ($db->fetchAll($select) as $row) {
                if ($row['code'] !== 'wands') {
                    throw new \RuntimeException('Existing SKU is unassigned or shared outside the WANDS website.');
                }
                $existing[$row['sku']] = true;
            }
        }
        return array_keys($existing);
    }

    private function import(string $sourceFile, bool $validateOnly, bool $reconcileBundles): array
    {
        $absolutePath = realpath($sourceFile);

        if ($absolutePath === false || !is_file($absolutePath)) {
            throw new \RuntimeException('Product import CSV does not exist: ' . $sourceFile);
        }

        $rootDirectory = $this->filesystem->getDirectoryRead(DirectoryList::ROOT);
        $rootPath = rtrim($rootDirectory->getAbsolutePath(), DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR;

        if (!str_starts_with($absolutePath, $rootPath)) {
            throw new \RuntimeException('Product import CSV must be inside the Mage-OS project root.');
        }

        $import = $this->importFactory->create();
        $import->setData([
            'entity' => 'catalog_product',
            'behavior' => Import::BEHAVIOR_APPEND,
            Import::FIELD_NAME_VALIDATION_STRATEGY => 'validation-stop-on-errors',
            Import::FIELD_NAME_ALLOWED_ERROR_COUNT => 100,
            Import::FIELD_FIELD_SEPARATOR => ',',
            Import::FIELD_FIELD_MULTIPLE_VALUE_SEPARATOR => ',',
            Import::FIELD_EMPTY_ATTRIBUTE_VALUE_CONSTANT => Import::DEFAULT_EMPTY_ATTRIBUTE_VALUE_CONSTANT,
            Import::FIELDS_ENCLOSURE => 1,
            Import::FIELD_NAME_IMG_FILE_DIR => 'pub/media/import',
            'images_base_directory' => $rootDirectory,
        ]);
        $source = $this->csvFactory->create([
            'file' => $absolutePath,
            'directory' => $rootDirectory,
        ]);

        if (!$import->validateSource($source)) {
            throw new \RuntimeException($this->formatErrors($import));
        }

        if ($validateOnly) {
            return [
                'validated_only' => true,
                'processed_rows' => $import->getProcessedRowsCount(),
                'invalid_rows' => $import->getErrorAggregator()->getInvalidRowsCount(),
                'errors' => $import->getErrorAggregator()->getErrorsCount(),
                'error_messages' => $this->errorMessages($import),
                'bundle_reconciliation' => $reconcileBundles
                    ? $this->bundleAssortmentReconciler->inspectExisting($sourceFile)
                    : null,
            ];
        }

        $connection = $this->resourceConnection->getConnection();
        $reconciliation = null;
        if ($reconcileBundles) {
            $connection->beginTransaction();
        }
        try {
            if ($reconcileBundles) {
                $reconciliation = $this->bundleAssortmentReconciler->deleteExisting($sourceFile);
            }
            if (!$import->importSource() || $import->getErrorAggregator()->getErrorsCount() > 0) {
                throw new \RuntimeException($this->formatErrors($import));
            }
            if ($reconcileBundles) {
                $connection->commit();
            }
        } catch (\Throwable $exception) {
            if ($reconcileBundles && $connection->getTransactionLevel() > 0) {
                $connection->rollBack();
            }
            throw $exception;
        }

        $import->invalidateIndex();

        return [
            'validated_only' => false,
            'processed_rows' => $import->getProcessedRowsCount(),
            'processed_entities' => $import->getProcessedEntitiesCount(),
            'invalid_rows' => $import->getErrorAggregator()->getInvalidRowsCount(),
            'errors' => $import->getErrorAggregator()->getErrorsCount(),
            'error_messages' => $this->errorMessages($import),
            'bundle_reconciliation' => $reconciliation,
        ];
    }

    private function formatErrors(Import $import): string
    {
        $messages = $this->errorMessages($import);

        if ($messages === []) {
            return 'Product import failed without a detailed validation error.';
        }

        return implode(PHP_EOL, $messages);
    }

    private function errorMessages(Import $import): array
    {
        $messages = [];

        foreach ($import->getErrorAggregator()->getAllErrors() as $error) {
            if (!$error instanceof ProcessingError) {
                continue;
            }

            $messages[] = sprintf(
                'row %s: %s',
                $error->getRowNumber() ?? 'n/a',
                $error->getErrorMessage()
            );

            if (count($messages) === 20) {
                break;
            }
        }

        return $messages;
    }
}
