<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot;

use InvalidArgumentException;

class SnapshotPolicy
{
    public function __construct(
        private readonly int $minimumPopularity,
        private readonly int $positiveResultLimit,
        private readonly int $zeroResultLimit,
        private readonly int $totalLimit,
        private readonly bool $includeRedirects,
        private readonly int $maximumTermLength,
        private readonly string $privacyPolicyVersion,
        private readonly ?string $sourceWindowStart = null,
        private readonly ?string $sourceWindowEnd = null
    ) {
        if (
            $this->minimumPopularity < 0
            || $this->positiveResultLimit < 1
            || $this->zeroResultLimit < 1
            || $this->totalLimit < 1
            || $this->maximumTermLength < 1
            || $this->privacyPolicyVersion === ''
        ) {
            throw new InvalidArgumentException('Snapshot policy limits and version must be valid');
        }
    }

    public function getMinimumPopularity(): int
    {
        return $this->minimumPopularity;
    }

    public function getPositiveResultLimit(): int
    {
        return $this->positiveResultLimit;
    }

    public function getZeroResultLimit(): int
    {
        return $this->zeroResultLimit;
    }

    public function getTotalLimit(): int
    {
        return $this->totalLimit;
    }

    public function includesRedirects(): bool
    {
        return $this->includeRedirects;
    }

    public function getMaximumTermLength(): int
    {
        return $this->maximumTermLength;
    }

    public function getPrivacyPolicyVersion(): string
    {
        return $this->privacyPolicyVersion;
    }

    public function getSourceWindowStart(): ?string
    {
        return $this->sourceWindowStart;
    }

    public function getSourceWindowEnd(): ?string
    {
        return $this->sourceWindowEnd;
    }

    /**
     * @return array<string, int|string|bool|null>
     */
    public function toCanonicalArray(): array
    {
        return [
            'minimum_popularity' => $this->minimumPopularity,
            'positive_result_limit' => $this->positiveResultLimit,
            'zero_result_limit' => $this->zeroResultLimit,
            'total_limit' => $this->totalLimit,
            'include_redirects' => $this->includeRedirects,
            'maximum_term_length' => $this->maximumTermLength,
            'privacy_policy_version' => $this->privacyPolicyVersion,
            'source_window_start' => $this->sourceWindowStart,
            'source_window_end' => $this->sourceWindowEnd,
        ];
    }
}
