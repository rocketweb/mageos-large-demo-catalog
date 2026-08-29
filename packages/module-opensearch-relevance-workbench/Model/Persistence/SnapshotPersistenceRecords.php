<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

class SnapshotPersistenceRecords
{
    /**
     * @param array<string, int|string|null> $snapshot
     * @param list<array<string, int|string|null>> $entries
     * @param array<string, int|string|null> $auditEvent
     */
    public function __construct(
        private readonly array $snapshot,
        private readonly array $entries,
        private readonly array $auditEvent
    ) {
    }

    /**
     * @return array<string, int|string|null>
     */
    public function getSnapshot(): array
    {
        return $this->snapshot;
    }

    /**
     * @return list<array<string, int|string|null>>
     */
    public function getEntries(): array
    {
        return $this->entries;
    }

    /**
     * @return array<string, int|string|null>
     */
    public function getAuditEvent(): array
    {
        return $this->auditEvent;
    }
}
