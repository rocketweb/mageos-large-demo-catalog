<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource;

class OwnedResourceCleanupDecision
{
    /**
     * @param list<string> $reasonCodes
     */
    public function __construct(
        private readonly string $remoteId,
        private readonly bool $eligible,
        private readonly array $reasonCodes
    ) {
    }

    public function getRemoteId(): string
    {
        return $this->remoteId;
    }

    public function isEligible(): bool
    {
        return $this->eligible;
    }

    /**
     * @return list<string>
     */
    public function getReasonCodes(): array
    {
        return $this->reasonCodes;
    }
}
