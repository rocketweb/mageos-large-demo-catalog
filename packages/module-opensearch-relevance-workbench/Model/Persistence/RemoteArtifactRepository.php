<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

use DateTimeImmutable;
use DateTimeZone;
use InvalidArgumentException;
use Magento\Framework\App\ResourceConnection;
use RuntimeException;
use Throwable;
use UnexpectedValueException;

class RemoteArtifactRepository
{
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/iD';
    private const AUDIT_TABLE = 'osrw_audit_event';

    public function __construct(
        private readonly ResourceConnection $resourceConnection,
        private readonly UuidGenerator $uuidGenerator
    ) {
    }

    public function getQuerySetId(string $snapshotUuid): ?string
    {
        return $this->getBinding('osrw_query_snapshot', 'snapshot_uuid', $snapshotUuid, 'remote_query_set_id');
    }

    public function bindQuerySetId(
        string $snapshotUuid,
        string $remoteId,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): void {
        $this->bind(
            'osrw_query_snapshot',
            'snapshot_uuid',
            $snapshotUuid,
            'remote_query_set_id',
            $remoteId,
            'QUERY_SET',
            $actorId,
            $createdAt,
            $correlationId
        );
    }

    public function getSearchConfigurationId(string $configurationUuid): ?string
    {
        return $this->getBinding(
            'osrw_search_configuration',
            'configuration_uuid',
            $configurationUuid,
            'remote_configuration_id'
        );
    }

    public function bindSearchConfigurationId(
        string $configurationUuid,
        string $remoteId,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): void {
        $this->bind(
            'osrw_search_configuration',
            'configuration_uuid',
            $configurationUuid,
            'remote_configuration_id',
            $remoteId,
            'SEARCH_CONFIGURATION',
            $actorId,
            $createdAt,
            $correlationId
        );
    }

    public function getJudgmentId(string $judgmentUuid): ?string
    {
        $effective = $this->getBinding(
            'osrw_judgment_run',
            'judgment_uuid',
            $judgmentUuid,
            'effective_imported_judgment_id'
        );

        return $effective ?? $this->getBinding(
            'osrw_judgment_run',
            'judgment_uuid',
            $judgmentUuid,
            'remote_judgment_id'
        );
    }

    public function bindJudgmentId(
        string $judgmentUuid,
        string $remoteId,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): void {
        $this->bind(
            'osrw_judgment_run',
            'judgment_uuid',
            $judgmentUuid,
            'remote_judgment_id',
            $remoteId,
            'JUDGMENT',
            $actorId,
            $createdAt,
            $correlationId
        );
    }

    public function markJudgmentCompleted(string $judgmentUuid, string $remoteId): void
    {
        $this->assertUuid($judgmentUuid);
        $this->assertUuid($remoteId);
        $connection = $this->resourceConnection->getConnection();
        $affected = $connection->update(
            $this->resourceConnection->getTableName('osrw_judgment_run'),
            [
                'state' => 'REMOTE_COMPLETED',
                'effective_imported_judgment_id' => strtolower($remoteId),
            ],
            [
                'judgment_uuid = ?' => strtolower($judgmentUuid),
                'remote_judgment_id = ?' => strtolower($remoteId),
            ]
        );

        if ($affected !== 1 && $this->getJudgmentId($judgmentUuid) !== strtolower($remoteId)) {
            throw new RuntimeException('Remote judgment completion could not be persisted');
        }
    }

    /**
     * @return list<array{
     *     local_uuid: string,
     *     remote_id: string,
     *     resource_type: string,
     *     resource_kind: string
     * }>
     */
    public function listBoundResources(int $limit = 20): array
    {
        $limit = max(1, min($limit, 100));
        $connection = $this->resourceConnection->getConnection();
        $bindings = [];

        foreach ($connection->fetchAll(
            $connection->select()
                ->from(
                    $this->resourceConnection->getTableName('osrw_query_snapshot'),
                    ['snapshot_uuid', 'remote_query_set_id']
                )
                ->where('remote_query_set_id IS NOT NULL')
                ->limit($limit)
        ) as $row) {
            $bindings[] = $this->bindingRow(
                (string)$row['snapshot_uuid'],
                (string)$row['remote_query_set_id'],
                'QUERY_SET',
                'query-set'
            );
        }

        foreach ($connection->fetchAll(
            $connection->select()
                ->from(
                    $this->resourceConnection->getTableName('osrw_search_configuration'),
                    ['configuration_uuid', 'kind', 'remote_configuration_id']
                )
                ->where('remote_configuration_id IS NOT NULL')
                ->limit($limit)
        ) as $row) {
            $bindings[] = $this->bindingRow(
                (string)$row['configuration_uuid'],
                (string)$row['remote_configuration_id'],
                'SEARCH_CONFIGURATION',
                strtolower((string)$row['kind'])
            );
        }

        foreach ($connection->fetchAll(
            $connection->select()
                ->from(
                    $this->resourceConnection->getTableName('osrw_judgment_run'),
                    ['judgment_uuid', 'remote_judgment_id', 'effective_imported_judgment_id']
                )
                ->where('remote_judgment_id IS NOT NULL')
                ->limit($limit)
        ) as $row) {
            $remoteId = $row['effective_imported_judgment_id'] ?? $row['remote_judgment_id'];
            $bindings[] = $this->bindingRow(
                (string)$row['judgment_uuid'],
                (string)$remoteId,
                'JUDGMENT',
                'human'
            );
        }

        foreach ($connection->fetchAll(
            $connection->select()
                ->from(
                    $this->resourceConnection->getTableName('osrw_experiment'),
                    ['experiment_uuid', 'remote_experiment_ids_json']
                )
                ->where('remote_experiment_ids_json != ?', '{}')
                ->limit($limit)
        ) as $row) {
            $remoteIds = json_decode((string)$row['remote_experiment_ids_json'], true, 512, JSON_THROW_ON_ERROR);

            if (!is_array($remoteIds)) {
                throw new UnexpectedValueException('Persisted remote experiment bindings are invalid');
            }

            foreach ($remoteIds as $kind => $remoteId) {
                if (!is_string($kind) || !is_string($remoteId)) {
                    throw new UnexpectedValueException('Persisted remote experiment binding is invalid');
                }

                $bindings[] = $this->bindingRow(
                    (string)$row['experiment_uuid'],
                    $remoteId,
                    'EXPERIMENT',
                    $kind
                );
            }
        }

        usort(
            $bindings,
            static fn (array $left, array $right): int => [
                $left['resource_type'],
                $left['local_uuid'],
                $left['resource_kind'],
            ] <=> [
                $right['resource_type'],
                $right['local_uuid'],
                $right['resource_kind'],
            ]
        );

        return array_slice($bindings, 0, $limit);
    }

    private function getBinding(
        string $table,
        string $identityColumn,
        string $localUuid,
        string $remoteColumn
    ): ?string {
        $this->assertUuid($localUuid);
        $connection = $this->resourceConnection->getConnection();
        $row = $connection->fetchRow(
            $connection->select()
                ->from(
                    $this->resourceConnection->getTableName($table),
                    [$identityColumn, $remoteColumn]
                )
                ->where($identityColumn . ' = ?', strtolower($localUuid))
                ->limit(1)
        );

        if (!is_array($row)) {
            throw new UnexpectedValueException('Local artifact for remote binding does not exist');
        }

        $value = $row[$remoteColumn] ?? null;

        if ($value === null || $value === '') {
            return null;
        }

        if (!is_string($value) || preg_match(self::UUID_PATTERN, $value) !== 1) {
            throw new UnexpectedValueException('Persisted remote artifact identity is invalid');
        }

        return strtolower($value);
    }

    /**
     * @return array{local_uuid: string, remote_id: string, resource_type: string, resource_kind: string}
     */
    private function bindingRow(
        string $localUuid,
        string $remoteId,
        string $resourceType,
        string $resourceKind
    ): array {
        $this->assertUuid($localUuid);
        $this->assertUuid($remoteId);

        if ($resourceType === '' || $resourceKind === '') {
            throw new UnexpectedValueException('Remote binding type and kind must not be empty');
        }

        return [
            'local_uuid' => strtolower($localUuid),
            'remote_id' => strtolower($remoteId),
            'resource_type' => $resourceType,
            'resource_kind' => $resourceKind,
        ];
    }

    private function bind(
        string $table,
        string $identityColumn,
        string $localUuid,
        string $remoteColumn,
        string $remoteId,
        string $targetType,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): void {
        $this->assertUuid($localUuid);
        $this->assertUuid($remoteId);

        if ($actorId < 1 || $correlationId === '' || strlen($correlationId) > 64) {
            throw new InvalidArgumentException('Remote artifact binding requires an admin actor and correlation ID');
        }

        $current = $this->getBinding($table, $identityColumn, $localUuid, $remoteColumn);

        if ($current !== null) {
            if ($current !== strtolower($remoteId)) {
                throw new RuntimeException('Local artifact is already bound to a different remote identity');
            }

            return;
        }

        $createdAt = (new DateTimeImmutable($createdAt))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d H:i:s');
        $connection = $this->resourceConnection->getConnection();
        $connection->beginTransaction();

        try {
            $affected = $connection->update(
                $this->resourceConnection->getTableName($table),
                [$remoteColumn => strtolower($remoteId)],
                [
                    $identityColumn . ' = ?' => strtolower($localUuid),
                    $remoteColumn . ' IS NULL' => null,
                ]
            );

            if ($affected !== 1) {
                throw new RuntimeException('Remote artifact binding target was missing or concurrently changed');
            }

            $connection->insert(
                $this->resourceConnection->getTableName(self::AUDIT_TABLE),
                [
                    'event_uuid' => $this->uuidGenerator->generate(),
                    'actor_type' => 'ADMIN',
                    'actor_id' => (string)$actorId,
                    'action' => 'REMOTE_RESOURCE_BOUND',
                    'target_type' => $targetType,
                    'target_uuid' => strtolower($localUuid),
                    'before_identity_sha256' => null,
                    'after_identity_sha256' => hash('sha256', strtolower($remoteId)),
                    'result' => 'SUCCESS',
                    'reason_code' => 'OWNED_RESOURCE_CREATED',
                    'correlation_id' => $correlationId,
                    'created_at' => $createdAt,
                ]
            );
            $connection->commit();
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }
    }

    private function assertUuid(string $uuid): void
    {
        if (preg_match(self::UUID_PATTERN, $uuid) !== 1) {
            throw new InvalidArgumentException('Remote artifact identities must be UUIDs');
        }
    }
}
