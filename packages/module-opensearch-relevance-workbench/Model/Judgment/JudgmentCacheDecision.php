<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Judgment;

class JudgmentCacheDecision
{
    /**
     * @param list<string> $reasonCodes
     */
    public function __construct(
        private readonly bool $overwriteCache,
        private readonly array $reasonCodes
    ) {
    }

    public function shouldOverwriteCache(): bool
    {
        return $this->overwriteCache;
    }

    /**
     * @return list<string>
     */
    public function getReasonCodes(): array
    {
        return $this->reasonCodes;
    }
}
