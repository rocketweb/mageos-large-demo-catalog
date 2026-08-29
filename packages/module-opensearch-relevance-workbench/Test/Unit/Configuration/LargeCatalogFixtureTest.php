<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Configuration;

use PHPUnit\Framework\TestCase;

class LargeCatalogFixtureTest extends TestCase
{
    public function testLargeCatalogRunnerUsesThePinnedMageOsSmallProfile(): void
    {
        $runner = $this->readRepositoryFile('dev/ci/run-large-catalog.sh');

        self::assertStringContainsString('dev/ci/run.sh', $runner);
        self::assertStringContainsString(
            'setup/performance-toolkit/profiles/ce/osrw-catalog-small.xml',
            $runner
        );
        self::assertStringContainsString('prepare-large-catalog-profile.php', $runner);
        self::assertStringContainsString('setup:perf:generate-fixtures', $runner);
        self::assertStringContainsString('indexer:reindex catalogsearch_fulltext', $runner);
        self::assertStringContainsString('assert-large-catalog.php', $runner);
    }

    public function testCatalogProfilePreparerRemovesUnneededAccountAndOrderFixtures(): void
    {
        $preparer = $this->readRepositoryFile('dev/ci/prepare-large-catalog-profile.php');

        foreach (
            [
                'admin_users',
                'customers',
                'catalog_price_rules',
                'cart_price_rules',
                'coupon_codes',
                'orders',
            ] as $element
        ) {
            self::assertStringContainsString("'/config/profile/{$element}' => '0'", $preparer);
        }
    }

    public function testLargeCatalogAssertionExercisesRealCatalogDataThroughTheWorkbench(): void
    {
        $assertion = $this->readRepositoryFile('dev/ci/assert-large-catalog.php');

        self::assertStringContainsString("getTableName('catalog_product_entity')", $assertion);
        self::assertStringContainsString('MINIMUM_CATALOG_PRODUCTS = 800', $assertion);
        self::assertStringContainsString('SnapshotPreviewService::class', $assertion);
        self::assertStringContainsString('StockBaselineCaptureService::class', $assertion);
        self::assertStringContainsString('CandidateValidationService::class', $assertion);
        self::assertStringContainsString('HumanRatingQueueService::class', $assertion);
    }

    private function readRepositoryFile(string $relativePath): string
    {
        $path = dirname(__DIR__, 3) . '/' . $relativePath;

        self::assertFileExists($path);
        $contents = file_get_contents($path);
        self::assertIsString($contents);

        return $contents;
    }
}
