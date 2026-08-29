<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot;

class ApprovedQuerySnapshot
{
    /**
     * @param list<QuerySnapshotEntry> $entries
     * @param array{updated_at: string, query_id: int} $highWaterBoundary
     */
    public function __construct(
        private readonly int $storeId,
        private readonly array $entries,
        private readonly SnapshotPolicy $policy,
        private readonly array $highWaterBoundary,
        private readonly string $snapshotHash,
        private readonly int $approvedBy,
        private readonly string $approvedAt
    ) {
    }

    public function getStatus(): string
    {
        return 'APPROVED';
    }

    public function getStoreId(): int
    {
        return $this->storeId;
    }

    /**
     * @return list<QuerySnapshotEntry>
     */
    public function getEntries(): array
    {
        return $this->entries;
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

    public function getApprovedBy(): int
    {
        return $this->approvedBy;
    }

    public function getApprovedAt(): string
    {
        return $this->approvedAt;
    }

    /**
     * @return list<array{queryText: string, customFields?: array<string, string>}>
     */
    public function getRemoteQuerySetEntries(): array
    {
        return array_map(
            static fn (QuerySnapshotEntry $entry): array => $entry->toRemoteQuerySetEntry(),
            $this->entries
        );
    }
}
