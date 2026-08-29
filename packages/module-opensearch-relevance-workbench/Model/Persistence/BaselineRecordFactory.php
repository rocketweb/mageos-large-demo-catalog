<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

use DateTimeImmutable;
use DateTimeZone;
use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\StockBaselineCapture;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;

class BaselineRecordFactory
{
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/iD';

    public function __construct(private readonly CanonicalJson $canonicalJson)
    {
    }

    public function create(
        StockBaselineCapture $capture,
        int $storeId,
        string $evidenceUuid,
        string $configurationUuid,
        string $auditEventUuid,
        int $actorId,
        string $capturedAt,
        string $correlationId
    ): BaselinePersistenceRecords {
        $this->assertUuid($evidenceUuid);
        $this->assertUuid($configurationUuid);
        $this->assertUuid($auditEventUuid);

        if ($storeId < 1 || $actorId < 1) {
            throw new InvalidArgumentException('Baseline persistence requires a store and admin actor');
        }

        if ($correlationId === '' || strlen($correlationId) > 64) {
            throw new InvalidArgumentException('Baseline correlation ID must contain 1 to 64 characters');
        }

        $capturedAt = (new DateTimeImmutable($capturedAt))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d H:i:s');
        $indexEvidence = $capture->getIndexEvidence();
        $captureResult = $capture->getCaptureResult();
        $template = $captureResult->getTemplate();
        $remoteConfiguration = $capture->getRemoteConfiguration();
        $evidenceRecord = [
            'evidence_uuid' => strtolower($evidenceUuid),
            'store_id' => $storeId,
            'alias_name' => $indexEvidence->getAlias(),
            'physical_index' => $indexEvidence->getPhysicalIndex(),
            'index_uuid' => $indexEvidence->getIndexUuid(),
            'mapping_sha256' => $indexEvidence->getMappingHash(),
            'settings_sha256' => $indexEvidence->getRelevantSettingsHash(),
            'primary_shards_json' => $this->canonicalJson->encode($indexEvidence->getPrimaryShardBoundaries()),
            'document_count' => $indexEvidence->getDocumentCount(),
            'captured_at' => $capturedAt,
            'evidence_sha256' => $indexEvidence->getEvidenceHash(),
        ];
        $configurationRecord = [
            'configuration_uuid' => strtolower($configurationUuid),
            'store_id' => $storeId,
            'kind' => 'BASELINE',
            'parent_baseline_uuid' => null,
            'template_json' => $this->canonicalJson->encode($template->getTemplate()),
            'transformation_json' => $this->canonicalJson->encode([
                'type' => 'STOCK_CAPTURE',
                'field_capabilities' => $capture->getFieldCapabilities(),
            ]),
            'index_evidence_uuid' => strtolower($evidenceUuid),
            'pipeline_identity' => $remoteConfiguration['searchPipeline'],
            'rendered_sample_hashes_json' => $this->canonicalJson->encode(
                $captureResult->getValidationEvidence()
            ),
            'validation_state' => 'VALID',
            'canonical_sha256' => $capture->getConfigurationHash(),
            'remote_configuration_id' => null,
            'created_at' => $capturedAt,
        ];
        $auditEvent = [
            'event_uuid' => strtolower($auditEventUuid),
            'actor_type' => 'ADMIN',
            'actor_id' => (string)$actorId,
            'action' => 'BASELINE_CAPTURED',
            'target_type' => 'SEARCH_CONFIGURATION',
            'target_uuid' => strtolower($configurationUuid),
            'before_identity_sha256' => null,
            'after_identity_sha256' => $capture->getConfigurationHash(),
            'result' => 'SUCCESS',
            'reason_code' => 'BASELINE_ROUND_TRIP_VALID',
            'correlation_id' => $correlationId,
            'created_at' => $capturedAt,
        ];

        return new BaselinePersistenceRecords($evidenceRecord, $configurationRecord, $auditEvent);
    }

    private function assertUuid(string $uuid): void
    {
        if (preg_match(self::UUID_PATTERN, $uuid) !== 1) {
            throw new InvalidArgumentException('Baseline persistence identities must be UUIDs');
        }
    }
}
