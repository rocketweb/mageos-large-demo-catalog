<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

use DateTimeImmutable;
use DateTimeZone;
use InvalidArgumentException;
use Magento\Framework\App\ResourceConnection;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\EvidenceReport;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\HumanExperimentPlan;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\PersistedExperiment;
use RuntimeException;
use Throwable;
use UnexpectedValueException;

class ExperimentRepository
{
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/iD';
    private const EXPERIMENT_TABLE = 'osrw_experiment';
    private const AUDIT_TABLE = 'osrw_audit_event';
    private const REMOTE_KINDS = [
        'PAIRWISE_COMPARISON',
        'POINTWISE_BASELINE',
        'POINTWISE_CANDIDATE',
    ];

    public function __construct(
        private readonly ResourceConnection $resourceConnection,
        private readonly CanonicalJson $canonicalJson,
        private readonly UuidGenerator $uuidGenerator,
        private readonly ExperimentRecordFactory $recordFactory
    ) {
    }

    public function createOrGet(
        HumanExperimentPlan $plan,
        int $storeId,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): string {
        $connection = $this->resourceConnection->getConnection();
        $table = $this->resourceConnection->getTableName(self::EXPERIMENT_TABLE);
        $existing = $connection->fetchRow(
            $connection->select()
                ->from($table, ['experiment_uuid'])
                ->where('input_sha256 = ?', $plan->getInputHash())
                ->limit(1)
        );

        if (
            is_array($existing)
            && isset($existing['experiment_uuid'])
            && is_string($existing['experiment_uuid'])
            && $existing['experiment_uuid'] !== ''
        ) {
            return $existing['experiment_uuid'];
        }

        $experimentUuid = $this->uuidGenerator->generate();
        $records = $this->recordFactory->create(
            $plan,
            $storeId,
            $experimentUuid,
            $this->uuidGenerator->generate(),
            $actorId,
            $createdAt,
            $correlationId
        );
        $connection->beginTransaction();

        try {
            $connection->insert($table, $records->getExperiment());
            $connection->insert(
                $this->resourceConnection->getTableName(self::AUDIT_TABLE),
                $records->getAuditEvent()
            );
            $connection->commit();
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }

        return $experimentUuid;
    }

    /**
     * @return array<string, string>
     */
    public function getRemoteExperimentIds(string $experimentUuid): array
    {
        $row = $this->getRow($experimentUuid);

        return $this->decodeStringMap((string)$row['remote_experiment_ids_json']);
    }

    public function bindRemoteExperimentId(
        string $experimentUuid,
        string $kind,
        string $remoteId,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): void {
        $this->assertUuid($experimentUuid);
        $this->assertUuid($remoteId);

        if (!in_array($kind, self::REMOTE_KINDS, true)) {
            throw new InvalidArgumentException('Remote experiment kind is not part of the frozen Phase 1 plan');
        }

        $this->assertActorAndCorrelation($actorId, $correlationId);
        $createdAt = $this->normalizeDate($createdAt);
        $connection = $this->resourceConnection->getConnection();
        $connection->beginTransaction();

        try {
            $row = $this->getRow($experimentUuid, true);
            $remoteIds = $this->decodeStringMap((string)$row['remote_experiment_ids_json']);

            if (isset($remoteIds[$kind]) && $remoteIds[$kind] !== strtolower($remoteId)) {
                throw new RuntimeException('Experiment kind is already bound to a different remote identity');
            }

            if (!isset($remoteIds[$kind])) {
                $remoteIds[$kind] = strtolower($remoteId);
                ksort($remoteIds, SORT_STRING);
                $connection->update(
                    $this->resourceConnection->getTableName(self::EXPERIMENT_TABLE),
                    [
                        'state' => 'REMOTE_RUNNING',
                        'remote_experiment_ids_json' => $this->canonicalJson->encode($remoteIds),
                    ],
                    ['experiment_uuid = ?' => strtolower($experimentUuid)]
                );
                $this->insertAudit(
                    $experimentUuid,
                    $actorId,
                    'REMOTE_EXPERIMENT_BOUND',
                    hash('sha256', strtolower($remoteId)),
                    'OWNED_EXPERIMENT_CREATED',
                    $correlationId,
                    $createdAt
                );
            }

            $connection->commit();
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }
    }

    /**
     * @param array<string, string> $remoteExperimentIds
     */
    public function complete(
        string $experimentUuid,
        EvidenceReport $evidence,
        array $remoteExperimentIds,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): void {
        $this->assertUuid($experimentUuid);
        $this->assertActorAndCorrelation($actorId, $correlationId);
        $this->assertCompleteRemoteIds($remoteExperimentIds);
        $createdAt = $this->normalizeDate($createdAt);
        $connection = $this->resourceConnection->getConnection();
        $connection->beginTransaction();

        try {
            $row = $this->getRow($experimentUuid, true);
            $storedIds = $this->decodeStringMap((string)$row['remote_experiment_ids_json']);

            if ($storedIds !== $remoteExperimentIds) {
                throw new RuntimeException('Completed remote experiment identities do not match the frozen run');
            }

            $aggregate = [
                'primary_metric' => $evidence->getPrimaryMetric(),
                'baseline_metric' => $evidence->getBaselineMetric(),
                'candidate_metric' => $evidence->getCandidateMetric(),
                'metric_delta' => $evidence->getMetricDelta(),
                'judged_coverage' => $evidence->getJudgedCoverage(),
            ];
            $aggregateJson = $this->canonicalJson->encode($aggregate);
            $perQueryJson = $this->canonicalJson->encode($evidence->getPerQueryEvidence());
            $accepted = (string)$row['state'] === 'ACCEPTED';

            if ($accepted) {
                if (
                    $evidence->getEligibility() !== 'EXPLORATORY'
                    || $evidence->getReasonCodes() !== ['MERCHANT_ACCEPTANCE_REQUIRED']
                    || !hash_equals((string)$row['aggregate_result_json'], $aggregateJson)
                    || !hash_equals((string)$row['per_query_result_json'], $perQueryJson)
                ) {
                    throw new RuntimeException('Accepted evidence cannot be replaced by a different rerun');
                }
            }

            $connection->update(
                $this->resourceConnection->getTableName(self::EXPERIMENT_TABLE),
                [
                    'state' => $accepted ? 'ACCEPTED' : 'LOCAL_EVIDENCE_READY',
                    'srw_validation_state' => 'VALID',
                    'index_freshness_state' => $evidence->getEligibility() === 'STALE' ? 'STALE' : 'FRESH',
                    'aggregate_result_json' => $aggregateJson,
                    'per_query_result_json' => $perQueryJson,
                    'eligibility' => $accepted ? 'WINNER' : $evidence->getEligibility(),
                    'reason_codes_json' => $accepted
                        ? $this->canonicalJson->encode([])
                        : $this->canonicalJson->encode($evidence->getReasonCodes()),
                ],
                ['experiment_uuid = ?' => strtolower($experimentUuid)]
            );
            $this->insertAudit(
                $experimentUuid,
                $actorId,
                'EXPERIMENT_EVIDENCE_RECORDED',
                hash('sha256', $this->canonicalJson->encode($aggregate)),
                'THREE_REMOTE_EXPERIMENTS_VALID',
                $correlationId,
                $createdAt
            );
            $connection->commit();
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }
    }

    public function accept(
        string $experimentUuid,
        int $actorId,
        string $acceptedAt,
        string $correlationId
    ): void {
        $this->assertUuid($experimentUuid);
        $this->assertActorAndCorrelation($actorId, $correlationId);
        $acceptedAt = $this->normalizeDate($acceptedAt);
        $connection = $this->resourceConnection->getConnection();
        $connection->beginTransaction();

        try {
            $row = $this->getRow($experimentUuid, true);
            $reasonCodes = $this->decodeStringList((string)$row['reason_codes_json']);

            if (
                (string)$row['eligibility'] !== 'EXPLORATORY'
                || $reasonCodes !== ['MERCHANT_ACCEPTANCE_REQUIRED']
                || (string)$row['srw_validation_state'] !== 'VALID'
                || (string)$row['index_freshness_state'] !== 'FRESH'
            ) {
                throw new RuntimeException('Only otherwise-winning fresh evidence may be accepted');
            }

            $connection->update(
                $this->resourceConnection->getTableName(self::EXPERIMENT_TABLE),
                [
                    'state' => 'ACCEPTED',
                    'eligibility' => 'WINNER',
                    'reason_codes_json' => $this->canonicalJson->encode([]),
                    'accepted_by' => $actorId,
                    'accepted_at' => $acceptedAt,
                ],
                ['experiment_uuid = ?' => strtolower($experimentUuid)]
            );
            $this->insertAudit(
                $experimentUuid,
                $actorId,
                'EXPERIMENT_ACCEPTED',
                (string)$row['input_sha256'],
                'MERCHANT_ACCEPTED_OFFLINE_EVIDENCE',
                $correlationId,
                $acceptedAt
            );
            $connection->commit();
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }
    }

    public function getCompleted(string $experimentUuid): PersistedExperiment
    {
        $row = $this->getRow($experimentUuid);

        if (!in_array((string)$row['state'], ['LOCAL_EVIDENCE_READY', 'ACCEPTED'], true)) {
            throw new UnexpectedValueException('Experiment has no completed local evidence');
        }

        $identities = $this->decodeScalarMap((string)$row['input_identities_json']);
        $aggregate = $this->decodeScalarMap((string)$row['aggregate_result_json']);
        $perQuery = $this->decodePerQuery((string)$row['per_query_result_json']);
        $reasonCodes = $this->decodeStringList((string)$row['reason_codes_json']);
        $primaryMetric = $aggregate['primary_metric'] ?? null;

        if (!is_string($primaryMetric)) {
            throw new UnexpectedValueException('Persisted experiment metric is invalid');
        }

        $evidence = new EvidenceReport(
            $primaryMetric,
            $this->toFloat($aggregate['baseline_metric'] ?? null),
            $this->toFloat($aggregate['candidate_metric'] ?? null),
            $this->toFloat($aggregate['metric_delta'] ?? null),
            $this->toFloat($aggregate['judged_coverage'] ?? null),
            $perQuery,
            (string)$row['eligibility'],
            $reasonCodes
        );

        return new PersistedExperiment(
            (string)$row['experiment_uuid'],
            (int)$row['store_id'],
            (string)$row['state'],
            $identities,
            (string)$row['input_sha256'],
            $this->decodeStringMap((string)$row['remote_experiment_ids_json']),
            $evidence,
            $row['accepted_by'] === null ? null : (int)$row['accepted_by'],
            $row['accepted_at'] === null ? null : (string)$row['accepted_at']
        );
    }

    /**
     * @return list<array<string, int|string|null>>
     */
    public function listRecent(int $limit = 20): array
    {
        $limit = max(1, min($limit, 100));
        $connection = $this->resourceConnection->getConnection();

        return array_values($connection->fetchAll(
            $connection->select()
                ->from(
                    $this->resourceConnection->getTableName(self::EXPERIMENT_TABLE),
                    [
                        'experiment_uuid',
                        'store_id',
                        'state',
                        'primary_metric',
                        'aggregate_result_json',
                        'eligibility',
                        'reason_codes_json',
                        'accepted_by',
                        'accepted_at',
                        'created_at',
                    ]
                )
                ->order('created_at DESC')
                ->limit($limit)
        ));
    }

    /**
     * @return array<string, mixed>
     */
    private function getRow(string $experimentUuid, bool $forUpdate = false): array
    {
        $this->assertUuid($experimentUuid);
        $connection = $this->resourceConnection->getConnection();
        $select = $connection->select()
            ->from($this->resourceConnection->getTableName(self::EXPERIMENT_TABLE))
            ->where('experiment_uuid = ?', strtolower($experimentUuid))
            ->limit(1);

        if ($forUpdate) {
            $select->forUpdate();
        }

        $row = $connection->fetchRow($select);

        if (!is_array($row)) {
            throw new UnexpectedValueException('Experiment does not exist');
        }

        return $row;
    }

    /**
     * @return array<string, string>
     */
    private function decodeStringMap(string $json): array
    {
        $decoded = json_decode($json, true, 512, JSON_THROW_ON_ERROR);

        if (!is_array($decoded)) {
            throw new UnexpectedValueException('Persisted remote experiment identities are invalid');
        }

        $result = [];

        foreach ($decoded as $key => $value) {
            if (!is_string($key) || !is_string($value)) {
                throw new UnexpectedValueException('Persisted remote experiment identity is invalid');
            }

            $result[$key] = $value;
        }

        ksort($result, SORT_STRING);

        return $result;
    }

    /**
     * @return array<string, float|int|string>
     */
    private function decodeScalarMap(string $json): array
    {
        $decoded = json_decode($json, true, 512, JSON_THROW_ON_ERROR);

        if (!is_array($decoded) || array_is_list($decoded)) {
            throw new UnexpectedValueException('Persisted experiment evidence is invalid');
        }

        $result = [];

        foreach ($decoded as $key => $value) {
            if (!is_string($key) || (!is_string($value) && !is_int($value) && !is_float($value))) {
                throw new UnexpectedValueException('Persisted experiment scalar is invalid');
            }

            $result[$key] = $value;
        }

        return $result;
    }

    /**
     * @return list<array<string, bool|float|string|int|list<string>>>
     */
    private function decodePerQuery(string $json): array
    {
        $decoded = json_decode($json, true, 512, JSON_THROW_ON_ERROR);

        if (!is_array($decoded) || !array_is_list($decoded)) {
            throw new UnexpectedValueException('Persisted per-query evidence is invalid');
        }

        $result = [];

        foreach ($decoded as $entry) {
            if (!is_array($entry) || array_is_list($entry)) {
                throw new UnexpectedValueException('Persisted per-query evidence entry is invalid');
            }

            $normalized = [];

            foreach ($entry as $key => $value) {
                if (!is_string($key)) {
                    throw new UnexpectedValueException('Persisted per-query evidence value is invalid');
                }

                if (is_string($value) || is_int($value) || is_float($value) || is_bool($value)) {
                    $normalized[$key] = $value;
                    continue;
                }

                if (!is_array($value) || !array_is_list($value)) {
                    throw new UnexpectedValueException('Persisted per-query evidence value is invalid');
                }

                foreach ($value as $item) {
                    if (!is_string($item) || $item === '') {
                        throw new UnexpectedValueException('Persisted per-query document identity is invalid');
                    }
                }

                $normalized[$key] = $value;
            }

            $result[] = $normalized;
        }

        return $result;
    }

    /**
     * @return list<string>
     */
    private function decodeStringList(string $json): array
    {
        $decoded = json_decode($json, true, 512, JSON_THROW_ON_ERROR);

        if (!is_array($decoded) || !array_is_list($decoded)) {
            throw new UnexpectedValueException('Persisted experiment reason codes are invalid');
        }

        $result = [];

        foreach ($decoded as $value) {
            if (!is_string($value)) {
                throw new UnexpectedValueException('Persisted experiment reason code is invalid');
            }

            $result[] = $value;
        }

        return $result;
    }

    /**
     * @param array<string, string> $remoteIds
     */
    private function assertCompleteRemoteIds(array &$remoteIds): void
    {
        ksort($remoteIds, SORT_STRING);
        $expected = self::REMOTE_KINDS;
        sort($expected, SORT_STRING);

        if (array_keys($remoteIds) !== $expected) {
            throw new InvalidArgumentException('Completed run must contain the exact three Phase 1 experiments');
        }

        foreach ($remoteIds as $remoteId) {
            $this->assertUuid($remoteId);
        }
    }

    private function insertAudit(
        string $experimentUuid,
        int $actorId,
        string $action,
        string $afterHash,
        string $reasonCode,
        string $correlationId,
        string $createdAt
    ): void {
        $this->resourceConnection->getConnection()->insert(
            $this->resourceConnection->getTableName(self::AUDIT_TABLE),
            [
                'event_uuid' => $this->uuidGenerator->generate(),
                'actor_type' => 'ADMIN',
                'actor_id' => (string)$actorId,
                'action' => $action,
                'target_type' => 'EXPERIMENT',
                'target_uuid' => strtolower($experimentUuid),
                'before_identity_sha256' => null,
                'after_identity_sha256' => $afterHash,
                'result' => 'SUCCESS',
                'reason_code' => $reasonCode,
                'correlation_id' => $correlationId,
                'created_at' => $createdAt,
            ]
        );
    }

    private function assertActorAndCorrelation(int $actorId, string $correlationId): void
    {
        if ($actorId < 1 || $correlationId === '' || strlen($correlationId) > 64) {
            throw new InvalidArgumentException('Experiment mutation requires an admin actor and correlation ID');
        }
    }

    private function normalizeDate(string $date): string
    {
        return (new DateTimeImmutable($date))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d H:i:s');
    }

    private function toFloat(mixed $value): float
    {
        if (!is_int($value) && !is_float($value)) {
            throw new UnexpectedValueException('Persisted experiment metric value is invalid');
        }

        return (float)$value;
    }

    private function assertUuid(string $uuid): void
    {
        if (preg_match(self::UUID_PATTERN, $uuid) !== 1) {
            throw new InvalidArgumentException('Experiment identity must be a UUID');
        }
    }
}
