<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Schedule;

use Magento\Framework\Lock\LockManagerInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\SnapshotScheduleRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\PrivacyDetector;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\QuerySnapshotPreviewer;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPolicy;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPreviewService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Schedule\ApprovedSnapshotSchedule;
use MageOS\OpenSearchRelevanceWorkbench\Model\Schedule\ScheduledDraftPreparer;
use MageOS\OpenSearchRelevanceWorkbench\Model\Schedule\SnapshotSchedulePolicyFactory;
use PHPUnit\Framework\TestCase;
use Psr\Log\LoggerInterface;

class ScheduledDraftPreparerTest extends TestCase
{
    public function testLockedDueScheduleCreatesDraftAndAdvancesOnlyAfterPersistence(): void
    {
        $scheduleUuid = '11111111-1111-4111-8111-111111111111';
        $now = '2026-09-01T02:05:00+00:00';
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
        $schedule = new ApprovedSnapshotSchedule($scheduleUuid, $policy);
        $preview = (new QuerySnapshotPreviewer(new PrivacyDetector(), new CanonicalJson()))->preview(
            1,
            [],
            new SnapshotPolicy(
                5,
                16,
                4,
                20,
                false,
                128,
                'osrw-privacy-v1',
                '2026-06-03T02:00:00+00:00',
                '2026-09-01T02:00:00+00:00'
            )
        );
        $scheduleRepository = $this->createMock(SnapshotScheduleRepository::class);
        $scheduleRepository->expects(self::once())->method('listDue')->with($now)->willReturn([$schedule]);
        $scheduleRepository->expects(self::once())->method('markPrepared')->with(
            $schedule,
            $now,
            self::callback(static fn (string $value): bool => strlen($value) === 32)
        );
        $previewService = $this->createMock(SnapshotPreviewService::class);
        $previewService->expects(self::once())->method('create')->with(
            $policy->getPreviewParameters()
        )->willReturn($preview);
        $snapshotRepository = $this->createMock(QuerySnapshotRepository::class);
        $snapshotRepository->expects(self::once())->method('saveDraft')->with(
            $preview,
            $scheduleUuid,
            $now,
            self::callback(static fn (string $value): bool => strlen($value) === 32)
        );
        $lockManager = $this->createMock(LockManagerInterface::class);
        $lockManager->expects(self::once())->method('lock')->willReturn(true);
        $lockManager->expects(self::once())->method('unlock');
        $logger = $this->createMock(LoggerInterface::class);
        $logger->expects(self::never())->method('error');

        (new ScheduledDraftPreparer(
            $scheduleRepository,
            $previewService,
            $snapshotRepository,
            $lockManager,
            $logger
        ))->prepare($now);
    }
}
