<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Plugin\OpenSearch;

use Magento\Framework\Search\RequestInterface;
use Magento\OpenSearch\SearchAdapter\Mapper;
use MageOS\OpenSearchRelevanceWorkbench\Model\Activation\LiveQueryApplier;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineCaptureContext;
use Psr\Log\LoggerInterface;
use Throwable;

class CaptureMappedQuery
{
    public function __construct(
        private readonly BaselineCaptureContext $captureContext,
        private readonly LiveQueryApplier $liveQueryApplier,
        private readonly LoggerInterface $logger
    ) {
    }

    /**
     * @param array<array-key, mixed> $mappedQuery
     * @return array<array-key, mixed>
     */
    public function afterBuildQuery(Mapper $subject, array $mappedQuery, RequestInterface $request): array
    {
        $this->captureContext->record($mappedQuery);

        if ((string)$request->getName() !== 'quick_search_container') {
            return $mappedQuery;
        }

        try {
            $mappedQuery = $this->liveQueryApplier->apply($mappedQuery);
        } catch (Throwable $exception) {
            $this->logger->error(
                'OpenSearch Relevance Workbench could not read the active configuration; stock query retained',
                ['exception' => $exception]
            );
        }

        return $mappedQuery;
    }
}
