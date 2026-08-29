<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Activation;

use MageOS\OpenSearchRelevanceWorkbench\Api\IndexEvidenceCaptureInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\CandidateConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\LiveActivationRepository;
use RuntimeException;

class LiveActivationService
{
    public function __construct(
        private readonly ExperimentRepository $experimentRepository,
        private readonly BaselineConfigurationRepository $baselineRepository,
        private readonly CandidateConfigurationRepository $candidateRepository,
        private readonly IndexEvidenceCaptureInterface $indexEvidenceCapture,
        private readonly LiveActivationRepository $activationRepository
    ) {
    }

    public function activate(
        string $experimentUuid,
        int $actorId,
        string $activatedAt,
        string $correlationId
    ): string {
        $experiment = $this->experimentRepository->getCompleted($experimentUuid);

        if (
            $experiment->getState() !== 'ACCEPTED'
            || $experiment->getEvidence()->getEligibility() !== 'WINNER'
            || $experiment->getAcceptedBy() === null
            || $experiment->getAcceptedAt() === null
        ) {
            throw new RuntimeException('Only an explicitly accepted winning experiment may be activated');
        }

        $identities = $experiment->getInputIdentities();
        $baselineUuid = $this->requiredIdentity($identities, 'baseline_configuration_uuid');
        $candidateUuid = $this->requiredIdentity($identities, 'candidate_configuration_uuid');
        $baselineHash = $this->requiredIdentity($identities, 'baseline_configuration_sha256');
        $candidateHash = $this->requiredIdentity($identities, 'candidate_configuration_sha256');
        $indexEvidenceHash = $this->requiredIdentity($identities, 'index_evidence_sha256');
        $baseline = $this->baselineRepository->get($baselineUuid);
        $candidate = $this->candidateRepository->get($candidateUuid);

        if (
            $baseline->getStoreId() !== $experiment->getStoreId()
            || $candidate->getStoreId() !== $experiment->getStoreId()
            || !hash_equals($baseline->getConfigurationHash(), $baselineHash)
            || !hash_equals($candidate->getConfigurationHash(), $candidateHash)
            || !hash_equals($baseline->getIndexEvidenceHash(), $indexEvidenceHash)
            || $candidate->getParentBaselineUuid() !== $baseline->getConfigurationUuid()
            || $candidate->getIndexEvidenceUuid() !== $baseline->getIndexEvidenceUuid()
            || $candidate->getPhysicalIndex() !== $baseline->getPhysicalIndex()
        ) {
            throw new RuntimeException('Accepted experiment inputs do not match their persisted configurations');
        }

        $freshEvidence = $this->indexEvidenceCapture->capture($baseline->getTargetAlias());

        if (
            $freshEvidence->getAlias() !== $baseline->getTargetAlias()
            || !hash_equals($baseline->getIndexEvidenceHash(), $freshEvidence->getEvidenceHash())
        ) {
            throw new RuntimeException('Activation index evidence is stale');
        }

        return $this->activationRepository->activate(
            $experiment->getStoreId(),
            $experiment->getExperimentUuid(),
            $candidate->getConfigurationUuid(),
            $candidate->getTransformation(),
            $candidate->getConfigurationHash(),
            $baseline->getIndexEvidenceHash(),
            $baseline->getTargetAlias(),
            $actorId,
            $activatedAt,
            $correlationId
        );
    }

    /**
     * @param array<string, float|int|string> $identities
     */
    private function requiredIdentity(array $identities, string $key): string
    {
        $value = $identities[$key] ?? null;

        if (!is_string($value) || $value === '') {
            throw new RuntimeException('Accepted experiment is missing required input identity ' . $key);
        }

        return $value;
    }
}
