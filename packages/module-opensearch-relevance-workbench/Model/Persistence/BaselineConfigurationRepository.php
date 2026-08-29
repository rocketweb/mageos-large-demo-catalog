<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

use Magento\Framework\App\ResourceConnection;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplateHydrator;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\StockBaselineCapture;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\PersistedBaselineConfiguration;
use Throwable;
use UnexpectedValueException;

class BaselineConfigurationRepository
{
    private const EVIDENCE_TABLE = 'osrw_index_evidence';
    private const CONFIGURATION_TABLE = 'osrw_search_configuration';
    private const AUDIT_TABLE = 'osrw_audit_event';

    public function __construct(
        private readonly ResourceConnection $resourceConnection,
        private readonly BaselineRecordFactory $recordFactory,
        private readonly UuidGenerator $uuidGenerator,
        private readonly BaselineTemplateHydrator $templateHydrator
    ) {
    }

    public function save(
        StockBaselineCapture $capture,
        int $storeId,
        int $actorId,
        string $capturedAt,
        string $correlationId
    ): string {
        $connection = $this->resourceConnection->getConnection();
        $configurationTable = $this->resourceConnection->getTableName(self::CONFIGURATION_TABLE);
        $existingConfiguration = $connection->fetchRow(
            $connection->select()
                ->from($configurationTable, ['configuration_uuid'])
                ->where('store_id = ?', $storeId)
                ->where('canonical_sha256 = ?', $capture->getConfigurationHash())
                ->limit(1)
        );

        if (
            is_array($existingConfiguration)
            && isset($existingConfiguration['configuration_uuid'])
            && is_string($existingConfiguration['configuration_uuid'])
            && $existingConfiguration['configuration_uuid'] !== ''
        ) {
            return $existingConfiguration['configuration_uuid'];
        }

        $evidenceTable = $this->resourceConnection->getTableName(self::EVIDENCE_TABLE);
        $existingEvidence = $connection->fetchRow(
            $connection->select()
                ->from($evidenceTable, ['evidence_uuid'])
                ->where('store_id = ?', $storeId)
                ->where('evidence_sha256 = ?', $capture->getIndexEvidence()->getEvidenceHash())
                ->limit(1)
        );
        $evidenceUuid = is_array($existingEvidence)
            && isset($existingEvidence['evidence_uuid'])
            && is_string($existingEvidence['evidence_uuid'])
            && $existingEvidence['evidence_uuid'] !== ''
                ? $existingEvidence['evidence_uuid']
                : $this->uuidGenerator->generate();
        $configurationUuid = $this->uuidGenerator->generate();
        $records = $this->recordFactory->create(
            $capture,
            $storeId,
            $evidenceUuid,
            $configurationUuid,
            $this->uuidGenerator->generate(),
            $actorId,
            $capturedAt,
            $correlationId
        );
        $connection->beginTransaction();

        try {
            if (!is_array($existingEvidence)) {
                $connection->insert($evidenceTable, $records->getIndexEvidence());
            }

            $connection->insert($configurationTable, $records->getConfiguration());
            $connection->insert(
                $this->resourceConnection->getTableName(self::AUDIT_TABLE),
                $records->getAuditEvent()
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
        $configurationTable = $this->resourceConnection->getTableName(self::CONFIGURATION_TABLE);
        $evidenceTable = $this->resourceConnection->getTableName(self::EVIDENCE_TABLE);
        $select = $connection->select()
            ->from(
                ['configuration' => $configurationTable],
                [
                    'configuration_uuid',
                    'store_id',
                    'kind',
                    'validation_state',
                    'canonical_sha256',
                    'transformation_json',
                    'created_at',
                ]
            )
            ->joinInner(
                ['evidence' => $evidenceTable],
                'evidence.evidence_uuid = configuration.index_evidence_uuid',
                ['alias_name', 'physical_index', 'evidence_sha256']
            )
            ->where('configuration.kind = ?', 'BASELINE')
            ->order('configuration.created_at DESC')
            ->limit($limit);

        return array_values($connection->fetchAll($select));
    }

    public function get(string $configurationUuid): PersistedBaselineConfiguration
    {
        $connection = $this->resourceConnection->getConnection();
        $configurationTable = $this->resourceConnection->getTableName(self::CONFIGURATION_TABLE);
        $evidenceTable = $this->resourceConnection->getTableName(self::EVIDENCE_TABLE);
        $row = $connection->fetchRow(
            $connection->select()
                ->from(['configuration' => $configurationTable])
                ->joinInner(
                    ['evidence' => $evidenceTable],
                    'evidence.evidence_uuid = configuration.index_evidence_uuid',
                    ['alias_name', 'physical_index', 'evidence_sha256']
                )
                ->where('configuration.configuration_uuid = ?', $configurationUuid)
                ->where('configuration.kind = ?', 'BASELINE')
                ->where('configuration.validation_state = ?', 'VALID')
                ->limit(1)
        );

        if (!is_array($row)) {
            throw new UnexpectedValueException('Locally verified baseline does not exist');
        }

        $template = $this->decodeObject((string)$row['template_json']);
        $transformation = $this->decodeObject((string)$row['transformation_json']);
        $fieldCapabilities = $transformation['field_capabilities'] ?? null;

        if (!is_array($fieldCapabilities) || array_is_list($fieldCapabilities)) {
            throw new UnexpectedValueException('Persisted baseline field registry is invalid');
        }

        return new PersistedBaselineConfiguration(
            (string)$row['configuration_uuid'],
            (int)$row['store_id'],
            $this->templateHydrator->hydrate($template),
            $this->normalizeFieldCapabilities($fieldCapabilities),
            (string)$row['index_evidence_uuid'],
            (string)$row['alias_name'],
            (string)$row['physical_index'],
            (string)$row['evidence_sha256'],
            (string)$row['pipeline_identity'],
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
            throw new UnexpectedValueException('Persisted baseline metadata is invalid');
        }

        return $decoded;
    }

    /**
     * @param array<array-key, mixed> $capabilities
     * @return array<string, array{searchable: bool, sensitive: bool, dynamic: bool, type: string}>
     */
    private function normalizeFieldCapabilities(array $capabilities): array
    {
        $normalized = [];

        foreach ($capabilities as $field => $capability) {
            if (
                !is_string($field)
                || !is_array($capability)
                || !isset(
                    $capability['searchable'],
                    $capability['sensitive'],
                    $capability['dynamic'],
                    $capability['type']
                )
                || !is_bool($capability['searchable'])
                || !is_bool($capability['sensitive'])
                || !is_bool($capability['dynamic'])
                || !is_string($capability['type'])
            ) {
                throw new UnexpectedValueException('Persisted baseline field capability is invalid');
            }

            $normalized[$field] = [
                'searchable' => $capability['searchable'],
                'sensitive' => $capability['sensitive'],
                'dynamic' => $capability['dynamic'],
                'type' => $capability['type'],
            ];
        }

        return $normalized;
    }
}
