<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Configuration;

use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;

class PersistedBaselineConfiguration
{
    /**
     * @param array<string, array{searchable: bool, sensitive: bool, dynamic: bool, type: string}> $fieldCapabilities
     */
    public function __construct(
        private readonly string $configurationUuid,
        private readonly int $storeId,
        private readonly BaselineTemplate $template,
        private readonly array $fieldCapabilities,
        private readonly string $indexEvidenceUuid,
        private readonly string $targetAlias,
        private readonly string $physicalIndex,
        private readonly string $indexEvidenceHash,
        private readonly string $pipelineIdentity,
        private readonly string $configurationHash
    ) {
    }

    public function getConfigurationUuid(): string
    {
        return $this->configurationUuid;
    }

    public function getStoreId(): int
    {
        return $this->storeId;
    }

    public function getTemplate(): BaselineTemplate
    {
        return $this->template;
    }

    /**
     * @return array<string, array{searchable: bool, sensitive: bool, dynamic: bool, type: string}>
     */
    public function getFieldCapabilities(): array
    {
        return $this->fieldCapabilities;
    }

    public function getIndexEvidenceUuid(): string
    {
        return $this->indexEvidenceUuid;
    }

    public function getPhysicalIndex(): string
    {
        return $this->physicalIndex;
    }

    public function getTargetAlias(): string
    {
        return $this->targetAlias;
    }

    public function getIndexEvidenceHash(): string
    {
        return $this->indexEvidenceHash;
    }

    public function getPipelineIdentity(): string
    {
        return $this->pipelineIdentity;
    }

    public function getConfigurationHash(): string
    {
        return $this->configurationHash;
    }
}
