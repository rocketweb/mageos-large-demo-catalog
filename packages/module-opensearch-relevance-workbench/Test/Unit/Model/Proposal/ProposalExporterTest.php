<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Proposal;

use LogicException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\EvidenceReport;
use MageOS\OpenSearchRelevanceWorkbench\Model\Proposal\ProposalExporter;
use PHPUnit\Framework\TestCase;

class ProposalExporterTest extends TestCase
{
    public function testExportsCanonicalReviewOnlyProposalWithContentHash(): void
    {
        $export = (new ProposalExporter(new CanonicalJson()))->export(
            proposalId: '11111111-1111-4111-8111-111111111111',
            createdAt: '2026-08-26T14:00:00+00:00',
            storeId: 1,
            experimentId: '22222222-2222-4222-8222-222222222222',
            querySnapshotHash: str_repeat('a', 64),
            judgmentHash: str_repeat('b', 64),
            indexEvidenceHash: str_repeat('c', 64),
            baselineConfigurationHash: str_repeat('d', 64),
            candidateConfigurationHash: str_repeat('e', 64),
            candidateTransformation: ['type' => 'FIELD_BOOST', 'boosts' => ['name' => 5.0]],
            evidence: new EvidenceReport(
                'NDCG@10',
                0.5,
                0.75,
                0.25,
                1.0,
                [],
                'WINNER',
                []
            ),
            warnings: ['Offline relevance evidence does not establish revenue lift.']
        );
        $artifact = json_decode($export->getCanonicalJson(), true, flags: JSON_THROW_ON_ERROR);

        self::assertSame('mageos-opensearch-relevance-proposal/v1', $artifact['schema']);
        self::assertSame('review_only', $artifact['target_type']);
        self::assertSame(false, $artifact['application']['supported']);
        self::assertSame('Version 1 is export only', $artifact['application']['reason']);
        self::assertSame('WINNER', $artifact['evidence']['eligibility']);
        self::assertSame(hash('sha256', $export->getCanonicalJson()), $export->getArtifactHash());
        self::assertSame(
            'osrw-proposal-11111111-1111-4111-8111-111111111111-' . substr($export->getArtifactHash(), 0, 12) . '.json',
            $export->getFilename()
        );
        self::assertStringNotContainsString('credential', $export->getCanonicalJson());
        self::assertStringNotContainsString('vector', $export->getCanonicalJson());
    }

    public function testRefusesExportWhenEvidenceIsNotWinner(): void
    {
        $this->expectException(LogicException::class);
        $this->expectExceptionMessage('Only accepted WINNER evidence may be exported');

        (new ProposalExporter(new CanonicalJson()))->export(
            '11111111-1111-4111-8111-111111111111',
            '2026-08-26T14:00:00+00:00',
            1,
            '22222222-2222-4222-8222-222222222222',
            str_repeat('a', 64),
            str_repeat('b', 64),
            str_repeat('c', 64),
            str_repeat('d', 64),
            str_repeat('e', 64),
            ['type' => 'FIELD_BOOST', 'boosts' => ['name' => 5.0]],
            new EvidenceReport('NDCG@10', 0.5, 0.5, 0.0, 1.0, [], 'INCONCLUSIVE', ['PRIMARY_METRIC_THRESHOLD_NOT_MET']),
            []
        );
    }
}
