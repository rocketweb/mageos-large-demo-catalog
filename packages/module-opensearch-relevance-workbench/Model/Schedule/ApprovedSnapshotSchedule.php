<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Schedule;

class ApprovedSnapshotSchedule
{
    public function __construct(
        private readonly string $scheduleUuid,
        private readonly SnapshotSchedulePolicy $policy
    ) {
    }

    public function getScheduleUuid(): string
    {
        return $this->scheduleUuid;
    }

    public function getPolicy(): SnapshotSchedulePolicy
    {
        return $this->policy;
    }
}
