<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Cron;

use MageOS\OpenSearchRelevanceWorkbench\Model\Schedule\ScheduledDraftPreparer;

class PrepareSnapshotDrafts
{
    public function __construct(private readonly ScheduledDraftPreparer $preparer)
    {
    }

    public function execute(): void
    {
        $this->preparer->prepare(gmdate(DATE_RFC3339));
    }
}
