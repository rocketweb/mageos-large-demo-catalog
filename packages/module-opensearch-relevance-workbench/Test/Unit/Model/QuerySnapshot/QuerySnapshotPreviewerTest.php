<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\QuerySnapshot;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\PrivacyDetector;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\QuerySnapshotPreviewer;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPolicy;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\CuratedQueryMetadataFactory;
use PHPUnit\Framework\TestCase;

class QuerySnapshotPreviewerTest extends TestCase
{
    public function testBuildsDeterministicStoreScopedPrivacyFilteredSnapshot(): void
    {
        $rows = [
            $this->row(9, 'matt@example.com', 20, 4, false, 1),
            $this->row(8, 'redirected boots', 18, 5, true, 1),
            $this->row(7, 'winter boots', 15, 6, false, 1),
            $this->row(6, 'red dress', 10, 3, false, 1),
            $this->row(5, 'zero result torso', 8, 0, false, 1),
            $this->row(4, 'zero result tail', 5, 0, false, 1),
            $this->row(3, 'low popularity', 2, 2, false, 1),
            $this->row(2, 'other store', 50, 7, false, 2),
        ];
        $policy = new SnapshotPolicy(
            minimumPopularity: 5,
            positiveResultLimit: 2,
            zeroResultLimit: 1,
            totalLimit: 3,
            includeRedirects: false,
            maximumTermLength: 128,
            privacyPolicyVersion: 'osrw-privacy-v1'
        );
        $previewer = new QuerySnapshotPreviewer(new PrivacyDetector(), new CanonicalJson());

        $first = $previewer->preview(1, $rows, $policy);
        $second = $previewer->preview(1, array_reverse($rows), $policy);

        self::assertSame($first->getSnapshotHash(), $second->getSnapshotHash());
        self::assertSame(7, $first->getSourceCount());
        self::assertSame(3, $first->getSelectedCount());
        self::assertSame(
            ['winter boots', 'red dress', 'zero result torso'],
            array_map(
                static fn ($entry): string => $entry->getQueryText(),
                $first->getEntries()
            )
        );
        self::assertSame(
            [
                'BELOW_MINIMUM_POPULARITY' => 1,
                'EMAIL_ADDRESS' => 1,
                'REDIRECT_EXCLUDED' => 1,
                'ZERO_RESULT_LIMIT_REACHED' => 1,
            ],
            $first->getExcludedCounts()
        );
        self::assertSame(
            ['updated_at' => '2026-08-26 12:00:00', 'query_id' => 9],
            $first->getHighWaterBoundary()
        );

        $approved = $first->approve(
            $first->getSnapshotHash(),
            42,
            '2026-08-26T12:30:00+00:00'
        );

        self::assertSame('APPROVED', $approved->getStatus());
        self::assertSame(42, $approved->getApprovedBy());
        self::assertSame($first->getSnapshotHash(), $approved->getSnapshotHash());
        self::assertSame(
            [
                ['queryText' => 'winter boots'],
                ['queryText' => 'red dress'],
                ['queryText' => 'zero result torso'],
            ],
            $approved->getRemoteQuerySetEntries()
        );
    }

    public function testApprovalIsBoundToExactPreviewHash(): void
    {
        $preview = (new QuerySnapshotPreviewer(new PrivacyDetector(), new CanonicalJson()))->preview(
            1,
            [$this->row(1, 'boots', 10, 3, false, 1)],
            new SnapshotPolicy(1, 10, 10, 20, false, 128, 'osrw-privacy-v1')
        );

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Snapshot approval hash does not match the preview');

        $preview->approve(str_repeat('a', 64), 42, '2026-08-26T12:30:00+00:00');
    }

    public function testCuratedMetadataChangesSnapshotIdentityAndRemoteQuerySetFields(): void
    {
        $row = $this->row(1, 'winter boots', 10, 3, false, 1);
        $queryHash = hash('sha256', 'winter boots');
        $metadata = (new CuratedQueryMetadataFactory())->create([
            $queryHash => ['category_id' => '42', 'brand_value' => 'Northwind'],
        ]);
        $previewer = new QuerySnapshotPreviewer(new PrivacyDetector(), new CanonicalJson());
        $policy = new SnapshotPolicy(1, 10, 10, 20, false, 128, 'osrw-privacy-v1');
        $withoutMetadata = $previewer->preview(1, [$row], $policy);
        $withMetadata = $previewer->preview(1, [$row], $policy, $metadata);

        self::assertNotSame($withoutMetadata->getSnapshotHash(), $withMetadata->getSnapshotHash());
        self::assertSame(
            [[
                'queryText' => 'winter boots',
                'customFields' => ['brand_value' => 'Northwind', 'category_id' => '42'],
            ]],
            $withMetadata->approve(
                $withMetadata->getSnapshotHash(),
                42,
                '2026-08-26T12:30:00+00:00'
            )->getRemoteQuerySetEntries()
        );
    }

    public function testRejectsRowsOutsideTheSelectedStoreBeforeHashing(): void
    {
        $preview = (new QuerySnapshotPreviewer(new PrivacyDetector(), new CanonicalJson()))->preview(
            1,
            [$this->row(1, 'other store', 10, 3, false, 2)],
            new SnapshotPolicy(1, 10, 10, 20, false, 128, 'osrw-privacy-v1')
        );

        self::assertSame(0, $preview->getSourceCount());
        self::assertSame(0, $preview->getSelectedCount());
        self::assertSame([], $preview->getEntries());
    }

    /**
     * @return array{
     *     query_id: int,
     *     query_text: string,
     *     popularity: int,
     *     num_results: int,
     *     redirect: string|null,
     *     store_id: int,
     *     is_active: int,
     *     updated_at: string
     * }
     */
    private function row(
        int $queryId,
        string $queryText,
        int $popularity,
        int $resultCount,
        bool $redirect,
        int $storeId
    ): array {
        return [
            'query_id' => $queryId,
            'query_text' => $queryText,
            'popularity' => $popularity,
            'num_results' => $resultCount,
            'redirect' => $redirect ? '/redirect' : null,
            'store_id' => $storeId,
            'is_active' => 1,
            'updated_at' => '2026-08-26 12:00:00',
        ];
    }
}
