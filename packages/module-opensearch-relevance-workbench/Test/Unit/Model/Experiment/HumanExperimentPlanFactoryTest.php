<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Experiment;

use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\HumanExperimentPlanFactory;
use PHPUnit\Framework\TestCase;

class HumanExperimentPlanFactoryTest extends TestCase
{
    public function testFreezesPairwiseAndTwoPointwiseExperiments(): void
    {
        $plan = (new HumanExperimentPlanFactory(new CanonicalJson()))->create(
            querySnapshotId: '11111111-1111-4111-8111-111111111111',
            querySnapshotHash: str_repeat('a', 64),
            remoteQuerySetId: '22222222-2222-4222-8222-222222222222',
            baselineConfigurationId: '33333333-3333-4333-8333-333333333333',
            baselineConfigurationHash: str_repeat('b', 64),
            candidateConfigurationId: '44444444-4444-4444-8444-444444444444',
            candidateConfigurationHash: str_repeat('c', 64),
            judgmentId: '55555555-5555-4555-8555-555555555555',
            judgmentHash: str_repeat('d', 64),
            indexEvidenceHash: str_repeat('e', 64),
            resultDepth: 10,
            minimumJudgedCoverage: 0.9,
            primaryMetric: 'NDCG@10',
            minimumImprovement: 0.02,
            baselineLocalConfigurationId: '66666666-6666-4666-8666-666666666666',
            candidateLocalConfigurationId: '77777777-7777-4777-8777-777777777777',
            localJudgmentId: '88888888-8888-4888-8888-888888888888'
        );

        self::assertSame(
            [
                'PAIRWISE_COMPARISON' => [
                    'querySetId' => '22222222-2222-4222-8222-222222222222',
                    'searchConfigurationList' => [
                        '33333333-3333-4333-8333-333333333333',
                        '44444444-4444-4444-8444-444444444444',
                    ],
                    'size' => 10,
                    'type' => 'PAIRWISE_COMPARISON',
                ],
                'POINTWISE_BASELINE' => [
                    'querySetId' => '22222222-2222-4222-8222-222222222222',
                    'searchConfigurationList' => ['33333333-3333-4333-8333-333333333333'],
                    'judgmentList' => ['55555555-5555-4555-8555-555555555555'],
                    'size' => 10,
                    'type' => 'POINTWISE_EVALUATION',
                ],
                'POINTWISE_CANDIDATE' => [
                    'querySetId' => '22222222-2222-4222-8222-222222222222',
                    'searchConfigurationList' => ['44444444-4444-4444-8444-444444444444'],
                    'judgmentList' => ['55555555-5555-4555-8555-555555555555'],
                    'size' => 10,
                    'type' => 'POINTWISE_EVALUATION',
                ],
            ],
            $plan->getRemotePayloads()
        );
        self::assertMatchesRegularExpression('/\A[0-9a-f]{64}\z/', $plan->getInputHash());
        self::assertSame('NDCG@10', $plan->getPrimaryMetric());
        self::assertSame(0.9, $plan->getMinimumJudgedCoverage());
        self::assertSame(0.02, $plan->getMinimumImprovement());
        self::assertSame(
            str_repeat('a', 64),
            $plan->getInputIdentities()['query_snapshot_sha256']
        );
        self::assertSame(
            '77777777-7777-4777-8777-777777777777',
            $plan->getInputIdentities()['candidate_configuration_uuid']
        );
        self::assertSame(2, $plan->getInputIdentities()['evidence_schema_version']);
    }
}
