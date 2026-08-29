<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Baseline;

use Magento\CatalogSearch\Model\ResourceModel\Fulltext\Collection;
use Magento\Framework\ObjectManagerInterface;

class SearchCollectionFactory
{
    public function __construct(private readonly ObjectManagerInterface $objectManager)
    {
    }

    /**
     * @param array<string, mixed> $data
     */
    public function create(array $data = []): Collection
    {
        return $this->objectManager->create(Collection::class, $data);
    }
}
