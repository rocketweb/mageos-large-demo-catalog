<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

use DateTimeImmutable;
use DateTimeZone;
use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\EvidenceReport;
use MageOS\OpenSearchRelevanceWorkbench\Model\Proposal\ProposalExport;

class ProposalRecordFactory
{
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/iD';

    public function __construct(private readonly CanonicalJson $canonicalJson)
    {
    }

    /**
     * @param list<string> $warnings
     */
    public function create(
        string $proposalUuid,
        string $experimentUuid,
        int $storeId,
        ProposalExport $export,
        EvidenceReport $evidence,
        array $warnings,
        int $actorId,
        string $createdAt,
        string $correlationId,
        string $auditEventUuid
    ): ProposalPersistenceRecords {
        foreach ([$proposalUuid, $experimentUuid, $auditEventUuid] as $uuid) {
            if (preg_match(self::UUID_PATTERN, $uuid) !== 1) {
                throw new InvalidArgumentException('Proposal persistence identities must be UUIDs');
            }
        }

        if ($storeId < 1 || $actorId < 1) {
            throw new InvalidArgumentException('Proposal persistence requires a store and admin actor');
        }

        if ($correlationId === '' || strlen($correlationId) > 64) {
            throw new InvalidArgumentException('Proposal correlation ID must contain 1 to 64 characters');
        }

        if ($evidence->getEligibility() !== 'WINNER') {
            throw new InvalidArgumentException('Proposal persistence requires accepted winner evidence');
        }

        $createdAt = (new DateTimeImmutable($createdAt))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d H:i:s');
        $evidenceRecord = [
            'primary_metric' => $evidence->getPrimaryMetric(),
            'baseline_metric' => $evidence->getBaselineMetric(),
            'candidate_metric' => $evidence->getCandidateMetric(),
            'metric_delta' => $evidence->getMetricDelta(),
            'judged_coverage' => $evidence->getJudgedCoverage(),
            'per_query' => $evidence->getPerQueryEvidence(),
            'eligibility' => $evidence->getEligibility(),
            'reason_codes' => $evidence->getReasonCodes(),
        ];
        $proposal = [
            'proposal_uuid' => strtolower($proposalUuid),
            'store_id' => $storeId,
            'schema_version' => 'mageos-opensearch-relevance-proposal/v1',
            'source_experiment_uuid' => strtolower($experimentUuid),
            'target_type' => 'review_only',
            'artifact_json' => $export->getCanonicalJson(),
            'artifact_sha256' => $export->getArtifactHash(),
            'evidence_json' => $this->canonicalJson->encode($evidenceRecord),
            'warnings_json' => $this->canonicalJson->encode($warnings),
            'created_by' => $actorId,
            'created_at' => $createdAt,
        ];
        $auditEvent = [
            'event_uuid' => strtolower($auditEventUuid),
            'actor_type' => 'ADMIN',
            'actor_id' => (string)$actorId,
            'action' => 'PROPOSAL_EXPORTED',
            'target_type' => 'PROPOSAL',
            'target_uuid' => strtolower($proposalUuid),
            'before_identity_sha256' => null,
            'after_identity_sha256' => $export->getArtifactHash(),
            'result' => 'SUCCESS',
            'reason_code' => 'REVIEW_ONLY_ARTIFACT_CREATED',
            'correlation_id' => $correlationId,
            'created_at' => $createdAt,
        ];

        return new ProposalPersistenceRecords($proposal, $auditEvent);
    }
}
