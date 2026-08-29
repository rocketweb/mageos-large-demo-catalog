<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

class ProposalPersistenceRecords
{
    /**
     * @param array<string, int|string> $proposal
     * @param array<string, string|null> $auditEvent
     */
    public function __construct(
        private readonly array $proposal,
        private readonly array $auditEvent
    ) {
    }

    /**
     * @return array<string, int|string>
     */
    public function getProposal(): array
    {
        return $this->proposal;
    }

    /**
     * @return array<string, string|null>
     */
    public function getAuditEvent(): array
    {
        return $this->auditEvent;
    }
}
