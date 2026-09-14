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
    ) {
    }

    public function execute(string $sourceFile, bool $validateOnly = false, bool $reconcileBundles = false): array
    {
        return $this->appState->emulateAreaCode(
            Area::AREA_ADMINHTML,
            fn(): array => $this->import($sourceFile, $validateOnly, $reconcileBundles)
        );
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
