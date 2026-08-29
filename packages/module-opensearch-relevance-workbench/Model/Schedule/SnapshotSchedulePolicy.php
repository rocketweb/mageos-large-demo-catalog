<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Schedule;

use DateTimeImmutable;
use DateTimeZone;

class SnapshotSchedulePolicy
{
    public function __construct(
        private readonly int $storeId,
        private readonly int $sourceWindowDays,
        private readonly int $minimumPopularity,
        private readonly int $positiveResultLimit,
        private readonly int $zeroResultLimit,
        private readonly int $maximumSnapshotSize,
        private readonly bool $includeRedirects,
        private readonly int $intervalDays,
        private readonly int $retentionDays,
        private readonly string $scheduleAnchorAt,
        private readonly string $nextRunAt,
        private readonly string $policyHash
    ) {
    }

    public function getStoreId(): int
    {
        return $this->storeId;
    }

    public function getSourceWindowDays(): int
    {
        return $this->sourceWindowDays;
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

    public function getMaximumSnapshotSize(): int
    {
        return $this->maximumSnapshotSize;
    }

    public function includesRedirects(): bool
    {
        return $this->includeRedirects;
    }

    public function getIntervalDays(): int
    {
        return $this->intervalDays;
    }

    public function getRetentionDays(): int
    {
        return $this->retentionDays;
    }

    public function getScheduleAnchorAt(): string
    {
        return $this->scheduleAnchorAt;
    }

    public function getNextRunAt(): string
    {
        return $this->nextRunAt;
    }

    public function getPolicyHash(): string
    {
        return $this->policyHash;
    }

    /**
     * @return array<string, int|string>
     */
    public function getPreviewParameters(): array
    {
        $end = new DateTimeImmutable($this->nextRunAt);
        $start = $end->modify('-' . $this->sourceWindowDays . ' days');

        return [
            'store_id' => $this->storeId,
            'source_window_start' => $start->format(DATE_ATOM),
            'source_window_end' => $end->format(DATE_ATOM),
            'minimum_popularity' => $this->minimumPopularity,
            'positive_result_limit' => $this->positiveResultLimit,
            'zero_result_limit' => $this->zeroResultLimit,
            'total_limit' => $this->maximumSnapshotSize,
            'include_redirects' => $this->includeRedirects ? '1' : '0',
        ];
    }

    public function getFollowingRunAt(): string
    {
        return (new DateTimeImmutable($this->nextRunAt))
            ->setTimezone(new DateTimeZone('UTC'))
            ->modify('+' . $this->intervalDays . ' days')
            ->format(DATE_ATOM);
    }

    /**
     * @return array<string, bool|int|string>
     */
    public function toCanonicalArray(): array
    {
        return [
            'store_id' => $this->storeId,
            'source_window_days' => $this->sourceWindowDays,
            'minimum_popularity' => $this->minimumPopularity,
            'positive_result_limit' => $this->positiveResultLimit,
            'zero_result_limit' => $this->zeroResultLimit,
            'maximum_snapshot_size' => $this->maximumSnapshotSize,
            'include_redirects' => $this->includeRedirects,
            'interval_days' => $this->intervalDays,
            'retention_days' => $this->retentionDays,
            'schedule_anchor_at' => $this->scheduleAnchorAt,
        ];
    }
}
