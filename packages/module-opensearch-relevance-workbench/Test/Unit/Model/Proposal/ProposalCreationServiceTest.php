<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Proposal;

use MageOS\OpenSearchRelevanceWorkbench\Api\IndexEvidenceCaptureInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\PersistedBaselineConfiguration;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\EvidenceReport;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\PersistedExperiment;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\IndexEvidence;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\CandidateConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ProposalRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\UuidGenerator;
use MageOS\OpenSearchRelevanceWorkbench\Model\Proposal\ProposalCreationService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Proposal\ProposalExporter;
use PHPUnit\Framework\TestCase;
use RuntimeException;

class ProposalCreationServiceTest extends TestCase
{
    public function testAcceptedWinnerCannotExportAfterItsIndexEvidenceChanges(): void
    {
        $experimentUuid = '11111111-1111-4111-8111-111111111111';
        $baselineUuid = '22222222-2222-4222-8222-222222222222';
        $candidateUuid = '33333333-3333-4333-8333-333333333333';
        $baselineHash = str_repeat('a', 64);
        $candidateHash = str_repeat('b', 64);
        $indexHash = str_repeat('c', 64);
        $experiment = new PersistedExperiment(
            $experimentUuid,
            1,
            'ACCEPTED',
            [
                'query_snapshot_sha256' => str_repeat('d', 64),
                'judgment_sha256' => str_repeat('e', 64),
                'index_evidence_sha256' => $indexHash,
                'baseline_configuration_uuid' => $baselineUuid,
                'baseline_configuration_sha256' => $baselineHash,
                'candidate_configuration_uuid' => $candidateUuid,
                'candidate_configuration_sha256' => $candidateHash,
            ],
            str_repeat('f', 64),
            [],
            new EvidenceReport('NDCG@10', 0.5, 1.0, 0.5, 1.0, [], 'WINNER', []),
            1,
            '2026-08-26 12:00:00'
        );
        $baseline = new PersistedBaselineConfiguration(
            $baselineUuid,
            1,
            new BaselineTemplate(['index' => 'products', 'body' => []], [], str_repeat('0', 64)),
            [],
            '44444444-4444-4444-8444-444444444444',
            'products',
            'products-v1',
            $indexHash,
            '',
            $baselineHash
        );
        $experimentRepository = $this->createMock(ExperimentRepository::class);
        $experimentRepository->expects(self::once())
            ->method('getCompleted')->with($experimentUuid)->willReturn($experiment);
        $baselineRepository = $this->createMock(BaselineConfigurationRepository::class);
        $baselineRepository->expects(self::once())
            ->method('get')->with($baselineUuid)->willReturn($baseline);
        $candidateRepository = $this->createMock(CandidateConfigurationRepository::class);
        $candidateRepository->expects(self::never())->method('get');
        $proposalRepository = $this->createMock(ProposalRepository::class);
        $proposalRepository->expects(self::never())->method('getByExperimentId');
        $indexEvidenceCapture = $this->createMock(IndexEvidenceCaptureInterface::class);
        $indexEvidenceCapture->expects(self::once())->method('capture')->with('products')->willReturn(
            new IndexEvidence(
                'products',
                'products-v1',
                'index-uuid',
                str_repeat('1', 64),
                str_repeat('2', 64),
                [],
                1,
                str_repeat('3', 64)
            )
        );
        $service = new ProposalCreationService(
            $experimentRepository,
            $baselineRepository,
            $candidateRepository,
            $proposalRepository,
            new ProposalExporter(new CanonicalJson()),
            new UuidGenerator(),
            $indexEvidenceCapture
        );

        $this->expectException(RuntimeException::class);
        $this->expectExceptionMessage('index evidence is stale');

        $service->create($experimentUuid, 1, '2026-08-26T13:00:00+00:00', 'proposal-stale-index');
    }
}
