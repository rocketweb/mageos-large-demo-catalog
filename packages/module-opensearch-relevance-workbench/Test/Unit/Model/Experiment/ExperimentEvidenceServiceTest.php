<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Experiment;

use MageOS\OpenSearchRelevanceWorkbench\Api\IndexEvidenceCaptureInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\PersistedBaselineConfiguration;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\EvidenceReport;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\ExperimentEvidenceService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\PersistedExperiment;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\ProductMovementClassifier;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\ProductContextProvider;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\IndexEvidence;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\ApprovedQuerySnapshot;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\QuerySnapshotEntry;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPolicy;
use PHPUnit\Framework\TestCase;

class ExperimentEvidenceServiceTest extends TestCase
{
    public function testBuildsQueryEvidenceAndMarksDeletedProductsUnavailable(): void
    {
        $snapshotUuid = '11111111-1111-4111-8111-111111111111';
        $baselineUuid = '22222222-2222-4222-8222-222222222222';
        $experimentUuid = '33333333-3333-4333-8333-333333333333';
        $queryHash = hash('sha256', 'known query');
        $snapshotHash = str_repeat('a', 64);
        $baselineHash = str_repeat('b', 64);
        $indexHash = str_repeat('c', 64);
        $snapshot = new ApprovedQuerySnapshot(
            1,
            [new QuerySnapshotEntry(1, 'known query', $queryHash, 10, 2, '2026-08-26 12:00:00')],
            new SnapshotPolicy(1, 10, 5, 15, false, 128, 'osrw-privacy-v1'),
            ['updated_at' => '2026-08-26 12:00:00', 'query_id' => 1],
            $snapshotHash,
            1,
            '2026-08-26T12:30:00+00:00'
        );
        $baseline = new PersistedBaselineConfiguration(
            $baselineUuid,
            1,
            new BaselineTemplate(['index' => 'products', 'body' => []], [], str_repeat('d', 64)),
            [],
            '44444444-4444-4444-8444-444444444444',
            'products',
            'products-v1',
            $indexHash,
            '',
            $baselineHash
        );
        $evidence = new EvidenceReport(
            'NDCG@10',
            0.5,
            1.0,
            0.5,
            1.0,
            [[
                'query_hash' => $queryHash,
                'baseline_ndcg_at_10' => 0.5,
                'candidate_ndcg_at_10' => 1.0,
                'delta' => 0.5,
                'judged_union_count' => 2,
                'union_count' => 2,
                'known_item_regression' => false,
                'baseline_document_ids' => ['available', 'deleted'],
                'candidate_document_ids' => ['deleted', 'available'],
            ]],
            'EXPLORATORY',
            ['MERCHANT_ACCEPTANCE_REQUIRED']
        );
        $experiment = new PersistedExperiment(
            $experimentUuid,
            1,
            'LOCAL_EVIDENCE_READY',
            [
                'query_snapshot_id' => $snapshotUuid,
                'query_snapshot_sha256' => $snapshotHash,
                'baseline_configuration_uuid' => $baselineUuid,
                'baseline_configuration_sha256' => $baselineHash,
                'index_evidence_sha256' => $indexHash,
            ],
            str_repeat('e', 64),
            [],
            $evidence,
            null,
            null
        );
        $experimentRepository = $this->createMock(ExperimentRepository::class);
        $experimentRepository->expects(self::once())
            ->method('getCompleted')->with($experimentUuid)->willReturn($experiment);
        $snapshotRepository = $this->createMock(QuerySnapshotRepository::class);
        $snapshotRepository->expects(self::once())
            ->method('getApproved')->with($snapshotUuid)->willReturn($snapshot);
        $baselineRepository = $this->createMock(BaselineConfigurationRepository::class);
        $baselineRepository->expects(self::once())
            ->method('get')->with($baselineUuid)->willReturn($baseline);
        $indexEvidenceCapture = $this->createMock(IndexEvidenceCaptureInterface::class);
        $indexEvidenceCapture->expects(self::once())
            ->method('capture')->with('products')->willReturn(new IndexEvidence(
            'products',
            'products-v1',
            'index-uuid',
            str_repeat('f', 64),
            str_repeat('0', 64),
            [],
            2,
            $indexHash
        ));
        $productContextProvider = $this->createMock(ProductContextProvider::class);
        $productContextProvider->expects(self::once())
            ->method('get')->with(
                'products-v1',
                ['available', 'deleted']
            )->willReturn(['available' => ['name' => 'Available product', 'sku' => 'SKU-1']]);
        $result = (new ExperimentEvidenceService(
            $experimentRepository,
            $snapshotRepository,
            $baselineRepository,
            $indexEvidenceCapture,
            $productContextProvider,
            new ProductMovementClassifier()
        ))->build($experimentUuid);

        self::assertSame('FRESH', $result['index_state']);
        self::assertSame('PARTIAL', $result['product_context_state']);
        self::assertSame('known query', $result['queries'][0]['query_text']);
        self::assertFalse($result['queries'][0]['is_regression']);
        self::assertSame([], $result['regressions']);
        self::assertFalse($result['queries'][0]['products'][0]['available']);
        self::assertSame('Product unavailable', $result['queries'][0]['products'][0]['name']);
    }
}
