<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

use DateTimeImmutable;
use DateTimeZone;
use InvalidArgumentException;
use Magento\Framework\App\ResourceConnection;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\HumanJudgmentSet;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\PersistedHumanJudgment;
use Throwable;
use UnexpectedValueException;

class HumanJudgmentRepository
{
    private const RATING_TABLE = 'osrw_human_rating';
    private const JUDGMENT_TABLE = 'osrw_judgment_run';
    private const AUDIT_TABLE = 'osrw_audit_event';

    public function __construct(
        private readonly ResourceConnection $resourceConnection,
        private readonly CanonicalJson $canonicalJson,
        private readonly UuidGenerator $uuidGenerator
    ) {
    }

    public function save(
        HumanJudgmentSet $judgmentSet,
        string $snapshotUuid,
        string $indexEvidenceUuid,
        string $correlationId
    ): string {
        if ($correlationId === '' || strlen($correlationId) > 64) {
            throw new InvalidArgumentException('Human judgment correlation ID must contain 1 to 64 characters');
        }

        $connection = $this->resourceConnection->getConnection();
        $judgmentTable = $this->resourceConnection->getTableName(self::JUDGMENT_TABLE);
        $existing = $connection->fetchRow(
            $connection->select()
                ->from($judgmentTable, ['judgment_uuid'])
                ->where('canonical_sha256 = ?', $judgmentSet->getJudgmentHash())
                ->limit(1)
        );

        if (
            is_array($existing)
            && isset($existing['judgment_uuid'])
            && is_string($existing['judgment_uuid'])
            && $existing['judgment_uuid'] !== ''
        ) {
            return $existing['judgment_uuid'];
        }

        $reviewedAt = (new DateTimeImmutable($judgmentSet->getReviewedAt()))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d H:i:s');
        $judgmentUuid = $this->uuidGenerator->generate();
        $ratingRecords = [];

        foreach ($judgmentSet->getRatings() as $rating) {
            $ratingRecords[] = [
                'rating_uuid' => $this->uuidGenerator->generate(),
                'rating_set_uuid' => $judgmentUuid,
                'query_snapshot_uuid' => $snapshotUuid,
                'query_hash' => $rating['query_hash'],
                'document_id' => $rating['document_id'],
                'rating' => $rating['rating'],
                'source' => 'HUMAN',
                'reviewer_id' => $judgmentSet->getReviewedBy(),
                'index_evidence_uuid' => $indexEvidenceUuid,
                'rated_at' => $reviewedAt,
            ];
        }

        $judgmentRecord = [
            'judgment_uuid' => $judgmentUuid,
            'source_type' => 'HUMAN',
            'state' => 'LOCALLY_REVIEWED',
            'model_id' => null,
            'model_metadata_json' => $this->canonicalJson->encode(['provider' => 'HUMAN']),
            'prompt_text' => null,
            'prompt_sha256' => null,
            'rating_type' => 'SCORE0_1',
            'context_fields_json' => $this->canonicalJson->encode(['name', 'sku']),
            'token_limit' => 0,
            'cache_policy_json' => $this->canonicalJson->encode(['mode' => 'DISABLED']),
            'retry_policy_json' => $this->canonicalJson->encode(['mode' => 'NONE']),
            'authorization_envelope_json' => $this->canonicalJson->encode([
                'external_spend' => false,
                'rating_count' => $judgmentSet->getRatingCount(),
            ]),
            'remote_judgment_id' => null,
            'total_count' => $judgmentSet->getRatingCount(),
            'success_count' => $judgmentSet->getRatingCount(),
            'failure_count' => 0,
            'unrated_count' => 0,
            'effective_imported_judgment_id' => null,
            'canonical_sha256' => $judgmentSet->getJudgmentHash(),
            'created_at' => $reviewedAt,
            'updated_at' => $reviewedAt,
        ];
        $auditEvent = [
            'event_uuid' => $this->uuidGenerator->generate(),
            'actor_type' => 'ADMIN',
            'actor_id' => (string)$judgmentSet->getReviewedBy(),
            'action' => 'HUMAN_RATINGS_REVIEWED',
            'target_type' => 'JUDGMENT',
            'target_uuid' => $judgmentUuid,
            'before_identity_sha256' => null,
            'after_identity_sha256' => $judgmentSet->getJudgmentHash(),
            'result' => 'SUCCESS',
            'reason_code' => 'HUMAN_SCORE0_1_REVIEWED',
            'correlation_id' => $correlationId,
            'created_at' => $reviewedAt,
        ];
        $connection->beginTransaction();

        try {
            $connection->insert($judgmentTable, $judgmentRecord);
            $connection->insertMultiple(
                $this->resourceConnection->getTableName(self::RATING_TABLE),
                $ratingRecords
            );
            $connection->insert(
                $this->resourceConnection->getTableName(self::AUDIT_TABLE),
                $auditEvent
            );
            $connection->commit();
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }

        return $judgmentUuid;
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
                $this->resourceConnection->getTableName(self::JUDGMENT_TABLE),
                [
                    'judgment_uuid',
                    'source_type',
                    'state',
                    'rating_type',
                    'total_count',
                    'canonical_sha256',
                    'created_at',
                ]
            )
            ->where('source_type = ?', 'HUMAN')
            ->order('created_at DESC')
            ->limit($limit);

        return array_values($connection->fetchAll($select));
    }

    public function get(string $judgmentUuid): PersistedHumanJudgment
    {
        $connection = $this->resourceConnection->getConnection();
        $judgmentRow = $connection->fetchRow(
            $connection->select()
                ->from($this->resourceConnection->getTableName(self::JUDGMENT_TABLE))
                ->where('judgment_uuid = ?', $judgmentUuid)
                ->where('source_type = ?', 'HUMAN')
                ->limit(1)
        );

        if (!is_array($judgmentRow)) {
            throw new UnexpectedValueException('Locally reviewed human judgment does not exist');
        }

        $ratingTable = $this->resourceConnection->getTableName(self::RATING_TABLE);
        $snapshotTable = $this->resourceConnection->getTableName('osrw_query_snapshot');
        $entryTable = $this->resourceConnection->getTableName('osrw_query_snapshot_entry');
        $evidenceTable = $this->resourceConnection->getTableName('osrw_index_evidence');
        $ratingRows = array_values($connection->fetchAll(
            $connection->select()
                ->from(['rating' => $ratingTable])
                ->joinInner(
                    ['snapshot' => $snapshotTable],
                    'snapshot.snapshot_uuid = rating.query_snapshot_uuid',
                    ['snapshot_sha256' => 'canonical_sha256']
                )
                ->joinInner(
                    ['entry' => $entryTable],
                    'entry.snapshot_uuid = rating.query_snapshot_uuid'
                    . ' AND entry.query_hash = rating.query_hash',
                    ['query_text']
                )
                ->joinInner(
                    ['evidence' => $evidenceTable],
                    'evidence.evidence_uuid = rating.index_evidence_uuid',
                    ['evidence_sha256']
                )
                ->where('rating.rating_set_uuid = ?', $judgmentUuid)
                ->order(['rating.query_hash ASC', 'rating.document_id ASC'])
        ));

        if ($ratingRows === []) {
            throw new UnexpectedValueException('Human judgment contains no persisted ratings');
        }

        $first = $ratingRows[0];
        $snapshotUuid = (string)$first['query_snapshot_uuid'];
        $indexEvidenceUuid = (string)$first['index_evidence_uuid'];
        $snapshotHash = (string)$first['snapshot_sha256'];
        $indexEvidenceHash = (string)$first['evidence_sha256'];
        $reviewedBy = (int)$first['reviewer_id'];
        $reviewedAt = (string)$first['rated_at'];
        $ratings = [];

        foreach ($ratingRows as $row) {
            if (
                (string)$row['query_snapshot_uuid'] !== $snapshotUuid
                || (string)$row['index_evidence_uuid'] !== $indexEvidenceUuid
                || (string)$row['snapshot_sha256'] !== $snapshotHash
                || (string)$row['evidence_sha256'] !== $indexEvidenceHash
                || (int)$row['reviewer_id'] !== $reviewedBy
                || (string)$row['rated_at'] !== $reviewedAt
            ) {
                throw new UnexpectedValueException('Human judgment ratings do not share one frozen identity');
            }

            $ratings[] = [
                'query_hash' => (string)$row['query_hash'],
                'query_text' => (string)$row['query_text'],
                'document_id' => (string)$row['document_id'],
                'rating' => (float)$row['rating'],
            ];
        }

        $remoteJudgmentId = $judgmentRow['effective_imported_judgment_id']
            ?? $judgmentRow['remote_judgment_id']
            ?? null;

        return new PersistedHumanJudgment(
            (string)$judgmentRow['judgment_uuid'],
            $snapshotUuid,
            $indexEvidenceUuid,
            $snapshotHash,
            $indexEvidenceHash,
            $ratings,
            (string)$judgmentRow['canonical_sha256'],
            $reviewedBy,
            $reviewedAt,
            is_string($remoteJudgmentId) && $remoteJudgmentId !== '' ? $remoteJudgmentId : null
        );
    }
}
