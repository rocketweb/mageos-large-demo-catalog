<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Proposal;

use DateTimeImmutable;
use InvalidArgumentException;
use LogicException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\EvidenceReport;

class ProposalExporter
{
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/iD';

    public function __construct(private readonly CanonicalJson $canonicalJson)
    {
    }

    /**
     * @param array<string, mixed> $candidateTransformation
     * @param list<string> $warnings
     */
    public function export(
        string $proposalId,
        string $createdAt,
        int $storeId,
        string $experimentId,
        string $querySnapshotHash,
        string $judgmentHash,
        string $indexEvidenceHash,
        string $baselineConfigurationHash,
        string $candidateConfigurationHash,
        array $candidateTransformation,
        EvidenceReport $evidence,
        array $warnings
    ): ProposalExport {
        if ($evidence->getEligibility() !== 'WINNER') {
            throw new LogicException('Only accepted WINNER evidence may be exported');
        }

        foreach ([$proposalId, $experimentId] as $uuid) {
            if (preg_match(self::UUID_PATTERN, $uuid) !== 1) {
                throw new InvalidArgumentException('Proposal identifiers must be UUIDs');
            }
        }

        foreach (
            [
                $querySnapshotHash,
                $judgmentHash,
                $indexEvidenceHash,
                $baselineConfigurationHash,
                $candidateConfigurationHash,
            ] as $hash
        ) {
            if (preg_match('/\A[0-9a-f]{64}\z/', $hash) !== 1) {
                throw new InvalidArgumentException('Proposal identities must be lowercase SHA-256 values');
            }
        }

        if ($storeId < 0) {
            throw new InvalidArgumentException('Proposal store ID must be non-negative');
        }

        new DateTimeImmutable($createdAt);
        $artifact = [
            'schema' => 'mageos-opensearch-relevance-proposal/v1',
            'proposal_id' => strtolower($proposalId),
            'created_at' => $createdAt,
            'store_id' => $storeId,
            'target_type' => 'review_only',
            'source' => [
                'experiment_id' => strtolower($experimentId),
                'query_snapshot_sha256' => $querySnapshotHash,
                'judgment_sha256' => $judgmentHash,
                'index_evidence_sha256' => $indexEvidenceHash,
            ],
            'baseline' => ['configuration_sha256' => $baselineConfigurationHash],
            'candidate' => [
                'configuration_sha256' => $candidateConfigurationHash,
                'transformation' => $candidateTransformation,
            ],
            'evidence' => [
                'primary_metric' => $evidence->getPrimaryMetric(),
                'baseline_metric' => $evidence->getBaselineMetric(),
                'candidate_metric' => $evidence->getCandidateMetric(),
                'metric_delta' => $evidence->getMetricDelta(),
                'judged_coverage' => $evidence->getJudgedCoverage(),
                'guardrails' => $evidence->getReasonCodes(),
                'eligibility' => $evidence->getEligibility(),
            ],
            'application' => [
                'supported' => false,
                'reason' => 'Version 1 is export only',
            ],
            'warnings' => $warnings,
        ];
        $canonicalJson = $this->canonicalJson->encode($artifact);
        $artifactHash = hash('sha256', $canonicalJson);
        $filename = 'osrw-proposal-' . strtolower($proposalId)
            . '-' . substr($artifactHash, 0, 12) . '.json';

        return new ProposalExport($canonicalJson, $artifactHash, $filename);
    }
}
