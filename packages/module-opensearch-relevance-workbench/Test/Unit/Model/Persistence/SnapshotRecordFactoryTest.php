<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Persistence;

use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\SnapshotRecordFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\PrivacyDetector;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\QuerySnapshotPreviewer;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPolicy;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\CuratedQueryMetadataFactory;
use PHPUnit\Framework\TestCase;

class SnapshotRecordFactoryTest extends TestCase
{
    public function testMapsOnlyApprovedTermsAndImmutableIdentitiesToPersistenceRecords(): void
    {
        $queryHash = hash('sha256', 'winter boots');
        $preview = (new QuerySnapshotPreviewer(new PrivacyDetector(), new CanonicalJson()))->preview(
            1,
            [
                $this->row(1, 'winter boots', 10, 4),
                $this->row(2, 'private@example.com', 9, 3),
            ],
            new SnapshotPolicy(1, 10, 10, 20, false, 128, 'osrw-privacy-v1'),
            (new CuratedQueryMetadataFactory())->create([
                $queryHash => ['category_id' => '42', 'brand_value' => 'Northwind'],
            ])
        );
        $approved = $preview->approve(
            $preview->getSnapshotHash(),
            42,
            '2026-08-26T15:00:00+00:00'
        );

        $records = (new SnapshotRecordFactory(new CanonicalJson()))->create(
            $preview,
            $approved,
            '11111111-1111-4111-8111-111111111111',
            ['22222222-2222-4222-8222-222222222222'],
            '33333333-3333-4333-8333-333333333333',
            'correlation-safe-1'
        );

        self::assertSame('APPROVED', $records->getSnapshot()['status']);
        self::assertSame($preview->getSnapshotHash(), $records->getSnapshot()['canonical_sha256']);
        self::assertSame(1, $records->getSnapshot()['selected_count']);
        self::assertSame(1, $records->getSnapshot()['excluded_count']);
        self::assertSame('winter boots', $records->getEntries()[0]['query_text']);
        self::assertSame(
            '{"brand_value":{"provenance":"MERCHANT_CURATED","value":"Northwind"},'
            . '"category_id":{"provenance":"MERCHANT_CURATED","value":"42"}}',
            $records->getEntries()[0]['custom_fields_json']
        );
        self::assertSame('SNAPSHOT_APPROVED', $records->getAuditEvent()['action']);
        self::assertSame($preview->getSnapshotHash(), $records->getAuditEvent()['after_identity_sha256']);
        self::assertStringNotContainsString(
            'private@example.com',
            json_encode([
                $records->getSnapshot(),
                $records->getEntries(),
                $records->getAuditEvent(),
            ], JSON_THROW_ON_ERROR)
        );
    }

    public function testScheduledRecordsRemainUnapprovedDraftsWithSystemProvenance(): void
    {
        $preview = (new QuerySnapshotPreviewer(new PrivacyDetector(), new CanonicalJson()))->preview(
            1,
            [$this->row(1, 'winter boots', 10, 4)],
            new SnapshotPolicy(
                1,
                10,
                10,
                20,
                false,
                128,
                'osrw-privacy-v1',
                '2026-06-01T00:00:00+00:00',
                '2026-09-01T00:00:00+00:00'
            )
        );
        $records = (new SnapshotRecordFactory(new CanonicalJson()))->createDraft(
            $preview,
            '44444444-4444-4444-8444-444444444444',
            '11111111-1111-4111-8111-111111111111',
            ['22222222-2222-4222-8222-222222222222'],
            '33333333-3333-4333-8333-333333333333',
            '2026-09-01T02:05:00+00:00',
            'scheduled-draft-1'
        );

        self::assertSame('DRAFT', $records->getSnapshot()['status']);
        self::assertNull($records->getSnapshot()['approved_by']);
        self::assertNull($records->getSnapshot()['approved_at']);
        self::assertSame(
            '44444444-4444-4444-8444-444444444444',
            $records->getSnapshot()['schedule_uuid']
        );
        self::assertSame('SYSTEM', $records->getAuditEvent()['actor_type']);
        self::assertSame('CRON', $records->getAuditEvent()['actor_id']);
        self::assertSame('SCHEDULED_DRAFT_ONLY', $records->getAuditEvent()['reason_code']);
    }

    /**
     * @return array<string, int|string|null>
     */
    private function row(int $queryId, string $queryText, int $popularity, int $resultCount): array
    {
        return [
            'query_id' => $queryId,
            'query_text' => $queryText,
            'popularity' => $popularity,
            'num_results' => $resultCount,
            'redirect' => null,
            'store_id' => 1,
            'is_active' => 1,
            'updated_at' => '2026-08-26 12:00:00',
        ];
    }
}
