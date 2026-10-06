<?php
declare(strict_types=1);

namespace RocketWeb\LabCatalog\Plugin;

use Magento\CatalogImportExport\Model\StockItemProcessorInterface;

class PreserveExistingStock
{
    public function __construct(
        private readonly \RocketWeb\LabCatalog\Model\Catalog\StockPreservation $stockPreservation,
    ) {
    }

    public function aroundProcess(
        StockItemProcessorInterface $subject,
        callable $proceed,
        array $stockData,
        array $importedData,
    ): void {
        if (!$this->stockPreservation->isActive()) {
            $proceed($stockData, $importedData);
            return;
        }
        $stockData = $this->stockPreservation->filter($stockData);
        $importedData = $this->stockPreservation->filter($importedData);
        // The outer interceptor prevents both legacy and MSI writes for held SKUs.
        if ($stockData !== []) {
            $proceed($stockData, $importedData);
        }
    }
}
