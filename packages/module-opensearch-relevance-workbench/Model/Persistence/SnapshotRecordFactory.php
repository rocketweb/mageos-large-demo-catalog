<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

use DateTimeImmutable;
use DateTimeZone;
use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\ApprovedQuerySnapshot;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\QuerySnapshotPreview;

class SnapshotRecordFactory
{
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/iD';

    public function __construct(private readonly CanonicalJson $canonicalJson)
    {
    }

    /**
     * @param list<string> $entryUuids
     */
    public function create(
        QuerySnapshotPreview $preview,
        ApprovedQuerySnapshot $approved,
        string $snapshotUuid,
        array $entryUuids,
        string $auditEventUuid,
        string $correlationId
    ): SnapshotPersistenceRecords {
        $this->assertUuid($snapshotUuid);
        $this->assertUuid($auditEventUuid);

        if (count($entryUuids) !== count($approved->getEntries())) {
            throw new InvalidArgumentException('Snapshot entry UUID count must match approved entries');
        }

        foreach ($entryUuids as $entryUuid) {
            $this->assertUuid($entryUuid);
        }

        if (
            $preview->getStoreId() !== $approved->getStoreId()
            || !hash_equals($preview->getSnapshotHash(), $approved->getSnapshotHash())
        ) {
            throw new InvalidArgumentException('Snapshot records require the exact approved preview');
        }

        if ($correlationId === '' || strlen($correlationId) > 64) {
            throw new InvalidArgumentException('Snapshot correlation ID must contain 1 to 64 characters');
        }

        $policy = $approved->getPolicy();
        $approvedAt = (new DateTimeImmutable($approved->getApprovedAt()))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d H:i:s');
        $boundary = $approved->getHighWaterBoundary();
        $snapshot = [
            'snapshot_uuid' => strtolower($snapshotUuid),
            'schedule_uuid' => null,
            'store_id' => $approved->getStoreId(),
            'status' => $approved->getStatus(),
            'source_window_json' => $this->canonicalJson->encode([
                'start' => $policy->getSourceWindowStart(),
                'end' => $policy->getSourceWindowEnd(),
                'high_water_boundary' => $boundary,
            ]),
            'high_water_updated_at' => $boundary['updated_at'] === '' ? null : $boundary['updated_at'],
            'high_water_query_id' => $boundary['query_id'],
            'sampling_policy_json' => $this->canonicalJson->encode([
                'minimum_popularity' => $policy->getMinimumPopularity(),
                'positive_result_limit' => $policy->getPositiveResultLimit(),
                'zero_result_limit' => $policy->getZeroResultLimit(),
                'total_limit' => $policy->getTotalLimit(),
                'include_redirects' => $policy->includesRedirects(),
            ]),
            'privacy_policy_json' => $this->canonicalJson->encode([
                'version' => $policy->getPrivacyPolicyVersion(),
                'maximum_term_length' => $policy->getMaximumTermLength(),
            ]),
            'source_count' => $preview->getSourceCount(),
            'selected_count' => $preview->getSelectedCount(),
            'excluded_count' => array_sum($preview->getExcludedCounts()),
            'redacted_count' => 0,
            'canonical_sha256' => $approved->getSnapshotHash(),
            'remote_query_set_id' => null,
            'approved_by' => $approved->getApprovedBy(),
            'approved_at' => $approvedAt,
        ];
        $entries = $this->entryRecords($approved->getEntries(), $snapshotUuid, $entryUuids);

        $auditEvent = [
            'event_uuid' => strtolower($auditEventUuid),
            'actor_type' => 'ADMIN',
            'actor_id' => (string)$approved->getApprovedBy(),
            'action' => 'SNAPSHOT_APPROVED',
            'target_type' => 'QUERY_SNAPSHOT',
            'target_uuid' => strtolower($snapshotUuid),
            'before_identity_sha256' => null,
            'after_identity_sha256' => $approved->getSnapshotHash(),
            'result' => 'SUCCESS',
            'reason_code' => 'EXACT_HASH_APPROVED',
            'correlation_id' => $correlationId,
            'created_at' => $approvedAt,
        ];

        return new SnapshotPersistenceRecords($snapshot, $entries, $auditEvent);
    }

    /**
     * @param list<string> $entryUuids
     */
    public function createDraft(
        QuerySnapshotPreview $preview,
        string $scheduleUuid,
        string $snapshotUuid,
        array $entryUuids,
        string $auditEventUuid,
        string $preparedAt,
        string $correlationId
    ): SnapshotPersistenceRecords {
        $this->assertUuid($scheduleUuid);
        $this->assertUuid($snapshotUuid);
        $this->assertUuid($auditEventUuid);

        if (count($entryUuids) !== count($preview->getEntries())) {
            throw new InvalidArgumentException('Snapshot entry UUID count must match draft entries');
        }

        foreach ($entryUuids as $entryUuid) {
            $this->assertUuid($entryUuid);
        }

        if ($correlationId === '' || strlen($correlationId) > 64) {
            throw new InvalidArgumentException('Snapshot correlation ID must contain 1 to 64 characters');
        }

        $preparedAt = (new DateTimeImmutable($preparedAt))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d H:i:s');
        $policy = $preview->getPolicy();
        $boundary = $preview->getHighWaterBoundary();
        $snapshot = [
            'snapshot_uuid' => strtolower($snapshotUuid),
            'schedule_uuid' => strtolower($scheduleUuid),
            'store_id' => $preview->getStoreId(),
            'status' => 'DRAFT',
            'source_window_json' => $this->canonicalJson->encode([
                'start' => $policy->getSourceWindowStart(),
                'end' => $policy->getSourceWindowEnd(),
                'high_water_boundary' => $boundary,
            ]),
            'high_water_updated_at' => $boundary['updated_at'] === '' ? null : $boundary['updated_at'],
            'high_water_query_id' => $boundary['query_id'],
            'sampling_policy_json' => $this->canonicalJson->encode([
                'minimum_popularity' => $policy->getMinimumPopularity(),
                'positive_result_limit' => $policy->getPositiveResultLimit(),
                'zero_result_limit' => $policy->getZeroResultLimit(),
                'total_limit' => $policy->getTotalLimit(),
                'include_redirects' => $policy->includesRedirects(),
            ]),
            'privacy_policy_json' => $this->canonicalJson->encode([
                'version' => $policy->getPrivacyPolicyVersion(),
                'maximum_term_length' => $policy->getMaximumTermLength(),
            ]),
            'source_count' => $preview->getSourceCount(),
            'selected_count' => $preview->getSelectedCount(),
            'excluded_count' => array_sum($preview->getExcludedCounts()),
            'redacted_count' => 0,
            'canonical_sha256' => $preview->getSnapshotHash(),
            'remote_query_set_id' => null,
            'approved_by' => null,
            'approved_at' => null,
        ];
        $auditEvent = [
            'event_uuid' => strtolower($auditEventUuid),
            'actor_type' => 'SYSTEM',
            'actor_id' => 'CRON',
            'action' => 'SNAPSHOT_DRAFT_PREPARED',
            'target_type' => 'QUERY_SNAPSHOT',
            'target_uuid' => strtolower($snapshotUuid),
            'before_identity_sha256' => null,
            'after_identity_sha256' => $preview->getSnapshotHash(),
            'result' => 'SUCCESS',
            'reason_code' => 'SCHEDULED_DRAFT_ONLY',
            'correlation_id' => $correlationId,
            'created_at' => $preparedAt,
        ];

        return new SnapshotPersistenceRecords(
            $snapshot,
            $this->entryRecords($preview->getEntries(), $snapshotUuid, $entryUuids),
            $auditEvent
        );
    }

    /**
     * @param list<\MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\QuerySnapshotEntry> $entries
     * @param list<string> $entryUuids
     * @return list<array<string, int|string|null>>
     */
    private function entryRecords(array $entries, string $snapshotUuid, array $entryUuids): array
    {
        $records = [];

        foreach ($entries as $ordinal => $entry) {
            $records[] = [
                'entry_uuid' => strtolower($entryUuids[$ordinal]),
                'snapshot_uuid' => strtolower($snapshotUuid),
                'ordinal' => $ordinal,
                'query_text' => $entry->getQueryText(),
                'query_hash' => $entry->getQueryHash(),
                'source_query_id' => $entry->getSourceQueryId(),
                'popularity' => $entry->getPopularity(),
                'result_count' => $entry->getResultCount(),
                'source_updated_at' => $entry->getSourceUpdatedAt(),
                'custom_fields_json' => $entry->getCustomFields() === []
                    ? null
                    : $this->canonicalJson->encode($entry->getCustomFields()),
                'is_excluded' => 0,
                'is_redacted' => 0,
            ];
        }

        return $records;
    }

    private function assertUuid(string $uuid): void
    {
        if (preg_match(self::UUID_PATTERN, $uuid) !== 1) {
            throw new InvalidArgumentException('Snapshot persistence identities must be UUIDs');
        }
    }
}
