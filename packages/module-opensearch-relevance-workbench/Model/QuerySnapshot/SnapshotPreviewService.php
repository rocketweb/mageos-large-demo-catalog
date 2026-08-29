<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot;

use InvalidArgumentException;
use Magento\Store\Api\StoreRepositoryInterface;

class SnapshotPreviewService
{
    public function __construct(
        private readonly StoreRepositoryInterface $storeRepository,
        private readonly SearchQuerySourceReader $sourceReader,
        private readonly QuerySnapshotPreviewer $previewer,
        private readonly CuratedQueryMetadataFactory $metadataFactory
    ) {
    }

    /**
     * @param array<string, mixed> $parameters
     */
    public function create(array $parameters): QuerySnapshotPreview
    {
        $storeId = $this->positiveInteger($parameters, 'store_id');
        $this->storeRepository->getActiveStoreById($storeId);
        $sourceWindowStart = $this->requiredString($parameters, 'source_window_start');
        $sourceWindowEnd = $this->requiredString($parameters, 'source_window_end');
        $policy = new SnapshotPolicy(
            $this->nonNegativeInteger($parameters, 'minimum_popularity'),
            $this->positiveInteger($parameters, 'positive_result_limit'),
            $this->positiveInteger($parameters, 'zero_result_limit'),
            $this->positiveInteger($parameters, 'total_limit'),
            ($parameters['include_redirects'] ?? null) === '1',
            128,
            'osrw-privacy-v1',
            $sourceWindowStart,
            $sourceWindowEnd
        );
        $rows = $this->sourceReader->read($storeId, $sourceWindowStart, $sourceWindowEnd);

        $rawMetadata = $parameters['metadata'] ?? [];

        if (!is_array($rawMetadata)) {
            throw new InvalidArgumentException('Curated query metadata must be an object');
        }

        return $this->previewer->preview(
            $storeId,
            $rows,
            $policy,
            $this->metadataFactory->create($rawMetadata)
        );
    }

    /**
     * @param array<string, mixed> $parameters
     */
    private function positiveInteger(array $parameters, string $key): int
    {
        $value = filter_var($parameters[$key] ?? null, FILTER_VALIDATE_INT);

        if (!is_int($value) || $value < 1) {
            throw new InvalidArgumentException('Snapshot parameter must be a positive integer: ' . $key);
        }

        return $value;
    }

    /**
     * @param array<string, mixed> $parameters
     */
    private function nonNegativeInteger(array $parameters, string $key): int
    {
        $value = filter_var($parameters[$key] ?? null, FILTER_VALIDATE_INT);

        if (!is_int($value) || $value < 0) {
            throw new InvalidArgumentException('Snapshot parameter must be a non-negative integer: ' . $key);
        }

        return $value;
    }

    /**
     * @param array<string, mixed> $parameters
     */
    private function requiredString(array $parameters, string $key): string
    {
        $value = trim((string)($parameters[$key] ?? ''));

        if ($value === '') {
            throw new InvalidArgumentException('Snapshot parameter is required: ' . $key);
        }

        return $value;
    }
}
