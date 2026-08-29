<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot;

class PrivacyInspection
{
    /**
     * @param list<string> $reasonCodes
     */
    public function __construct(private readonly array $reasonCodes)
    {
    }

    public function isAllowed(): bool
    {
        return $this->reasonCodes === [];
    }

    /**
     * @return list<string>
     */
    public function getReasonCodes(): array
    {
        return $this->reasonCodes;
    }
}
