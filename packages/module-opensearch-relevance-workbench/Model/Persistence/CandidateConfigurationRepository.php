<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

use DateTimeImmutable;
use DateTimeZone;
use InvalidArgumentException;
use Magento\Framework\App\ResourceConnection;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplateHydrator;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\PersistedCandidateConfiguration;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\ValidatedCandidateConfiguration;
use Throwable;
use UnexpectedValueException;

class CandidateConfigurationRepository
{
    private const CONFIGURATION_TABLE = 'osrw_search_configuration';
    private const AUDIT_TABLE = 'osrw_audit_event';

    public function __construct(
        private readonly ResourceConnection $resourceConnection,
        private readonly CanonicalJson $canonicalJson,
        private readonly UuidGenerator $uuidGenerator,
        private readonly BaselineTemplateHydrator $templateHydrator
    ) {
    }

    public function save(
        ValidatedCandidateConfiguration $validatedCandidate,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): string {
        if ($actorId < 1 || $correlationId === '' || strlen($correlationId) > 64) {
            throw new InvalidArgumentException('Candidate persistence requires an admin actor and correlation ID');
        }

        $candidate = $validatedCandidate->getCandidate();
        $baseline = $validatedCandidate->getBaseline();
        $connection = $this->resourceConnection->getConnection();
        $configurationTable = $this->resourceConnection->getTableName(self::CONFIGURATION_TABLE);
        $existing = $connection->fetchRow(
            $connection->select()
                ->from($configurationTable, ['configuration_uuid'])
                ->where('store_id = ?', $baseline->getStoreId())
                ->where('canonical_sha256 = ?', $candidate->getConfigurationHash())
                ->limit(1)
        );

        if (
            is_array($existing)
            && isset($existing['configuration_uuid'])
            && is_string($existing['configuration_uuid'])
            && $existing['configuration_uuid'] !== ''
        ) {
            return $existing['configuration_uuid'];
        }

        $createdAt = (new DateTimeImmutable($createdAt))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d H:i:s');
        $configurationUuid = $this->uuidGenerator->generate();
        $configurationRecord = [
            'configuration_uuid' => $configurationUuid,
            'store_id' => $baseline->getStoreId(),
            'kind' => 'CANDIDATE',
            'parent_baseline_uuid' => $baseline->getConfigurationUuid(),
            'template_json' => $this->canonicalJson->encode($candidate->getTemplate()),
            'transformation_json' => $this->canonicalJson->encode($candidate->getTransformation()),
            'index_evidence_uuid' => $baseline->getIndexEvidenceUuid(),
            'pipeline_identity' => $baseline->getPipelineIdentity(),
            'rendered_sample_hashes_json' => $this->canonicalJson->encode(
                $validatedCandidate->getValidationEvidence()
            ),
            'validation_state' => 'VALID',
            'canonical_sha256' => $candidate->getConfigurationHash(),
            'remote_configuration_id' => null,
            'created_at' => $createdAt,
        ];
        $auditEvent = [
            'event_uuid' => $this->uuidGenerator->generate(),
            'actor_type' => 'ADMIN',
            'actor_id' => (string)$actorId,
            'action' => 'CANDIDATE_COMPILED',
            'target_type' => 'SEARCH_CONFIGURATION',
            'target_uuid' => $configurationUuid,
            'before_identity_sha256' => $baseline->getConfigurationHash(),
            'after_identity_sha256' => $candidate->getConfigurationHash(),
            'result' => 'SUCCESS',
            'reason_code' => 'FIVE_QUERY_VALIDATION_PASSED',
            'correlation_id' => $correlationId,
            'created_at' => $createdAt,
        ];
        $connection->beginTransaction();

        try {
            $connection->insert($configurationTable, $configurationRecord);
            $connection->insert(
                $this->resourceConnection->getTableName(self::AUDIT_TABLE),
                $auditEvent
            );
            $connection->commit();
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }

        return $configurationUuid;
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
                $this->resourceConnection->getTableName(self::CONFIGURATION_TABLE),
                [
                    'configuration_uuid',
                    'store_id',
                    'parent_baseline_uuid',
                    'transformation_json',
                    'validation_state',
                    'canonical_sha256',
                    'created_at',
                ]
            )
            ->where('kind = ?', 'CANDIDATE')
            ->order('created_at DESC')
            ->limit($limit);

        return array_values($connection->fetchAll($select));
    }

    public function get(string $configurationUuid): PersistedCandidateConfiguration
    {
        $connection = $this->resourceConnection->getConnection();
        $configurationTable = $this->resourceConnection->getTableName(self::CONFIGURATION_TABLE);
        $evidenceTable = $this->resourceConnection->getTableName('osrw_index_evidence');
        $row = $connection->fetchRow(
            $connection->select()
                ->from(['configuration' => $configurationTable])
                ->joinInner(
                    ['evidence' => $evidenceTable],
                    'evidence.evidence_uuid = configuration.index_evidence_uuid',
                    ['physical_index']
                )
                ->where('configuration.configuration_uuid = ?', $configurationUuid)
                ->where('configuration.kind = ?', 'CANDIDATE')
                ->where('configuration.validation_state = ?', 'VALID')
                ->limit(1)
        );

        if (!is_array($row)) {
            throw new UnexpectedValueException('Locally validated candidate does not exist');
        }

        $template = $this->decodeObject((string)$row['template_json']);
        $transformation = $this->decodeObject((string)$row['transformation_json']);
        $type = $transformation['type'] ?? null;
        $boosts = $transformation['boosts'] ?? null;

        if ($type !== 'FIELD_BOOST' || !is_array($boosts) || array_is_list($boosts)) {
            throw new UnexpectedValueException('Persisted candidate transformation is invalid');
        }

        $normalizedBoosts = [];

        foreach ($boosts as $field => $boost) {
            if (!is_string($field) || !is_float($boost)) {
                throw new UnexpectedValueException('Persisted candidate field boost is invalid');
            }

            $normalizedBoosts[$field] = $boost;
        }

        return new PersistedCandidateConfiguration(
            (string)$row['configuration_uuid'],
            (int)$row['store_id'],
            (string)$row['parent_baseline_uuid'],
            $this->templateHydrator->hydrate($template),
            ['type' => 'FIELD_BOOST', 'boosts' => $normalizedBoosts],
            (string)$row['index_evidence_uuid'],
            (string)$row['physical_index'],
            (string)$row['canonical_sha256']
        );
    }

    /**
     * @return array<string, mixed>
     */
    private function decodeObject(string $json): array
    {
        $decoded = json_decode($json, true, 512, JSON_THROW_ON_ERROR);

        if (!is_array($decoded) || array_is_list($decoded)) {
            throw new UnexpectedValueException('Persisted candidate metadata is invalid');
        }

        return $decoded;
    }
}
