<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Configuration;

class ValidatedCandidateConfiguration
{
    /**
     * @param list<array{query_text_hash: string, rendered_request_hash: string, result_count: int}> $validationEvidence
     */
    public function __construct(
        private readonly CandidateConfiguration $candidate,
        private readonly PersistedBaselineConfiguration $baseline,
        private readonly array $validationEvidence
    ) {
    }

    public function getCandidate(): CandidateConfiguration
    {
        return $this->candidate;
    }

    public function getBaseline(): PersistedBaselineConfiguration
    {
        return $this->baseline;
    }

    /**
     * @return list<array{query_text_hash: string, rendered_request_hash: string, result_count: int}>
     */
    public function getValidationEvidence(): array
    {
        return $this->validationEvidence;
    }
}
