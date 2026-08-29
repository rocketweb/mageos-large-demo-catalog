<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

use DateTimeImmutable;
use DateTimeZone;
use InvalidArgumentException;
use Magento\Framework\App\ResourceConnection;
use MageOS\OpenSearchRelevanceWorkbench\Model\Activation\LiveActivation;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use Throwable;
use UnexpectedValueException;

class LiveActivationRepository
{
    private const ACTIVATION_TABLE = 'osrw_live_activation';
    private const STATE_TABLE = 'osrw_live_state';
    private const AUDIT_TABLE = 'osrw_audit_event';
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/iD';
    private const HASH_PATTERN = '/\A[0-9a-f]{64}\z/iD';

    public function __construct(
        private readonly ResourceConnection $resourceConnection,
        private readonly CanonicalJson $canonicalJson,
        private readonly UuidGenerator $uuidGenerator
    ) {
    }

    /**
     * @param array<string, mixed> $transformation
     */
    public function activate(
        int $storeId,
        string $sourceExperimentUuid,
        string $candidateUuid,
        array $transformation,
        string $candidateHash,
        string $indexEvidenceHash,
        string $targetAlias,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): string {
        $this->assertCommon($storeId, $actorId, $indexEvidenceHash, $targetAlias, $createdAt, $correlationId);
        $this->assertUuid($sourceExperimentUuid);
        $this->assertUuid($candidateUuid);
        $this->assertHash($candidateHash);
        $this->assertTransformation($transformation);

        return $this->writeEvent(
            $storeId,
            'APPLY',
            strtolower($candidateUuid),
            strtolower($sourceExperimentUuid),
            $transformation,
            strtolower($candidateHash),
            strtolower($indexEvidenceHash),
            $targetAlias,
            $actorId,
            $createdAt,
            $correlationId
        );
    }

    public function rollback(
        int $storeId,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): string {
        if ($storeId < 1 || $actorId < 1) {
            throw new InvalidArgumentException('Rollback requires a store and an authenticated admin');
        }

        $connection = $this->resourceConnection->getConnection();
        $connection->beginTransaction();

        try {
            $current = $this->getCurrentRow($storeId, true);

            if ($current === null) {
                throw new UnexpectedValueException('Storefront search already uses the stock configuration');
            }

            $target = null;
            $previousUuid = $current['previous_activation_uuid'] ?? null;

            if (is_string($previousUuid) && $previousUuid !== '') {
                $target = $this->getRow($previousUuid);
            }

            $createdAt = $this->normalizeDate($createdAt);
            $this->assertCorrelation($correlationId);
            $activationUuid = $this->uuidGenerator->generate();
            $transformation = $target === null
                ? ['type' => 'STOCK']
                : $this->decodeTransformation((string)$target['transformation_json']);
            $record = $this->eventRecord(
                $activationUuid,
                $storeId,
                'ROLLBACK',
                $target === null ? null : $this->nullableString($target['candidate_uuid'] ?? null),
                $target === null ? null : $this->nullableString($target['source_experiment_uuid'] ?? null),
                (string)$current['activation_uuid'],
                $transformation,
                $target === null ? null : $this->nullableString($target['candidate_sha256'] ?? null),
                $target === null
                    ? (string)$current['index_evidence_sha256']
                    : (string)$target['index_evidence_sha256'],
                $target === null ? (string)$current['target_alias'] : (string)$target['target_alias'],
                $actorId,
                $createdAt
            );
            $connection->insert($this->table(self::ACTIVATION_TABLE), $record);
            $this->persistState($storeId, $activationUuid, $createdAt, true);
            $this->insertAudit(
                $activationUuid,
                $actorId,
                'LIVE_CONFIGURATION_ROLLED_BACK',
                $this->nullableString($current['candidate_sha256'] ?? null),
                $this->nullableString($record['candidate_sha256']),
                'PREVIOUS_LIVE_STATE_RESTORED',
                $correlationId,
                $createdAt
            );
            $connection->commit();

            return $activationUuid;
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }
    }

    public function getCurrent(int $storeId): ?LiveActivation
    {
        $row = $this->getCurrentRow($storeId);

        return $row === null ? null : $this->hydrate($row);
    }

    public function getByUuid(string $activationUuid): LiveActivation
    {
        return $this->hydrate($this->getRow($activationUuid));
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
                ->from($this->table(self::ACTIVATION_TABLE))
                ->order('created_at DESC')
                ->limit($limit)
        ));
    }

    /**
     * @param array<string, mixed> $transformation
     */
    private function writeEvent(
        int $storeId,
        string $action,
        ?string $candidateUuid,
        ?string $sourceExperimentUuid,
        array $transformation,
        ?string $candidateHash,
        string $indexEvidenceHash,
        string $targetAlias,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): string {
        $createdAt = $this->normalizeDate($createdAt);
        $connection = $this->resourceConnection->getConnection();
        $connection->beginTransaction();

        try {
            $current = $this->getCurrentRow($storeId, true);

            if (
                $current !== null
                && $this->nullableString($current['candidate_uuid'] ?? null) === $candidateUuid
                && $this->nullableString($current['candidate_sha256'] ?? null) === $candidateHash
                && (string)$current['index_evidence_sha256'] === $indexEvidenceHash
                && (string)$current['target_alias'] === $targetAlias
                && (string)$current['transformation_json'] === $this->canonicalJson->encode($transformation)
            ) {
                throw new UnexpectedValueException('The exact candidate is already active for this store');
            }

            $activationUuid = $this->uuidGenerator->generate();
            $record = $this->eventRecord(
                $activationUuid,
                $storeId,
                $action,
                $candidateUuid,
                $sourceExperimentUuid,
                $current === null ? null : (string)$current['activation_uuid'],
                $transformation,
                $candidateHash,
                $indexEvidenceHash,
                $targetAlias,
                $actorId,
                $createdAt
            );
            $connection->insert($this->table(self::ACTIVATION_TABLE), $record);
            $this->persistState($storeId, $activationUuid, $createdAt, $current !== null);
            $this->insertAudit(
                $activationUuid,
                $actorId,
                'LIVE_CONFIGURATION_ACTIVATED',
                $current === null ? null : $this->nullableString($current['candidate_sha256'] ?? null),
                $candidateHash,
                'ACCEPTED_WINNER_ACTIVATED',
                $correlationId,
                $createdAt
            );
            $connection->commit();

            return $activationUuid;
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }
    }

    /**
     * @param array<string, mixed> $transformation
     * @return array<string, int|string|null>
     */
    private function eventRecord(
        string $activationUuid,
        int $storeId,
        string $action,
        ?string $candidateUuid,
        ?string $sourceExperimentUuid,
        ?string $previousActivationUuid,
        array $transformation,
        ?string $candidateHash,
        string $indexEvidenceHash,
        string $targetAlias,
        int $actorId,
        string $createdAt
    ): array {
        return [
            'activation_uuid' => strtolower($activationUuid),
            'store_id' => $storeId,
            'action' => $action,
            'candidate_uuid' => $candidateUuid,
            'source_experiment_uuid' => $sourceExperimentUuid,
            'previous_activation_uuid' => $previousActivationUuid,
            'transformation_json' => $this->canonicalJson->encode($transformation),
            'candidate_sha256' => $candidateHash,
            'index_evidence_sha256' => $indexEvidenceHash,
            'target_alias' => $targetAlias,
            'actor_id' => $actorId,
            'created_at' => $createdAt,
        ];
    }

    private function persistState(
        int $storeId,
        string $activationUuid,
        string $createdAt,
        bool $exists
    ): void {
        $connection = $this->resourceConnection->getConnection();
        $state = [
            'current_activation_uuid' => strtolower($activationUuid),
            'updated_at' => $createdAt,
        ];

        if ($exists) {
            $connection->update(
                $this->table(self::STATE_TABLE),
                $state + ['version' => new \Zend_Db_Expr('version + 1')],
                ['store_id = ?' => $storeId]
            );
            return;
        }

        $connection->insert($this->table(self::STATE_TABLE), $state + ['store_id' => $storeId, 'version' => 1]);
    }

    /**
     * @return array<string, mixed>|null
     */
    private function getCurrentRow(int $storeId, bool $forUpdate = false): ?array
    {
        $connection = $this->resourceConnection->getConnection();
        $select = $connection->select()
            ->from(['state' => $this->table(self::STATE_TABLE)], [])
            ->joinInner(
                ['activation' => $this->table(self::ACTIVATION_TABLE)],
                'activation.activation_uuid = state.current_activation_uuid'
            )
            ->where('state.store_id = ?', $storeId)
            ->limit(1);

        if ($forUpdate) {
            $select->forUpdate();
        }

        $row = $connection->fetchRow($select);

        return is_array($row) ? $row : null;
    }

    /**
     * @return array<string, mixed>
     */
    private function getRow(string $activationUuid): array
    {
        $this->assertUuid($activationUuid);
        $connection = $this->resourceConnection->getConnection();
        $row = $connection->fetchRow(
            $connection->select()
                ->from($this->table(self::ACTIVATION_TABLE))
                ->where('activation_uuid = ?', strtolower($activationUuid))
                ->limit(1)
        );

        if (!is_array($row)) {
            throw new UnexpectedValueException('Live activation does not exist');
        }

        return $row;
    }

    /**
     * @param array<string, mixed> $row
     */
    private function hydrate(array $row): LiveActivation
    {
        return new LiveActivation(
            (string)$row['activation_uuid'],
            (int)$row['store_id'],
            (string)$row['action'],
            $this->nullableString($row['candidate_uuid'] ?? null),
            $this->nullableString($row['source_experiment_uuid'] ?? null),
            $this->nullableString($row['previous_activation_uuid'] ?? null),
            $this->decodeTransformation((string)$row['transformation_json']),
            $this->nullableString($row['candidate_sha256'] ?? null),
            (string)$row['index_evidence_sha256'],
            (string)$row['target_alias'],
            (int)$row['actor_id'],
            (string)$row['created_at']
        );
    }

    /**
     * @return array{type: string, boosts?: array<string, float>}
     */
    private function decodeTransformation(string $json): array
    {
        $decoded = json_decode($json, true, 512, JSON_THROW_ON_ERROR);

        if (!is_array($decoded) || array_is_list($decoded)) {
            throw new UnexpectedValueException('Persisted live transformation is invalid');
        }

        if (($decoded['type'] ?? null) === 'STOCK') {
            return ['type' => 'STOCK'];
        }

        $boosts = $decoded['boosts'] ?? null;

        if (($decoded['type'] ?? null) !== 'FIELD_BOOST' || !is_array($boosts) || array_is_list($boosts)) {
            throw new UnexpectedValueException('Persisted live transformation is invalid');
        }

        $normalized = [];

        foreach ($boosts as $field => $boost) {
            if (!is_string($field) || (!is_float($boost) && !is_int($boost))) {
                throw new UnexpectedValueException('Persisted live field boost is invalid');
            }

            $normalized[$field] = (float)$boost;
        }

        return ['type' => 'FIELD_BOOST', 'boosts' => $normalized];
    }

    /**
     * @param array<string, mixed> $transformation
     */
    private function assertTransformation(array $transformation): void
    {
        $boosts = $transformation['boosts'] ?? null;

        if (($transformation['type'] ?? null) !== 'FIELD_BOOST' || !is_array($boosts) || $boosts === []) {
            throw new InvalidArgumentException('Only a bounded field boost may be activated');
        }

        foreach ($boosts as $field => $boost) {
            if (
                !is_string($field)
                || $field === ''
                || !is_float($boost)
                || !is_finite($boost)
                || $boost < 0.1
                || $boost > 20.0
            ) {
                throw new InvalidArgumentException('Activated field boosts must match the validated candidate');
            }
        }
    }

    private function assertCommon(
        int $storeId,
        int $actorId,
        string $indexEvidenceHash,
        string $targetAlias,
        string $createdAt,
        string $correlationId
    ): void {
        if ($storeId < 1 || $actorId < 1 || $targetAlias === '' || strlen($targetAlias) > 255) {
            throw new InvalidArgumentException('Live activation requires a store, alias, and authenticated admin');
        }

        $this->assertHash($indexEvidenceHash);
        $this->normalizeDate($createdAt);
        $this->assertCorrelation($correlationId);
    }

    private function assertUuid(string $uuid): void
    {
        if (!preg_match(self::UUID_PATTERN, $uuid)) {
            throw new InvalidArgumentException('Live activation identity must be a UUID');
        }
    }

    private function assertHash(string $hash): void
    {
        if (!preg_match(self::HASH_PATTERN, $hash)) {
            throw new InvalidArgumentException('Live activation identity must be a SHA-256 hash');
        }
    }

    private function assertCorrelation(string $correlationId): void
    {
        if ($correlationId === '' || strlen($correlationId) > 64) {
            throw new InvalidArgumentException('Live activation correlation identity is invalid');
        }
    }

    private function normalizeDate(string $date): string
    {
        return (new DateTimeImmutable($date))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d H:i:s');
    }

    private function nullableString(mixed $value): ?string
    {
        return is_string($value) && $value !== '' ? $value : null;
    }

    private function table(string $name): string
    {
        return $this->resourceConnection->getTableName($name);
    }

    private function insertAudit(
        string $activationUuid,
        int $actorId,
        string $action,
        ?string $beforeHash,
        ?string $afterHash,
        string $reasonCode,
        string $correlationId,
        string $createdAt
    ): void {
        $this->resourceConnection->getConnection()->insert($this->table(self::AUDIT_TABLE), [
            'event_uuid' => $this->uuidGenerator->generate(),
            'actor_type' => 'ADMIN',
            'actor_id' => (string)$actorId,
            'action' => $action,
            'target_type' => 'LIVE_CONFIGURATION',
            'target_uuid' => $activationUuid,
            'before_identity_sha256' => $beforeHash,
            'after_identity_sha256' => $afterHash,
            'result' => 'SUCCESS',
            'reason_code' => $reasonCode,
            'correlation_id' => $correlationId,
            'created_at' => $createdAt,
        ]);
    }
}
