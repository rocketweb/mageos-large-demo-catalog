<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Schedule;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Schedule\SnapshotSchedulePolicyFactory;
use PHPUnit\Framework\TestCase;

class SnapshotSchedulePolicyFactoryTest extends TestCase
{
    public function testFreezesBoundedRulesAndProducesOneDraftWindow(): void
    {
        $policy = (new SnapshotSchedulePolicyFactory(new CanonicalJson()))->create([
            'store_id' => '1',
            'source_window_days' => '90',
            'minimum_popularity' => '5',
            'positive_result_limit' => '16',
            'zero_result_limit' => '4',
            'total_limit' => '20',
            'include_redirects' => '0',
            'interval_days' => '30',
            'retention_days' => '180',
            'first_run_at' => '2026-09-01T02:00:00+00:00',
        ]);

        self::assertSame(1, $policy->getStoreId());
        self::assertSame('2026-09-01T02:00:00+00:00', $policy->getNextRunAt());
        self::assertSame('2026-09-01T02:00:00+00:00', $policy->getScheduleAnchorAt());
        self::assertSame('2026-06-03T02:00:00+00:00', $policy->getPreviewParameters()['source_window_start']);
        self::assertSame('2026-09-01T02:00:00+00:00', $policy->getPreviewParameters()['source_window_end']);
        self::assertSame('2026-10-01T02:00:00+00:00', $policy->getFollowingRunAt());
        self::assertMatchesRegularExpression('/\A[0-9a-f]{64}\z/', $policy->getPolicyHash());
        self::assertSame(20, $policy->getMaximumSnapshotSize());
        self::assertFalse($policy->includesRedirects());
    }

    public function testRejectsRetentionShorterThanTheScheduleInterval(): void
    {
        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('retention');

        (new SnapshotSchedulePolicyFactory(new CanonicalJson()))->create([
            'store_id' => '1',
            'source_window_days' => '30',
            'minimum_popularity' => '1',
            'positive_result_limit' => '10',
            'zero_result_limit' => '5',
            'total_limit' => '15',
            'include_redirects' => '0',
            'interval_days' => '30',
            'retention_days' => '7',
            'first_run_at' => '2026-09-01T02:00:00+00:00',
        ]);
    }
}
