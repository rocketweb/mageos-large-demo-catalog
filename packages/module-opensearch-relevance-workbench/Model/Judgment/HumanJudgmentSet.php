<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Judgment;

class HumanJudgmentSet
{
    /**
     * @param list<array{query_hash: string, query_text: string, document_id: string, rating: float}> $ratings
     */
    public function __construct(
        private readonly string $snapshotHash,
        private readonly string $indexEvidenceHash,
        private readonly array $ratings,
        private readonly string $judgmentHash,
        private readonly int $reviewedBy,
        private readonly string $reviewedAt
    ) {
    }

    public function getSnapshotHash(): string
    {
        return $this->snapshotHash;
    }

    public function getIndexEvidenceHash(): string
    {
        return $this->indexEvidenceHash;
    }

    public function getJudgmentHash(): string
    {
        return $this->judgmentHash;
    }

    public function getRatingCount(): int
    {
        return count($this->ratings);
    }

    public function getReviewedBy(): int
    {
        return $this->reviewedBy;
    }

    public function getReviewedAt(): string
    {
        return $this->reviewedAt;
    }

    /**
     * @return list<array{query_hash: string, query_text: string, document_id: string, rating: float}>
     */
    public function getRatings(): array
    {
        return $this->ratings;
    }

    /**
     * @return list<array{query: string, ratings: list<array{docId: string, rating: string}>}>
     */
    public function getRemoteJudgmentRatings(): array
    {
        $byQuery = [];

        foreach ($this->ratings as $rating) {
            $byQuery[$rating['query_hash']]['query'] = $rating['query_text'];
            $byQuery[$rating['query_hash']]['ratings'][] = [
                'docId' => $rating['document_id'],
                'rating' => number_format($rating['rating'], 1, '.', ''),
            ];
        }

        return array_values($byQuery);
    }
}
