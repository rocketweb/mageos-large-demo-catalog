<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Activation;

class LiveActivation
{
    /**
     * @param array{type: string, boosts?: array<string, float>} $transformation
     */
    public function __construct(
        private readonly string $activationUuid,
        private readonly int $storeId,
        private readonly string $action,
        private readonly ?string $candidateUuid,
        private readonly ?string $sourceExperimentUuid,
        private readonly ?string $previousActivationUuid,
        private readonly array $transformation,
        private readonly ?string $candidateHash,
        private readonly string $indexEvidenceHash,
        private readonly string $targetAlias,
        private readonly int $actorId,
        private readonly string $createdAt
    ) {
    }

    public function getActivationUuid(): string
    {
        return $this->activationUuid;
    }

    public function getStoreId(): int
    {
        return $this->storeId;
    }

    public function getAction(): string
    {
        return $this->action;
    }

    public function getCandidateUuid(): ?string
    {
        return $this->candidateUuid;
    }

    public function getSourceExperimentUuid(): ?string
    {
        return $this->sourceExperimentUuid;
    }

    public function getPreviousActivationUuid(): ?string
    {
        return $this->previousActivationUuid;
    }

    /**
     * @return array{type: string, boosts?: array<string, float>}
     */
    public function getTransformation(): array
    {
        return $this->transformation;
    }

    public function getCandidateHash(): ?string
    {
        return $this->candidateHash;
    }

    public function getIndexEvidenceHash(): string
    {
        return $this->indexEvidenceHash;
    }

    public function getTargetAlias(): string
    {
        return $this->targetAlias;
    }

    public function getActorId(): int
    {
        return $this->actorId;
    }

    public function getCreatedAt(): string
    {
        return $this->createdAt;
    }
}
