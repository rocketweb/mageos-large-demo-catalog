<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Judgment;

use DateTimeImmutable;
use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\ApprovedQuerySnapshot;

class HumanJudgmentSetFactory
{
    public function __construct(private readonly CanonicalJson $canonicalJson)
    {
    }

    /**
     * @param list<array{query_hash: string, document_id: string, rating: float}> $ratings
     */
    public function create(
        ApprovedQuerySnapshot $snapshot,
        string $indexEvidenceHash,
        array $ratings,
        int $reviewedBy,
        string $reviewedAt
    ): HumanJudgmentSet {
        $this->assertHash($indexEvidenceHash, 'Index evidence hash');

        if ($ratings === []) {
            throw new InvalidArgumentException('Human judgment requires at least one reviewed rating');
        }

        if ($reviewedBy < 1) {
            throw new InvalidArgumentException('Human judgment reviewer must be a positive administrator ID');
        }

        new DateTimeImmutable($reviewedAt);
        $queriesByHash = [];

        foreach ($snapshot->getEntries() as $entry) {
            $queriesByHash[$entry->getQueryHash()] = $entry->getQueryText();
        }

        $normalizedRatings = [];

        foreach ($ratings as $rating) {
            $queryHash = $rating['query_hash'];
            $documentId = trim($rating['document_id']);
            $ratingValue = $rating['rating'];

            if (!isset($queriesByHash[$queryHash])) {
                throw new InvalidArgumentException(
                    'Human rating references a query outside the approved snapshot'
                );
            }

            if ($documentId === '') {
                throw new InvalidArgumentException('Human rating document ID must be non-empty');
            }

            if (!in_array($ratingValue, [0.0, 0.5, 1.0], true)) {
                throw new InvalidArgumentException('Human rating must be 0.0, 0.5, or 1.0');
            }

            $identity = $queryHash . "\0" . $documentId;

            if (isset($normalizedRatings[$identity])) {
                throw new InvalidArgumentException('Human rating contains a duplicate query-document pair');
            }

            $normalizedRatings[$identity] = [
                'query_hash' => $queryHash,
                'query_text' => $queriesByHash[$queryHash],
                'document_id' => $documentId,
                'rating' => $ratingValue,
            ];
        }

        usort(
            $normalizedRatings,
            static fn (array $left, array $right): int =>
                [$left['query_text'], $left['document_id']]
                <=> [$right['query_text'], $right['document_id']]
        );
        $judgmentHash = $this->canonicalJson->hash([
            'query_snapshot_sha256' => $snapshot->getSnapshotHash(),
            'index_evidence_sha256' => $indexEvidenceHash,
            'rating_type' => 'SCORE0_1',
            'ratings' => array_map(
                static fn (array $rating): array => [
                    'query_hash' => $rating['query_hash'],
                    'document_id' => $rating['document_id'],
                    'rating' => $rating['rating'],
                ],
                $normalizedRatings
            ),
        ]);

        return new HumanJudgmentSet(
            $snapshot->getSnapshotHash(),
            $indexEvidenceHash,
            $normalizedRatings,
            $judgmentHash,
            $reviewedBy,
            $reviewedAt
        );
    }

    private function assertHash(string $hash, string $label): void
    {
        if (preg_match('/\A[0-9a-f]{64}\z/', $hash) !== 1) {
            throw new InvalidArgumentException($label . ' must be a lowercase SHA-256 value');
        }
    }
}
