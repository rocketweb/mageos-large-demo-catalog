<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Experiment;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;

class HumanExperimentPlanFactory
{
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/iD';

    public function __construct(private readonly CanonicalJson $canonicalJson)
    {
    }

    public function create(
        string $querySnapshotId,
        string $querySnapshotHash,
        string $remoteQuerySetId,
        string $baselineConfigurationId,
        string $baselineConfigurationHash,
        string $candidateConfigurationId,
        string $candidateConfigurationHash,
        string $judgmentId,
        string $judgmentHash,
        string $indexEvidenceHash,
        int $resultDepth,
        float $minimumJudgedCoverage,
        string $primaryMetric,
        float $minimumImprovement = 0.01,
        ?string $baselineLocalConfigurationId = null,
        ?string $candidateLocalConfigurationId = null,
        ?string $localJudgmentId = null
    ): HumanExperimentPlan {
        foreach (
            [
                $querySnapshotId,
                $remoteQuerySetId,
                $baselineConfigurationId,
                $candidateConfigurationId,
                $judgmentId,
            ] as $uuid
        ) {
            if (preg_match(self::UUID_PATTERN, $uuid) !== 1) {
                throw new InvalidArgumentException('Experiment identifiers must be UUIDs');
            }
        }

        foreach (
            [
                $baselineLocalConfigurationId,
                $candidateLocalConfigurationId,
                $localJudgmentId,
            ] as $localUuid
        ) {
            if ($localUuid !== null && preg_match(self::UUID_PATTERN, $localUuid) !== 1) {
                throw new InvalidArgumentException('Local experiment identifiers must be UUIDs');
            }
        }

        foreach (
            [
                $querySnapshotHash,
                $baselineConfigurationHash,
                $candidateConfigurationHash,
                $judgmentHash,
                $indexEvidenceHash,
            ] as $hash
        ) {
            if (preg_match('/\A[0-9a-f]{64}\z/', $hash) !== 1) {
                throw new InvalidArgumentException('Experiment identities must be lowercase SHA-256 values');
            }
        }

        if ($resultDepth < 1 || $resultDepth > 100) {
            throw new InvalidArgumentException('Experiment result depth must be between 1 and 100');
        }

        if ($minimumJudgedCoverage < 0.0 || $minimumJudgedCoverage > 1.0) {
            throw new InvalidArgumentException('Minimum judged coverage must be between 0.0 and 1.0');
        }

        if ($minimumImprovement < -1.0 || $minimumImprovement > 1.0) {
            throw new InvalidArgumentException('Minimum improvement must be between -1.0 and 1.0');
        }

        if ($primaryMetric !== 'NDCG@10') {
            throw new InvalidArgumentException('Phase 1 primary metric must be NDCG@10');
        }

        $remotePayloads = [
            'PAIRWISE_COMPARISON' => [
                'querySetId' => $remoteQuerySetId,
                'searchConfigurationList' => [$baselineConfigurationId, $candidateConfigurationId],
                'size' => $resultDepth,
                'type' => 'PAIRWISE_COMPARISON',
            ],
            'POINTWISE_BASELINE' => [
                'querySetId' => $remoteQuerySetId,
                'searchConfigurationList' => [$baselineConfigurationId],
                'judgmentList' => [$judgmentId],
                'size' => $resultDepth,
                'type' => 'POINTWISE_EVALUATION',
            ],
            'POINTWISE_CANDIDATE' => [
                'querySetId' => $remoteQuerySetId,
                'searchConfigurationList' => [$candidateConfigurationId],
                'judgmentList' => [$judgmentId],
                'size' => $resultDepth,
                'type' => 'POINTWISE_EVALUATION',
            ],
        ];
        $inputIdentities = [
            'query_snapshot_id' => strtolower($querySnapshotId),
            'query_snapshot_sha256' => $querySnapshotHash,
            'remote_query_set_id' => strtolower($remoteQuerySetId),
            'baseline_remote_configuration_id' => strtolower($baselineConfigurationId),
            'baseline_configuration_sha256' => $baselineConfigurationHash,
            'candidate_remote_configuration_id' => strtolower($candidateConfigurationId),
            'candidate_configuration_sha256' => $candidateConfigurationHash,
            'remote_judgment_id' => strtolower($judgmentId),
            'judgment_sha256' => $judgmentHash,
            'index_evidence_sha256' => $indexEvidenceHash,
            'result_depth' => $resultDepth,
            'minimum_judged_coverage' => $minimumJudgedCoverage,
            'minimum_improvement' => $minimumImprovement,
            'primary_metric' => $primaryMetric,
            'evidence_schema_version' => 2,
        ];

        if ($baselineLocalConfigurationId !== null) {
            $inputIdentities['baseline_configuration_uuid'] = strtolower($baselineLocalConfigurationId);
        }

        if ($candidateLocalConfigurationId !== null) {
            $inputIdentities['candidate_configuration_uuid'] = strtolower($candidateLocalConfigurationId);
        }

        if ($localJudgmentId !== null) {
            $inputIdentities['judgment_uuid'] = strtolower($localJudgmentId);
        }
        $inputHash = $this->canonicalJson->hash($inputIdentities + ['remote_payloads' => $remotePayloads]);

        return new HumanExperimentPlan(
            $remotePayloads,
            $inputIdentities,
            $inputHash,
            $primaryMetric,
            $minimumJudgedCoverage,
            $minimumImprovement
        );
    }
}
