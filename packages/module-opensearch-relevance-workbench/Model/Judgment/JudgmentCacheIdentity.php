<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Judgment;

class JudgmentCacheIdentity
{
    /**
     * @param list<string> $contextFields
     */
    public function __construct(
        private readonly string $modelId,
        private readonly string $promptHash,
        private readonly string $ratingType,
        private readonly array $contextFields,
        private readonly string $contextValuesHash,
        private readonly string $querySnapshotHash,
        private readonly string $searchConfigurationHash,
        private readonly string $indexEvidenceHash,
        private readonly string $identityHash
    ) {
    }

    public function getModelId(): string
    {
        return $this->modelId;
    }

    public function getPromptHash(): string
    {
        return $this->promptHash;
    }

    public function getRatingType(): string
    {
        return $this->ratingType;
    }

    /**
     * @return list<string>
     */
    public function getContextFields(): array
    {
        return $this->contextFields;
    }

    public function getContextValuesHash(): string
    {
        return $this->contextValuesHash;
    }

    public function getQuerySnapshotHash(): string
    {
        return $this->querySnapshotHash;
    }

    public function getSearchConfigurationHash(): string
    {
        return $this->searchConfigurationHash;
    }

    public function getIndexEvidenceHash(): string
    {
        return $this->indexEvidenceHash;
    }

    public function getIdentityHash(): string
    {
        return $this->identityHash;
    }
}
