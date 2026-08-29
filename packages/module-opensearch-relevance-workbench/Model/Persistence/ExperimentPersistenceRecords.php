<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

class ExperimentPersistenceRecords
{
    /**
     * @param array<string, int|string|null> $experiment
     * @param array<string, string|null> $auditEvent
     */
    public function __construct(
        private readonly array $experiment,
        private readonly array $auditEvent
    ) {
    }

    /**
     * @return array<string, int|string|null>
     */
    public function getExperiment(): array
    {
        return $this->experiment;
    }

    /**
     * @return array<string, string|null>
     */
    public function getAuditEvent(): array
    {
        return $this->auditEvent;
    }
}
