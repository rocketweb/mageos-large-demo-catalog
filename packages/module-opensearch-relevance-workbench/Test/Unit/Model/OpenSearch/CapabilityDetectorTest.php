<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\OpenSearch;

use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\CapabilityDetector;
use PHPUnit\Framework\TestCase;

class CapabilityDetectorTest extends TestCase
{
    public function testReportsCoreAndLlmReadinessForPinnedCapabilities(): void
    {
        $detector = new CapabilityDetector();

        $report = $detector->detect(
            '3.8.0',
            ['opensearch-ml', 'opensearch-search-relevance'],
            true
        );

        self::assertTrue($report->isCoreReady());
        self::assertTrue($report->isLlmReady());
        self::assertSame([], $report->getReasonCodes());
    }

    public function testKeepsHumanWorkflowReadyWhenMlCommonsIsMissing(): void
    {
        $detector = new CapabilityDetector();

        $report = $detector->detect('3.8.1', ['opensearch-search-relevance'], true);

        self::assertTrue($report->isCoreReady());
        self::assertFalse($report->isLlmReady());
        self::assertSame(['ML_COMMONS_PLUGIN_MISSING'], $report->getReasonCodes());
    }

    public function testReportsAllBlockingCapabilityFailures(): void
    {
        $detector = new CapabilityDetector();

        $report = $detector->detect('4.0.0', ['search-relevance'], false);

        self::assertFalse($report->isCoreReady());
        self::assertFalse($report->isLlmReady());
        self::assertSame(
            [
                'OPENSEARCH_VERSION_UNSUPPORTED',
                'SEARCH_RELEVANCE_PLUGIN_MISSING',
                'WORKBENCH_UNAVAILABLE',
                'ML_COMMONS_PLUGIN_MISSING',
            ],
            $report->getReasonCodes()
        );
    }
}
