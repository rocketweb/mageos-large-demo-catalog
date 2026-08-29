<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Activation;

use MageOS\OpenSearchRelevanceWorkbench\Api\IndexEvidenceCaptureInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Activation\LiveActivationService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\PersistedBaselineConfiguration;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\PersistedCandidateConfiguration;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\EvidenceReport;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\PersistedExperiment;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\IndexEvidence;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\CandidateConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\LiveActivationRepository;
use PHPUnit\Framework\TestCase;
use RuntimeException;

class LiveActivationServiceTest extends TestCase
{
    public function testActivatesOnlyAnAcceptedWinnerWithFreshExactEvidence(): void
    {
        [$experiment, $baseline, $candidate] = $this->fixtures();
        $experiments = $this->createStub(ExperimentRepository::class);
        $experiments->method('getCompleted')->willReturn($experiment);
        $baselines = $this->createStub(BaselineConfigurationRepository::class);
        $baselines->method('get')->willReturn($baseline);
        $candidates = $this->createStub(CandidateConfigurationRepository::class);
        $candidates->method('get')->willReturn($candidate);
        $capture = $this->createMock(IndexEvidenceCaptureInterface::class);
        $capture->expects(self::once())
            ->method('capture')
            ->with('catalog_product_1')
            ->willReturn($this->indexEvidence(str_repeat('c', 64)));
        $activations = $this->createMock(LiveActivationRepository::class);
        $activations->expects(self::once())->method('activate')->with(
            1,
            $experiment->getExperimentUuid(),
            $candidate->getConfigurationUuid(),
            $candidate->getTransformation(),
            $candidate->getConfigurationHash(),
            $baseline->getIndexEvidenceHash(),
            $baseline->getTargetAlias(),
            7,
            '2026-08-28T12:00:00+00:00',
            'activate-lab-candidate'
        )->willReturn('77777777-7777-4777-8777-777777777777');
        $service = new LiveActivationService($experiments, $baselines, $candidates, $capture, $activations);

        self::assertSame(
            '77777777-7777-4777-8777-777777777777',
            $service->activate(
                $experiment->getExperimentUuid(),
                7,
                '2026-08-28T12:00:00+00:00',
                'activate-lab-candidate'
            )
        );
    }

    public function testRefusesActivationAfterTheCatalogIndexChanges(): void
    {
        [$experiment, $baseline, $candidate] = $this->fixtures();
        $experiments = $this->createStub(ExperimentRepository::class);
        $experiments->method('getCompleted')->willReturn($experiment);
        $baselines = $this->createStub(BaselineConfigurationRepository::class);
        $baselines->method('get')->willReturn($baseline);
        $candidates = $this->createStub(CandidateConfigurationRepository::class);
        $candidates->method('get')->willReturn($candidate);
        $capture = $this->createStub(IndexEvidenceCaptureInterface::class);
        $capture->method('capture')->willReturn($this->indexEvidence(str_repeat('9', 64)));
        $activations = $this->createMock(LiveActivationRepository::class);
        $activations->expects(self::never())->method('activate');
        $service = new LiveActivationService($experiments, $baselines, $candidates, $capture, $activations);

        $this->expectException(RuntimeException::class);
        $this->expectExceptionMessage('index evidence is stale');

        $service->activate(
            $experiment->getExperimentUuid(),
            7,
            '2026-08-28T12:00:00+00:00',
            'activate-stale-candidate'
        );
    }

    /**
     * @return array{PersistedExperiment, PersistedBaselineConfiguration, PersistedCandidateConfiguration}
     */
    private function fixtures(): array
    {
        $experimentUuid = '11111111-1111-4111-8111-111111111111';
        $baselineUuid = '22222222-2222-4222-8222-222222222222';
        $candidateUuid = '33333333-3333-4333-8333-333333333333';
        $baselineHash = str_repeat('a', 64);
        $candidateHash = str_repeat('b', 64);
        $indexHash = str_repeat('c', 64);
        $template = new BaselineTemplate(
            ['query' => ['match' => ['name' => ['query' => '{{queryText}}']]]],
            ['/query/match/name/query'],
            str_repeat('d', 64)
        );
        $experiment = new PersistedExperiment(
            $experimentUuid,
            1,
            'ACCEPTED',
            [
                'baseline_configuration_uuid' => $baselineUuid,
                'baseline_configuration_sha256' => $baselineHash,
                'candidate_configuration_uuid' => $candidateUuid,
                'candidate_configuration_sha256' => $candidateHash,
                'index_evidence_sha256' => $indexHash,
            ],
            str_repeat('e', 64),
            [],
            new EvidenceReport('NDCG@10', 0.4, 0.7, 0.3, 1.0, [], 'WINNER', []),
            7,
            '2026-08-28 11:50:00'
        );
        $baseline = new PersistedBaselineConfiguration(
            $baselineUuid,
            1,
            $template,
            [],
            '44444444-4444-4444-8444-444444444444',
            'catalog_product_1',
            'catalog_product_1_v6',
            $indexHash,
            '',
            $baselineHash
        );
        $candidate = new PersistedCandidateConfiguration(
            $candidateUuid,
            1,
            $baselineUuid,
            $template,
            ['type' => 'FIELD_BOOST', 'boosts' => ['name' => 2.0]],
            '44444444-4444-4444-8444-444444444444',
            'catalog_product_1_v6',
            $candidateHash
        );

        return [$experiment, $baseline, $candidate];
    }

    private function indexEvidence(string $hash): IndexEvidence
    {
        return new IndexEvidence(
            'catalog_product_1',
            'catalog_product_1_v6',
            'index-uuid',
            str_repeat('1', 64),
            str_repeat('2', 64),
            [],
            816,
            $hash
        );
    }
}
