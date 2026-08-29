<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Experiment;

class PersistedExperiment
{
    /**
     * @param array<string, float|int|string> $inputIdentities
     * @param array<string, string> $remoteExperimentIds
     */
    public function __construct(
        private readonly string $experimentUuid,
        private readonly int $storeId,
        private readonly string $state,
        private readonly array $inputIdentities,
        private readonly string $inputHash,
        private readonly array $remoteExperimentIds,
        private readonly EvidenceReport $evidence,
        private readonly ?int $acceptedBy,
        private readonly ?string $acceptedAt
    ) {
    }

    public function getExperimentUuid(): string
    {
        return $this->experimentUuid;
    }

    public function getStoreId(): int
    {
        return $this->storeId;
    }

    public function getState(): string
    {
        return $this->state;
    }

    /**
     * @return array<string, float|int|string>
     */
    public function getInputIdentities(): array
    {
        return $this->inputIdentities;
    }

    public function getInputHash(): string
    {
        return $this->inputHash;
    }

    /**
     * @return array<string, string>
     */
    public function getRemoteExperimentIds(): array
    {
        return $this->remoteExperimentIds;
    }

    public function getEvidence(): EvidenceReport
    {
        return $this->evidence;
    }

    public function getAcceptedBy(): ?int
    {
        return $this->acceptedBy;
    }

    public function getAcceptedAt(): ?string
    {
        return $this->acceptedAt;
    }
}
