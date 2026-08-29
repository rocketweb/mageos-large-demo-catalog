<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Schedule;

use Magento\Framework\Lock\LockManagerInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\SnapshotScheduleRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPreviewService;
use Psr\Log\LoggerInterface;
use Throwable;

class ScheduledDraftPreparer
{
    public function __construct(
        private readonly SnapshotScheduleRepository $scheduleRepository,
        private readonly SnapshotPreviewService $previewService,
        private readonly QuerySnapshotRepository $snapshotRepository,
        private readonly LockManagerInterface $lockManager,
        private readonly LoggerInterface $logger
    ) {
    }

    public function prepare(string $now): void
    {
        foreach ($this->scheduleRepository->listDue($now) as $schedule) {
            $lockName = 'osrw_snapshot_schedule_' . $schedule->getScheduleUuid();

            if (!$this->lockManager->lock($lockName, 0)) {
                continue;
            }

            try {
                $correlationId = bin2hex(random_bytes(16));
                $preview = $this->previewService->create(
                    $schedule->getPolicy()->getPreviewParameters()
                );
                $this->snapshotRepository->saveDraft(
                    $preview,
                    $schedule->getScheduleUuid(),
                    $now,
                    $correlationId
                );
                $this->scheduleRepository->markPrepared($schedule, $now, $correlationId);
            } catch (Throwable $exception) {
                $this->logger->error(
                    'Scheduled relevance snapshot draft preparation failed',
                    [
                        'schedule_uuid' => $schedule->getScheduleUuid(),
                        'exception' => $exception,
                    ]
                );
            } finally {
                $this->lockManager->unlock($lockName);
            }
        }
    }
}
