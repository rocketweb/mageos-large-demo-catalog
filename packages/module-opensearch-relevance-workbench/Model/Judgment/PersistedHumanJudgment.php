<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Judgment;

class PersistedHumanJudgment
{
    /**
     * @param list<array{query_hash: string, query_text: string, document_id: string, rating: float}> $ratings
     */
    public function __construct(
        private readonly string $judgmentUuid,
        private readonly string $snapshotUuid,
        private readonly string $indexEvidenceUuid,
        private readonly string $snapshotHash,
        private readonly string $indexEvidenceHash,
        private readonly array $ratings,
        private readonly string $judgmentHash,
        private readonly int $reviewedBy,
        private readonly string $reviewedAt,
        private readonly ?string $remoteJudgmentId
    ) {
    }

    public function getJudgmentUuid(): string
    {
        return $this->judgmentUuid;
    }

    public function getSnapshotUuid(): string
    {
        return $this->snapshotUuid;
    }

    public function getIndexEvidenceUuid(): string
    {
        return $this->indexEvidenceUuid;
    }

    public function getSnapshotHash(): string
    {
        return $this->snapshotHash;
    }

    public function getIndexEvidenceHash(): string
    {
        return $this->indexEvidenceHash;
    }

    /**
     * @return list<array{query_hash: string, query_text: string, document_id: string, rating: float}>
     */
    public function getRatings(): array
    {
        return $this->ratings;
    }

    public function getJudgmentHash(): string
    {
        return $this->judgmentHash;
    }

    public function getReviewedBy(): int
    {
        return $this->reviewedBy;
    }

    public function getReviewedAt(): string
    {
        return $this->reviewedAt;
    }

    public function getRemoteJudgmentId(): ?string
    {
        return $this->remoteJudgmentId;
    }

    public function toJudgmentSet(): HumanJudgmentSet
    {
        return new HumanJudgmentSet(
            $this->snapshotHash,
            $this->indexEvidenceHash,
            $this->ratings,
            $this->judgmentHash,
            $this->reviewedBy,
            $this->reviewedAt
        );
    }
}
