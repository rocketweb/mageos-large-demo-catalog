<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Configuration;

use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;

class PersistedCandidateConfiguration
{
    /**
     * @param array{type: string, boosts: array<string, float>} $transformation
     */
    public function __construct(
        private readonly string $configurationUuid,
        private readonly int $storeId,
        private readonly string $parentBaselineUuid,
        private readonly BaselineTemplate $template,
        private readonly array $transformation,
        private readonly string $indexEvidenceUuid,
        private readonly string $physicalIndex,
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

    public function getParentBaselineUuid(): string
    {
        return $this->parentBaselineUuid;
    }

    public function getTemplate(): BaselineTemplate
    {
        return $this->template;
    }

    /**
     * @return array{type: string, boosts: array<string, float>}
     */
    public function getTransformation(): array
    {
        return $this->transformation;
    }

    public function getIndexEvidenceUuid(): string
    {
        return $this->indexEvidenceUuid;
    }

    public function getPhysicalIndex(): string
    {
        return $this->physicalIndex;
    }

    public function getConfigurationHash(): string
    {
        return $this->configurationHash;
    }
}
