<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Schedule;

use DateTimeImmutable;
use DateTimeZone;
use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;

class SnapshotSchedulePolicyFactory
{
    public function __construct(private readonly CanonicalJson $canonicalJson)
    {
    }

    /**
     * @param array<string, mixed> $parameters
     */
    public function create(array $parameters): SnapshotSchedulePolicy
    {
        $storeId = $this->integer($parameters, 'store_id', 1, PHP_INT_MAX);
        $sourceWindowDays = $this->integer($parameters, 'source_window_days', 1, 365);
        $minimumPopularity = $this->integer($parameters, 'minimum_popularity', 0, PHP_INT_MAX);
        $positiveResultLimit = $this->integer($parameters, 'positive_result_limit', 1, 100);
        $zeroResultLimit = $this->integer($parameters, 'zero_result_limit', 1, 100);
        $maximumSnapshotSize = $this->integer($parameters, 'total_limit', 1, 200);
        $intervalDays = $this->integer($parameters, 'interval_days', 7, 90);
        $retentionDays = $this->integer($parameters, 'retention_days', 7, 730);

        if ($retentionDays < $intervalDays) {
            throw new InvalidArgumentException('Snapshot retention must not be shorter than the schedule interval');
        }

        $firstRunAt = $this->date($parameters, 'first_run_at');
        $canonical = [
            'store_id' => $storeId,
            'source_window_days' => $sourceWindowDays,
            'minimum_popularity' => $minimumPopularity,
            'positive_result_limit' => $positiveResultLimit,
            'zero_result_limit' => $zeroResultLimit,
            'maximum_snapshot_size' => $maximumSnapshotSize,
            'include_redirects' => ($parameters['include_redirects'] ?? null) === '1',
            'interval_days' => $intervalDays,
            'retention_days' => $retentionDays,
            'schedule_anchor_at' => $firstRunAt,
        ];

        return new SnapshotSchedulePolicy(
            $storeId,
            $sourceWindowDays,
            $minimumPopularity,
            $positiveResultLimit,
            $zeroResultLimit,
            $maximumSnapshotSize,
            $canonical['include_redirects'],
            $intervalDays,
            $retentionDays,
            $firstRunAt,
            $firstRunAt,
            $this->canonicalJson->hash($canonical)
        );
    }

    /**
     * @param array<string, mixed> $row
     */
    public function rehydrate(array $row): SnapshotSchedulePolicy
    {
        $canonical = [
            'store_id' => (int)($row['store_id'] ?? 0),
            'source_window_days' => (int)($row['source_window_days'] ?? 0),
            'minimum_popularity' => (int)($row['minimum_popularity'] ?? 0),
            'positive_result_limit' => (int)($row['positive_result_limit'] ?? 0),
            'zero_result_limit' => (int)($row['zero_result_limit'] ?? 0),
            'maximum_snapshot_size' => (int)($row['maximum_snapshot_size'] ?? 0),
            'include_redirects' => (int)($row['include_redirects'] ?? 0) === 1,
            'interval_days' => (int)($row['interval_days'] ?? 0),
            'retention_days' => (int)($row['retention_days'] ?? 0),
            'schedule_anchor_at' => $this->date($row, 'schedule_anchor_at'),
        ];
        $policyHash = (string)($row['policy_sha256'] ?? '');

        if (!hash_equals($this->canonicalJson->hash($canonical), $policyHash)) {
            throw new InvalidArgumentException('Persisted snapshot schedule policy hash does not match its rules');
        }

        return new SnapshotSchedulePolicy(
            $canonical['store_id'],
            $canonical['source_window_days'],
            $canonical['minimum_popularity'],
            $canonical['positive_result_limit'],
            $canonical['zero_result_limit'],
            $canonical['maximum_snapshot_size'],
            $canonical['include_redirects'],
            $canonical['interval_days'],
            $canonical['retention_days'],
            $canonical['schedule_anchor_at'],
            $this->date($row, 'next_run_at'),
            $policyHash
        );
    }

    /**
     * @param array<string, mixed> $parameters
     */
    private function integer(array $parameters, string $key, int $minimum, int $maximum): int
    {
        $value = filter_var($parameters[$key] ?? null, FILTER_VALIDATE_INT);

        if (!is_int($value) || $value < $minimum || $value > $maximum) {
            throw new InvalidArgumentException('Snapshot schedule integer is outside its bound: ' . $key);
        }

        return $value;
    }

    /**
     * @param array<string, mixed> $parameters
     */
    private function date(array $parameters, string $key): string
    {
        $value = trim((string)($parameters[$key] ?? ''));

        if ($value === '') {
            throw new InvalidArgumentException('Snapshot schedule date is required: ' . $key);
        }

        return (new DateTimeImmutable($value, new DateTimeZone('UTC')))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format(DATE_ATOM);
    }
}
