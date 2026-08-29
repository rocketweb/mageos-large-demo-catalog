<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

use DateTimeImmutable;
use DateTimeZone;
use InvalidArgumentException;
use Magento\Framework\App\ResourceConnection;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\QuerySnapshotEntry;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPolicy;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\ApprovedQuerySnapshot;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\QuerySnapshotPreview;
use Throwable;
use UnexpectedValueException;

class QuerySnapshotRepository
{
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/iD';
    private const SNAPSHOT_TABLE = 'osrw_query_snapshot';
    private const ENTRY_TABLE = 'osrw_query_snapshot_entry';
    private const AUDIT_TABLE = 'osrw_audit_event';

    public function __construct(
        private readonly ResourceConnection $resourceConnection,
        private readonly SnapshotRecordFactory $recordFactory,
        private readonly UuidGenerator $uuidGenerator
    ) {
    }

    public function saveApproved(
        QuerySnapshotPreview $preview,
        ApprovedQuerySnapshot $approved,
        string $correlationId
    ): string {
        $connection = $this->resourceConnection->getConnection();
        $snapshotTable = $this->resourceConnection->getTableName(self::SNAPSHOT_TABLE);
        $select = $connection->select()
            ->from($snapshotTable, ['snapshot_uuid'])
            ->where('store_id = ?', $approved->getStoreId())
            ->where('canonical_sha256 = ?', $approved->getSnapshotHash())
            ->limit(1);
        $existingSnapshot = $connection->fetchRow($select);

        if (
            is_array($existingSnapshot)
            && isset($existingSnapshot['snapshot_uuid'])
            && is_string($existingSnapshot['snapshot_uuid'])
            && $existingSnapshot['snapshot_uuid'] !== ''
        ) {
            return $existingSnapshot['snapshot_uuid'];
        }

        $snapshotUuid = $this->uuidGenerator->generate();
        $entryUuids = array_map(
            fn (): string => $this->uuidGenerator->generate(),
            $approved->getEntries()
        );
        $records = $this->recordFactory->create(
            $preview,
            $approved,
            $snapshotUuid,
            $entryUuids,
            $this->uuidGenerator->generate(),
            $correlationId
        );
        $connection->beginTransaction();

        try {
            $connection->insert($snapshotTable, $records->getSnapshot());

            if ($records->getEntries() !== []) {
                $connection->insertMultiple(
                    $this->resourceConnection->getTableName(self::ENTRY_TABLE),
                    $records->getEntries()
                );
            }

            $connection->insert(
                $this->resourceConnection->getTableName(self::AUDIT_TABLE),
                $records->getAuditEvent()
            );
            $connection->commit();
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }

        return $snapshotUuid;
    }

    public function saveDraft(
        QuerySnapshotPreview $preview,
        string $scheduleUuid,
        string $preparedAt,
        string $correlationId
    ): string {
        $this->assertUuid($scheduleUuid);
        $connection = $this->resourceConnection->getConnection();
        $snapshotTable = $this->resourceConnection->getTableName(self::SNAPSHOT_TABLE);
        $existing = $connection->fetchRow(
            $connection->select()
                ->from($snapshotTable, ['snapshot_uuid'])
                ->where('store_id = ?', $preview->getStoreId())
                ->where('canonical_sha256 = ?', $preview->getSnapshotHash())
                ->limit(1)
        );

        if (is_array($existing) && is_string($existing['snapshot_uuid'] ?? null)) {
            return (string)$existing['snapshot_uuid'];
        }

        $snapshotUuid = $this->uuidGenerator->generate();
        $entryUuids = array_map(
            fn (): string => $this->uuidGenerator->generate(),
            $preview->getEntries()
        );
        $records = $this->recordFactory->createDraft(
            $preview,
            $scheduleUuid,
            $snapshotUuid,
            $entryUuids,
            $this->uuidGenerator->generate(),
            $preparedAt,
            $correlationId
        );
        $connection->beginTransaction();

        try {
            $connection->insert($snapshotTable, $records->getSnapshot());

            if ($records->getEntries() !== []) {
                $connection->insertMultiple(
                    $this->resourceConnection->getTableName(self::ENTRY_TABLE),
                    $records->getEntries()
                );
            }

            $connection->insert(
                $this->resourceConnection->getTableName(self::AUDIT_TABLE),
                $records->getAuditEvent()
            );
            $connection->commit();
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }

        return $snapshotUuid;
    }

    public function approveDraft(
        string $snapshotUuid,
        string $expectedHash,
        int $actorId,
        string $approvedAt,
        string $correlationId
    ): void {
        $this->assertUuid($snapshotUuid);

        if (
            preg_match('/\A[0-9a-f]{64}\z/', $expectedHash) !== 1
            || $actorId < 1
            || $correlationId === ''
            || strlen($correlationId) > 64
        ) {
            throw new InvalidArgumentException('Draft approval requires exact identities and an admin actor');
        }

        $approvedAt = (new DateTimeImmutable($approvedAt))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d H:i:s');
        $connection = $this->resourceConnection->getConnection();
        $connection->beginTransaction();

        try {
            $row = $connection->fetchRow(
                $connection->select()
                    ->from($this->resourceConnection->getTableName(self::SNAPSHOT_TABLE))
                    ->where('snapshot_uuid = ?', strtolower($snapshotUuid))
                    ->limit(1)
                    ->forUpdate()
            );

            if (
                !is_array($row)
                || (string)$row['status'] !== 'DRAFT'
                || !hash_equals((string)$row['canonical_sha256'], $expectedHash)
            ) {
                throw new UnexpectedValueException('Only the exact scheduled draft may be approved');
            }

            $connection->update(
                $this->resourceConnection->getTableName(self::SNAPSHOT_TABLE),
                [
                    'status' => 'APPROVED',
                    'approved_by' => $actorId,
                    'approved_at' => $approvedAt,
                ],
                ['snapshot_uuid = ?' => strtolower($snapshotUuid)]
            );
            $connection->insert(
                $this->resourceConnection->getTableName(self::AUDIT_TABLE),
                [
                    'event_uuid' => $this->uuidGenerator->generate(),
                    'actor_type' => 'ADMIN',
                    'actor_id' => (string)$actorId,
                    'action' => 'SCHEDULED_SNAPSHOT_APPROVED',
                    'target_type' => 'QUERY_SNAPSHOT',
                    'target_uuid' => strtolower($snapshotUuid),
                    'before_identity_sha256' => $expectedHash,
                    'after_identity_sha256' => $expectedHash,
                    'result' => 'SUCCESS',
                    'reason_code' => 'EXACT_DRAFT_HASH_APPROVED',
                    'correlation_id' => $correlationId,
                    'created_at' => $approvedAt,
                ]
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
        $connection = $this->resourceConnection->getConnection();
        $select = $connection->select()
            ->from(
                $this->resourceConnection->getTableName(self::SNAPSHOT_TABLE),
                [
                    'snapshot_uuid',
                    'schedule_uuid',
                    'store_id',
                    'status',
                    'selected_count',
                    'excluded_count',
                    'canonical_sha256',
                    'approved_by',
                    'approved_at',
                    'created_at',
                ]
            )
            ->order('created_at DESC')
            ->limit($limit);

        return array_values($connection->fetchAll($select));
    }

    /**
     * @return list<array{query_text: string, popularity: int, result_count: int}>
     */
    public function getDraftReviewEntries(string $snapshotUuid): array
    {
        $this->assertUuid($snapshotUuid);
        $connection = $this->resourceConnection->getConnection();
        $snapshot = $connection->fetchRow(
            $connection->select()
                ->from($this->resourceConnection->getTableName(self::SNAPSHOT_TABLE), ['status'])
                ->where('snapshot_uuid = ?', strtolower($snapshotUuid))
                ->limit(1)
        );

        if (!is_array($snapshot) || (string)$snapshot['status'] !== 'DRAFT') {
            return [];
        }

        return array_values(array_map(
            static fn (array $row): array => [
                'query_text' => (string)$row['query_text'],
                'popularity' => (int)$row['popularity'],
                'result_count' => (int)$row['result_count'],
            ],
            $connection->fetchAll(
                $connection->select()
                    ->from(
                        $this->resourceConnection->getTableName(self::ENTRY_TABLE),
                        ['query_text', 'popularity', 'result_count']
                    )
                    ->where('snapshot_uuid = ?', strtolower($snapshotUuid))
                    ->where('is_excluded = ?', 0)
                    ->order('ordinal ASC')
            )
        ));
    }

    public function getApproved(string $snapshotUuid): ApprovedQuerySnapshot
    {
        $connection = $this->resourceConnection->getConnection();
        $snapshotRow = $connection->fetchRow(
            $connection->select()
                ->from($this->resourceConnection->getTableName(self::SNAPSHOT_TABLE))
                ->where('snapshot_uuid = ?', $snapshotUuid)
                ->where('status = ?', 'APPROVED')
                ->limit(1)
        );

        if (!is_array($snapshotRow)) {
            throw new UnexpectedValueException('Approved query snapshot does not exist');
        }

        $entryRows = $connection->fetchAll(
            $connection->select()
                ->from($this->resourceConnection->getTableName(self::ENTRY_TABLE))
                ->where('snapshot_uuid = ?', $snapshotUuid)
                ->where('is_excluded = ?', 0)
                ->order('ordinal ASC')
        );
        $sourceWindow = $this->decodeObject((string)$snapshotRow['source_window_json']);
        $samplingPolicy = $this->decodeObject((string)$snapshotRow['sampling_policy_json']);
        $privacyPolicy = $this->decodeObject((string)$snapshotRow['privacy_policy_json']);
        $boundary = $sourceWindow['high_water_boundary'] ?? null;

        if (!is_array($boundary)) {
            throw new UnexpectedValueException('Approved query snapshot has no high-water boundary');
        }

        $entries = array_map(
            fn (array $row): QuerySnapshotEntry => new QuerySnapshotEntry(
                (int)$row['source_query_id'],
                (string)$row['query_text'],
                (string)$row['query_hash'],
                (int)$row['popularity'],
                (int)$row['result_count'],
                (string)$row['source_updated_at'],
                $this->decodeCustomFields($row['custom_fields_json'] ?? null)
            ),
            array_values($entryRows)
        );
        $policy = new SnapshotPolicy(
            (int)($samplingPolicy['minimum_popularity'] ?? -1),
            (int)($samplingPolicy['positive_result_limit'] ?? 0),
            (int)($samplingPolicy['zero_result_limit'] ?? 0),
            (int)($samplingPolicy['total_limit'] ?? 0),
            (bool)($samplingPolicy['include_redirects'] ?? false),
            (int)($privacyPolicy['maximum_term_length'] ?? 0),
            (string)($privacyPolicy['version'] ?? ''),
            isset($sourceWindow['start']) ? (string)$sourceWindow['start'] : null,
            isset($sourceWindow['end']) ? (string)$sourceWindow['end'] : null
        );

        return new ApprovedQuerySnapshot(
            (int)$snapshotRow['store_id'],
            $entries,
            $policy,
            [
                'updated_at' => (string)($boundary['updated_at'] ?? ''),
                'query_id' => (int)($boundary['query_id'] ?? 0),
            ],
            (string)$snapshotRow['canonical_sha256'],
            (int)$snapshotRow['approved_by'],
            (string)$snapshotRow['approved_at']
        );
    }

    private function assertUuid(string $uuid): void
    {
        if (preg_match(self::UUID_PATTERN, $uuid) !== 1) {
            throw new InvalidArgumentException('Snapshot identity must be a UUID');
        }
    }

    /**
     * @return array<string, mixed>
     */
    private function decodeObject(string $json): array
    {
        $decoded = json_decode($json, true, 512, JSON_THROW_ON_ERROR);

        if (!is_array($decoded) || array_is_list($decoded)) {
            throw new UnexpectedValueException('Approved query snapshot metadata is invalid');
        }

        return $decoded;
    }

    /**
     * @return array<string, array{value: string, provenance: string}>
     */
    private function decodeCustomFields(mixed $json): array
    {
        if ($json === null || $json === '') {
            return [];
        }

        if (!is_string($json)) {
            throw new UnexpectedValueException('Approved query custom fields are invalid');
        }

        $decoded = $this->decodeObject($json);
        $customFields = [];

        foreach ($decoded as $field => $metadata) {
            if (
                !in_array($field, ['brand_value', 'category_id'], true)
                || !is_array($metadata)
                || !is_string($metadata['value'] ?? null)
                || !is_string($metadata['provenance'] ?? null)
            ) {
                throw new UnexpectedValueException('Approved query custom-field provenance is invalid');
            }

            $customFields[$field] = [
                'value' => $metadata['value'],
                'provenance' => $metadata['provenance'],
            ];
        }

        return $customFields;
    }
}
