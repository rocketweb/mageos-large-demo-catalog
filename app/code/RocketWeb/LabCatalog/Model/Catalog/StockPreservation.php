<?php
declare(strict_types=1);

namespace RocketWeb\LabCatalog\Model\Catalog;

use InvalidArgumentException;
use LogicException;

class StockPreservation
{
    private ?array $protected = null;

    public function execute(array $skus, callable $operation): mixed
    {
        if ($this->protected !== null) {
            throw new LogicException('Nested stock preservation is not supported.');
        }
        foreach ($skus as $sku) {
            if (!is_string($sku) || !str_starts_with($sku, 'WANDS-')) {
                throw new InvalidArgumentException('Stock preservation is limited to WANDS SKUs.');
            }
        }
        $this->protected = array_fill_keys($skus, true);
        try {
            return $operation();
        } finally {
            $this->protected = null;
        }
    }

    public function filter(array $rows): array
    {
        return array_diff_key($rows, $this->protected ?? []);
    }

    public function isActive(): bool
    {
        return $this->protected !== null;
    }
}
