<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Baseline;

use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\IndexEvidence;

class StockBaselineCapture
{
    /**
     * @param array<string, array{searchable: bool, sensitive: bool, dynamic: bool, type: string}> $fieldCapabilities
     * @param array{index: string, query: string, searchPipeline: string} $remoteConfiguration
     */
    public function __construct(
        private readonly BaselineCaptureResult $captureResult,
        private readonly IndexEvidence $indexEvidence,
        private readonly array $fieldCapabilities,
        private readonly array $remoteConfiguration,
        private readonly string $configurationHash
    ) {
    }

    public function getCaptureResult(): BaselineCaptureResult
    {
        return $this->captureResult;
    }

    public function getIndexEvidence(): IndexEvidence
    {
        return $this->indexEvidence;
    }

    /**
     * @return array<string, array{searchable: bool, sensitive: bool, dynamic: bool, type: string}>
     */
    public function getFieldCapabilities(): array
    {
        return $this->fieldCapabilities;
    }

    /**
     * @return array{index: string, query: string, searchPipeline: string}
     */
    public function getRemoteConfiguration(): array
    {
        return $this->remoteConfiguration;
    }

    public function getConfigurationHash(): string
    {
        return $this->configurationHash;
    }
}
