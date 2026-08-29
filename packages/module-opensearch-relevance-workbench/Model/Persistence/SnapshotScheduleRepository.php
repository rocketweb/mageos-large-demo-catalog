<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

use DateTimeImmutable;
use DateTimeZone;
use InvalidArgumentException;
use Magento\Framework\App\ResourceConnection;
use MageOS\OpenSearchRelevanceWorkbench\Model\Schedule\ApprovedSnapshotSchedule;
use MageOS\OpenSearchRelevanceWorkbench\Model\Schedule\SnapshotSchedulePolicy;
use MageOS\OpenSearchRelevanceWorkbench\Model\Schedule\SnapshotSchedulePolicyFactory;
use RuntimeException;
use Throwable;
use UnexpectedValueException;

class SnapshotScheduleRepository
{
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/iD';
    private const TABLE = 'osrw_snapshot_schedule';
    private const AUDIT_TABLE = 'osrw_audit_event';

    public function __construct(
        private readonly ResourceConnection $resourceConnection,
        private readonly UuidGenerator $uuidGenerator,
        private readonly SnapshotSchedulePolicyFactory $policyFactory
    ) {
    }

    public function approve(
        SnapshotSchedulePolicy $policy,
        int $actorId,
        string $approvedAt,
        string $correlationId
    ): string {
        $this->assertActorAndCorrelation($actorId, $correlationId);
        $approvedAt = $this->normalizeDate($approvedAt);
        $connection = $this->resourceConnection->getConnection();
        $table = $this->resourceConnection->getTableName(self::TABLE);
        $connection->beginTransaction();

        try {
            $existing = $connection->fetchRow(
                $connection->select()
                    ->from($table)
                    ->where('store_id = ?', $policy->getStoreId())
                    ->limit(1)
                    ->forUpdate()
            );
            $scheduleUuid = is_array($existing)
                ? (string)$existing['schedule_uuid']
                : $this->uuidGenerator->generate();
            $record = $this->record($policy, $actorId, $approvedAt);

            if (is_array($existing)) {
                $connection->update($table, $record, ['schedule_uuid = ?' => $scheduleUuid]);
            } else {
                $connection->insert($table, ['schedule_uuid' => $scheduleUuid] + $record);
            }

            $this->insertAudit(
                $scheduleUuid,
                'ADMIN',
                (string)$actorId,
                'SNAPSHOT_SCHEDULE_APPROVED',
                is_array($existing) ? (string)$existing['policy_sha256'] : null,
                $policy->getPolicyHash(),
                'BOUNDED_DRAFT_ONLY_SCHEDULE',
                $correlationId,
                $approvedAt
            );
            $connection->commit();

            return $scheduleUuid;
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }
    }

    public function pause(
        string $scheduleUuid,
        int $actorId,
        string $pausedAt,
        string $correlationId
    ): void {
        $this->assertUuid($scheduleUuid);
        $this->assertActorAndCorrelation($actorId, $correlationId);
        $pausedAt = $this->normalizeDate($pausedAt);
        $connection = $this->resourceConnection->getConnection();
        $connection->beginTransaction();

        try {
            $row = $this->getRow($scheduleUuid, true);

            if ((string)$row['status'] !== 'PAUSED') {
                $connection->update(
                    $this->resourceConnection->getTableName(self::TABLE),
                    ['status' => 'PAUSED'],
                    ['schedule_uuid = ?' => strtolower($scheduleUuid)]
                );
                $this->insertAudit(
                    strtolower($scheduleUuid),
                    'ADMIN',
                    (string)$actorId,
                    'SNAPSHOT_SCHEDULE_PAUSED',
                    (string)$row['policy_sha256'],
                    (string)$row['policy_sha256'],
                    'MERCHANT_PAUSED_SCHEDULE',
                    $correlationId,
                    $pausedAt
                );
            }

            $connection->commit();
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }
    }

    /**
     * @return list<ApprovedSnapshotSchedule>
     */
    public function listDue(string $now, int $limit = 10): array
    {
        $now = $this->normalizeDate($now);
        $limit = max(1, min($limit, 100));
        $connection = $this->resourceConnection->getConnection();
        $rows = $connection->fetchAll(
            $connection->select()
                ->from($this->resourceConnection->getTableName(self::TABLE))
                ->where('status = ?', 'ACTIVE')
                ->where('next_run_at <= ?', $now)
                ->order('next_run_at ASC')
                ->limit($limit)
        );

        return array_values(array_map(
            fn (array $row): ApprovedSnapshotSchedule => new ApprovedSnapshotSchedule(
                (string)$row['schedule_uuid'],
                $this->policyFactory->rehydrate($row)
            ),
            $rows
        ));
    }

    public function markPrepared(
        ApprovedSnapshotSchedule $schedule,
        string $preparedAt,
        string $correlationId
    ): void {
        $preparedAt = $this->normalizeDate($preparedAt);
        $policy = $schedule->getPolicy();
        $connection = $this->resourceConnection->getConnection();
        $connection->beginTransaction();

        try {
            $affected = $connection->update(
                $this->resourceConnection->getTableName(self::TABLE),
                [
                    'last_prepared_at' => $preparedAt,
                    'next_run_at' => $this->normalizeDate($policy->getFollowingRunAt()),
                ],
                [
                    'schedule_uuid = ?' => strtolower($schedule->getScheduleUuid()),
                    'status = ?' => 'ACTIVE',
                    'next_run_at = ?' => $this->normalizeDate($policy->getNextRunAt()),
                ]
            );

            if ($affected !== 1) {
                throw new RuntimeException('Snapshot schedule changed before its draft could be recorded');
            }

            $this->insertAudit(
                strtolower($schedule->getScheduleUuid()),
                'SYSTEM',
                'CRON',
                'SNAPSHOT_SCHEDULE_ADVANCED',
                $policy->getPolicyHash(),
                $policy->getPolicyHash(),
                'DRAFT_PREPARED_WITHOUT_APPROVAL',
                $correlationId,
                $preparedAt
            );
            $connection->commit();
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }
    }

    /**
     * @return list<array<string, int|string|null>>
     */
    public function listRecent(int $limit = 20): array
    {
        $limit = max(1, min($limit, 100));

        return array_values($this->resourceConnection->getConnection()->fetchAll(
            $this->resourceConnection->getConnection()->select()
                ->from($this->resourceConnection->getTableName(self::TABLE))
                ->order('updated_at DESC')
                ->limit($limit)
        ));
    }

    /**
     * @return array<string, int|string|null>
     */
    private function record(SnapshotSchedulePolicy $policy, int $actorId, string $approvedAt): array
    {
        return [
            'store_id' => $policy->getStoreId(),
            'status' => 'ACTIVE',
            'source_window_days' => $policy->getSourceWindowDays(),
            'minimum_popularity' => $policy->getMinimumPopularity(),
            'positive_result_limit' => $policy->getPositiveResultLimit(),
            'zero_result_limit' => $policy->getZeroResultLimit(),
            'maximum_snapshot_size' => $policy->getMaximumSnapshotSize(),
            'include_redirects' => $policy->includesRedirects() ? 1 : 0,
            'interval_days' => $policy->getIntervalDays(),
            'retention_days' => $policy->getRetentionDays(),
            'schedule_anchor_at' => $this->normalizeDate($policy->getScheduleAnchorAt()),
            'next_run_at' => $this->normalizeDate($policy->getNextRunAt()),
            'last_prepared_at' => null,
            'policy_sha256' => $policy->getPolicyHash(),
            'approved_by' => $actorId,
            'approved_at' => $approvedAt,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function getRow(string $scheduleUuid, bool $forUpdate = false): array
    {
        $select = $this->resourceConnection->getConnection()->select()
            ->from($this->resourceConnection->getTableName(self::TABLE))
            ->where('schedule_uuid = ?', strtolower($scheduleUuid))
            ->limit(1);

        if ($forUpdate) {
            $select->forUpdate();
        }

        $row = $this->resourceConnection->getConnection()->fetchRow($select);

        if (!is_array($row)) {
            throw new UnexpectedValueException('Snapshot schedule does not exist');
        }

        return $row;
    }

    private function insertAudit(
        string $scheduleUuid,
        string $actorType,
        string $actorId,
        string $action,
        ?string $beforeHash,
        string $afterHash,
        string $reasonCode,
        string $correlationId,
        string $createdAt
    ): void {
        $this->resourceConnection->getConnection()->insert(
            $this->resourceConnection->getTableName(self::AUDIT_TABLE),
            [
                'event_uuid' => $this->uuidGenerator->generate(),
                'actor_type' => $actorType,
                'actor_id' => $actorId,
                'action' => $action,
                'target_type' => 'SNAPSHOT_SCHEDULE',
                'target_uuid' => strtolower($scheduleUuid),
                'before_identity_sha256' => $beforeHash,
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
            throw new InvalidArgumentException('Snapshot schedule requires an admin actor and correlation ID');
        }
    }

    private function assertUuid(string $uuid): void
    {
        if (preg_match(self::UUID_PATTERN, $uuid) !== 1) {
            throw new InvalidArgumentException('Snapshot schedule identity must be a UUID');
        }
    }

    private function normalizeDate(string $value): string
    {
        return (new DateTimeImmutable($value, new DateTimeZone('UTC')))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d H:i:s');
    }
}
