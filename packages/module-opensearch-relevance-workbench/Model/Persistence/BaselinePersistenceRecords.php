<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

class BaselinePersistenceRecords
{
    /**
     * @param array<string, int|string> $indexEvidence
     * @param array<string, int|string|null> $configuration
     * @param array<string, string|null> $auditEvent
     */
    public function __construct(
        private readonly array $indexEvidence,
        private readonly array $configuration,
        private readonly array $auditEvent
    ) {
    }

    /**
     * @return array<string, int|string>
     */
    public function getIndexEvidence(): array
    {
        return $this->indexEvidence;
    }

    /**
     * @return array<string, int|string|null>
     */
    public function getConfiguration(): array
    {
        return $this->configuration;
    }

    /**
     * @return array<string, string|null>
     */
    public function getAuditEvent(): array
    {
        return $this->auditEvent;
    }
}
