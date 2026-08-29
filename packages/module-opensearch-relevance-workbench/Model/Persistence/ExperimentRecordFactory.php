<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

use DateTimeImmutable;
use DateTimeZone;
use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\HumanExperimentPlan;

class ExperimentRecordFactory
{
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/iD';

    public function __construct(private readonly CanonicalJson $canonicalJson)
    {
    }

    public function create(
        HumanExperimentPlan $plan,
        int $storeId,
        string $experimentUuid,
        string $auditEventUuid,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): ExperimentPersistenceRecords {
        $this->assertUuid($experimentUuid);
        $this->assertUuid($auditEventUuid);

        if ($storeId < 1 || $actorId < 1) {
            throw new InvalidArgumentException('Experiment persistence requires a store and admin actor');
        }

        if ($correlationId === '' || strlen($correlationId) > 64) {
            throw new InvalidArgumentException('Experiment correlation ID must contain 1 to 64 characters');
        }

        $createdAt = (new DateTimeImmutable($createdAt))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d H:i:s');
        $experiment = [
            'experiment_uuid' => strtolower($experimentUuid),
            'store_id' => $storeId,
            'type' => 'HUMAN_RELEVANCE_COMPARISON',
            'state' => 'REMOTE_PENDING',
            'input_identities_json' => $this->canonicalJson->encode($plan->getInputIdentities()),
            'input_sha256' => $plan->getInputHash(),
            'primary_metric' => $plan->getPrimaryMetric(),
            'guardrails_json' => $this->canonicalJson->encode([
                'minimum_judged_coverage' => $plan->getMinimumJudgedCoverage(),
                'minimum_improvement' => $plan->getMinimumImprovement(),
            ]),
            'remote_experiment_ids_json' => $this->canonicalJson->encode([]),
            'srw_validation_state' => 'PENDING',
            'index_freshness_state' => 'FRESH',
            'aggregate_result_json' => $this->canonicalJson->encode([]),
            'per_query_result_json' => $this->canonicalJson->encode([]),
            'eligibility' => 'PENDING',
            'reason_codes_json' => $this->canonicalJson->encode([]),
            'accepted_by' => null,
            'accepted_at' => null,
            'created_at' => $createdAt,
        ];
        $auditEvent = [
            'event_uuid' => strtolower($auditEventUuid),
            'actor_type' => 'ADMIN',
            'actor_id' => (string)$actorId,
            'action' => 'EXPERIMENT_REGISTERED',
            'target_type' => 'EXPERIMENT',
            'target_uuid' => strtolower($experimentUuid),
            'before_identity_sha256' => null,
            'after_identity_sha256' => $plan->getInputHash(),
            'result' => 'SUCCESS',
            'reason_code' => 'THREE_EXPERIMENT_PLAN_FROZEN',
            'correlation_id' => $correlationId,
            'created_at' => $createdAt,
        ];

        return new ExperimentPersistenceRecords($experiment, $auditEvent);
    }

    private function assertUuid(string $uuid): void
    {
        if (preg_match(self::UUID_PATTERN, $uuid) !== 1) {
            throw new InvalidArgumentException('Experiment persistence identities must be UUIDs');
        }
    }
}
