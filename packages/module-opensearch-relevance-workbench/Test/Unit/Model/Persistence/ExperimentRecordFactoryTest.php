<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Persistence;

use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\HumanExperimentPlanFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRecordFactory;
use PHPUnit\Framework\TestCase;

class ExperimentRecordFactoryTest extends TestCase
{
    public function testCreatesFrozenPendingExperimentAndAuditRecords(): void
    {
        $canonicalJson = new CanonicalJson();
        $plan = (new HumanExperimentPlanFactory($canonicalJson))->create(
            '11111111-1111-4111-8111-111111111111',
            str_repeat('a', 64),
            '22222222-2222-4222-8222-222222222222',
            '33333333-3333-4333-8333-333333333333',
            str_repeat('b', 64),
            '44444444-4444-4444-8444-444444444444',
            str_repeat('c', 64),
            '55555555-5555-4555-8555-555555555555',
            str_repeat('d', 64),
            str_repeat('e', 64),
            10,
            1.0,
            'NDCG@10',
            0.01
        );
        $records = (new ExperimentRecordFactory($canonicalJson))->create(
            $plan,
            1,
            '66666666-6666-4666-8666-666666666666',
            '77777777-7777-4777-8777-777777777777',
            42,
            '2026-08-26T18:00:00+00:00',
            'experiment-correlation'
        );

        self::assertSame('REMOTE_PENDING', $records->getExperiment()['state']);
        self::assertSame($plan->getInputHash(), $records->getExperiment()['input_sha256']);
        self::assertStringContainsString(
            'remote_query_set_id',
            (string)$records->getExperiment()['input_identities_json']
        );
        self::assertStringContainsString(
            'minimum_improvement',
            (string)$records->getExperiment()['guardrails_json']
        );
        self::assertSame('EXPERIMENT_REGISTERED', $records->getAuditEvent()['action']);
        self::assertSame('THREE_EXPERIMENT_PLAN_FROZEN', $records->getAuditEvent()['reason_code']);
    }
}
