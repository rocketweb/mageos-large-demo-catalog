<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch;

class CapabilityReport
{
    /**
     * @param list<string> $reasonCodes
     */
    public function __construct(
        private readonly bool $coreReady,
        private readonly bool $llmReady,
        private readonly array $reasonCodes
    ) {
    }

    public function isCoreReady(): bool
    {
        return $this->coreReady;
    }

    public function isLlmReady(): bool
    {
        return $this->llmReady;
    }

    /**
     * @return list<string>
     */
    public function getReasonCodes(): array
    {
        return $this->reasonCodes;
    }
}
