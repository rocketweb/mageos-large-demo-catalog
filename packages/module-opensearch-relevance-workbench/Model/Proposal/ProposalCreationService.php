<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Proposal;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Api\IndexEvidenceCaptureInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\PersistedExperiment;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\CandidateConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ProposalRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\UuidGenerator;
use RuntimeException;

class ProposalCreationService
{
    /** @var list<string> */
    private const WARNINGS = [
        'Offline relevance evidence does not establish revenue lift.',
        'This artifact is review only and cannot change live search configuration.',
    ];

    public function __construct(
        private readonly ExperimentRepository $experimentRepository,
        private readonly BaselineConfigurationRepository $baselineRepository,
        private readonly CandidateConfigurationRepository $candidateRepository,
        private readonly ProposalRepository $proposalRepository,
        private readonly ProposalExporter $proposalExporter,
        private readonly UuidGenerator $uuidGenerator,
        private readonly IndexEvidenceCaptureInterface $indexEvidenceCapture
    ) {
    }

    public function create(
        string $experimentUuid,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): string {
        if ($actorId < 1) {
            throw new InvalidArgumentException('Proposal export requires an admin actor');
        }

        $experiment = $this->experimentRepository->getCompleted($experimentUuid);
        $this->assertAcceptedWinner($experiment);
        $identities = $experiment->getInputIdentities();
        $baselineUuid = $this->identity($identities, 'baseline_configuration_uuid');
        $baseline = $this->baselineRepository->get($baselineUuid);
        $candidateUuid = $this->identity($identities, 'candidate_configuration_uuid');
        $baselineHash = $this->identity($identities, 'baseline_configuration_sha256');
        $candidateHash = $this->identity($identities, 'candidate_configuration_sha256');
        $indexEvidenceHash = $this->identity($identities, 'index_evidence_sha256');

        if (
            $baseline->getStoreId() !== $experiment->getStoreId()
            || !hash_equals($baselineHash, $baseline->getConfigurationHash())
            || !hash_equals($indexEvidenceHash, $baseline->getIndexEvidenceHash())
            || !hash_equals(
                $indexEvidenceHash,
                $this->indexEvidenceCapture->capture($baseline->getTargetAlias())->getEvidenceHash()
            )
        ) {
            throw new RuntimeException('Accepted experiment index evidence is stale');
        }

        $existing = $this->proposalRepository->getByExperimentId($experimentUuid);

        if ($existing !== null) {
            return $existing;
        }

        $candidate = $this->candidateRepository->get($candidateUuid);

        if (
            $candidate->getStoreId() !== $experiment->getStoreId()
            || $candidate->getConfigurationHash() !== $candidateHash
        ) {
            throw new RuntimeException('Accepted experiment candidate no longer matches local configuration evidence');
        }

        $proposalUuid = $this->uuidGenerator->generate();
        $export = $this->proposalExporter->export(
            $proposalUuid,
            $createdAt,
            $experiment->getStoreId(),
            $experiment->getExperimentUuid(),
            $this->identity($identities, 'query_snapshot_sha256'),
            $this->identity($identities, 'judgment_sha256'),
            $indexEvidenceHash,
            $baselineHash,
            $candidateHash,
            $candidate->getTransformation(),
            $experiment->getEvidence(),
            self::WARNINGS
        );

        return $this->proposalRepository->save(
            $proposalUuid,
            $experiment->getExperimentUuid(),
            $experiment->getStoreId(),
            $export,
            $experiment->getEvidence(),
            self::WARNINGS,
            $actorId,
            $createdAt,
            $correlationId
        );
    }

    private function assertAcceptedWinner(PersistedExperiment $experiment): void
    {
        if (
            $experiment->getState() !== 'ACCEPTED'
            || $experiment->getEvidence()->getEligibility() !== 'WINNER'
            || $experiment->getAcceptedBy() === null
            || $experiment->getAcceptedAt() === null
        ) {
            throw new RuntimeException('Only explicitly accepted winner evidence may be exported');
        }
    }

    /**
     * @param array<string, float|int|string> $identities
     */
    private function identity(array $identities, string $key): string
    {
        $value = $identities[$key] ?? null;

        if (!is_string($value) || $value === '') {
            throw new RuntimeException('Accepted experiment is missing identity ' . $key);
        }

        return $value;
    }
}
