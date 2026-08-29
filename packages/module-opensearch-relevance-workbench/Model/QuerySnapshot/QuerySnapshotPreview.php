<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot;

use DateTimeImmutable;
use InvalidArgumentException;

class QuerySnapshotPreview
{
    /**
     * @param list<QuerySnapshotEntry> $entries
     * @param array<string, int> $excludedCounts
     * @param array{updated_at: string, query_id: int} $highWaterBoundary
     */
    public function __construct(
        private readonly int $storeId,
        private readonly int $sourceCount,
        private readonly array $entries,
        private readonly array $excludedCounts,
        private readonly SnapshotPolicy $policy,
        private readonly array $highWaterBoundary,
        private readonly string $snapshotHash
    ) {
    }

    public function getStoreId(): int
    {
        return $this->storeId;
    }

    public function getSourceCount(): int
    {
        return $this->sourceCount;
    }

    public function getSelectedCount(): int
    {
        return count($this->entries);
    }

    /**
     * @return list<QuerySnapshotEntry>
     */
    public function getEntries(): array
    {
        return $this->entries;
    }

    /**
     * @return array<string, int>
     */
    public function getExcludedCounts(): array
    {
        return $this->excludedCounts;
    }

    public function getPolicy(): SnapshotPolicy
    {
        return $this->policy;
    }

    /**
     * @return array{updated_at: string, query_id: int}
     */
    public function getHighWaterBoundary(): array
    {
        return $this->highWaterBoundary;
    }

    public function getSnapshotHash(): string
    {
        return $this->snapshotHash;
    }

    public function approve(
        string $expectedHash,
        int $approvedBy,
        string $approvedAt
    ): ApprovedQuerySnapshot {
        if (!hash_equals($this->snapshotHash, $expectedHash)) {
            throw new InvalidArgumentException('Snapshot approval hash does not match the preview');
        }

        if ($approvedBy < 1) {
            throw new InvalidArgumentException('Snapshot approver must be a positive administrator ID');
        }

        new DateTimeImmutable($approvedAt);

        return new ApprovedQuerySnapshot(
            $this->storeId,
            $this->entries,
            $this->policy,
            $this->highWaterBoundary,
            $this->snapshotHash,
            $approvedBy,
            $approvedAt
        );
    }
}
