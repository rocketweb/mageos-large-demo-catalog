<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Block\Adminhtml;

use Magento\Backend\Block\Template;
use Magento\Backend\Block\Template\Context;
use Magento\Framework\App\Request\DataPersistorInterface;
use Magento\Store\Api\Data\StoreInterface;
use Magento\Store\Api\StoreRepositoryInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\ExperimentEvidenceService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\CandidateConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\HumanJudgmentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\LiveActivationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ProposalRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\SnapshotScheduleRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\OwnedResourceCleanupPreviewService;
use Throwable;

class Workbench extends Template
{
    /**
     * @param array<string, mixed> $data
     */
    public function __construct(
        Context $context,
        private readonly DataPersistorInterface $dataPersistor,
        private readonly StoreRepositoryInterface $storeRepository,
        private readonly QuerySnapshotRepository $snapshotRepository,
        private readonly BaselineConfigurationRepository $baselineRepository,
        private readonly CandidateConfigurationRepository $candidateRepository,
        private readonly HumanJudgmentRepository $humanJudgmentRepository,
        private readonly ExperimentRepository $experimentRepository,
        private readonly ProposalRepository $proposalRepository,
        private readonly ExperimentEvidenceService $experimentEvidenceService,
        private readonly SnapshotScheduleRepository $snapshotScheduleRepository,
        private readonly OwnedResourceCleanupPreviewService $cleanupPreviewService,
        private readonly LiveActivationRepository $liveActivationRepository,
        array $data = []
    ) {
        parent::__construct($context, $data);
    }

    /**
     * @return array<string, mixed>
     */
    public function getPreflightResult(): array
    {
        $result = $this->dataPersistor->get('osrw_preflight_result');
        $this->dataPersistor->clear('osrw_preflight_result');

        return is_array($result) ? $result : [];
    }

    /**
     * @return array<string, mixed>
     */
    public function getSnapshotPreview(): array
    {
        $preview = $this->dataPersistor->get('osrw_snapshot_preview');
        $this->dataPersistor->clear('osrw_snapshot_preview');

        return is_array($preview) ? $preview : [];
    }

    /**
     * @return array<string, mixed>
     */
    public function getRatingQueue(): array
    {
        $queue = $this->dataPersistor->get('osrw_rating_queue');
        $this->dataPersistor->clear('osrw_rating_queue');

        return is_array($queue) ? $queue : [];
    }

    /**
     * @return list<StoreInterface>
     */
    public function getStoreViews(): array
    {
        $stores = array_filter(
            $this->storeRepository->getList(),
            static fn (StoreInterface $store): bool =>
                (int)$store->getId() > 0 && (int)$store->getIsActive() === 1
        );

        usort(
            $stores,
            static fn (StoreInterface $left, StoreInterface $right): int =>
                strcmp((string)$left->getName(), (string)$right->getName())
        );

        return $stores;
    }

    /**
     * @return list<array<string, mixed>>
     */
    public function getRecentSnapshots(): array
    {
        return $this->snapshotRepository->listRecent();
    }

    /**
     * @return list<array<string, mixed>>
     */
    public function getRecentBaselines(): array
    {
        $baselines = $this->baselineRepository->listRecent();

        foreach ($baselines as &$baseline) {
            $transformation = json_decode(
                (string)($baseline['transformation_json'] ?? ''),
                true
            );
            $fieldCapabilities = is_array($transformation)
                && is_array($transformation['field_capabilities'] ?? null)
                    ? $transformation['field_capabilities']
                    : [];
            $baseline['candidate_fields'] = array_keys($fieldCapabilities);
        }
        unset($baseline);

        return $baselines;
    }

    /**
     * @return list<array<string, int|string|null>>
     */
    public function getRecentCandidates(): array
    {
        return $this->candidateRepository->listRecent();
    }

    /**
     * @return list<array<string, int|string|null>>
     */
    public function getRecentHumanJudgments(): array
    {
        return $this->humanJudgmentRepository->listRecent();
    }

    /**
     * @return list<array{snapshot_uuid: string, baseline_uuid: string, candidate_uuid: string, judgment_uuid: string}>
     */
    public function getEligibleExperimentInputs(): array
    {
        $inputs = [];

        foreach ($this->candidateRepository->listRecent() as $candidateRow) {
            try {
                $candidate = $this->candidateRepository->get(
                    (string)$candidateRow['configuration_uuid']
                );
                $baseline = $this->baselineRepository->get($candidate->getParentBaselineUuid());

                foreach ($this->humanJudgmentRepository->listRecent() as $judgmentRow) {
                    $judgment = $this->humanJudgmentRepository->get(
                        (string)$judgmentRow['judgment_uuid']
                    );

                    if ($judgment->getIndexEvidenceUuid() !== $baseline->getIndexEvidenceUuid()) {
                        continue;
                    }

                    $snapshot = $this->snapshotRepository->getApproved($judgment->getSnapshotUuid());

                    if ($snapshot->getStoreId() !== $baseline->getStoreId()) {
                        continue;
                    }

                    $inputs[] = [
                        'snapshot_uuid' => $judgment->getSnapshotUuid(),
                        'baseline_uuid' => $baseline->getConfigurationUuid(),
                        'candidate_uuid' => $candidate->getConfigurationUuid(),
                        'judgment_uuid' => $judgment->getJudgmentUuid(),
                    ];
                }
            } catch (Throwable) {
                continue;
            }
        }

        return $inputs;
    }

    /**
     * @return list<array<string, mixed>>
     */
    public function getRecentExperiments(): array
    {
        $experiments = $this->experimentRepository->listRecent();

        foreach ($experiments as &$experiment) {
            $aggregate = json_decode((string)$experiment['aggregate_result_json'], true);
            $reasons = json_decode((string)$experiment['reason_codes_json'], true);
            $experiment['aggregate'] = is_array($aggregate) ? $aggregate : [];
            $experiment['reason_codes'] = is_array($reasons) ? $reasons : [];
        }
        unset($experiment);

        return $experiments;
    }

    /**
     * @return list<array<string, int|string>>
     */
    public function getRecentProposals(): array
    {
        return $this->proposalRepository->listRecent();
    }

    public function canPreviewQueryData(): bool
    {
        return $this->_authorization->isAllowed(
            'MageOS_OpenSearchRelevanceWorkbench::preview_queries'
        );
    }

    public function canManageSettings(): bool
    {
        return $this->_authorization->isAllowed(
            'MageOS_OpenSearchRelevanceWorkbench::manage_settings'
        );
    }

    public function canApproveSnapshots(): bool
    {
        return $this->_authorization->isAllowed(
            'MageOS_OpenSearchRelevanceWorkbench::approve_snapshots'
        );
    }

    public function canPreviewOwnedResourceCleanup(): bool
    {
        return $this->_authorization->isAllowed(
            'MageOS_OpenSearchRelevanceWorkbench::cleanup_remote_resources'
        );
    }

    public function canApplyLiveConfiguration(): bool
    {
        return $this->_authorization->isAllowed(
            'MageOS_OpenSearchRelevanceWorkbench::apply_live_configuration'
        );
    }

    /**
     * @return list<array{
     *     experiment_uuid: string,
     *     store_id: int,
     *     candidate_uuid: string,
     *     candidate_sha256: string,
     *     index_evidence_sha256: string,
     *     transformation: array{type: string, boosts: array<string, float>}
     * }>
     */
    public function getActivationCandidates(): array
    {
        $candidates = [];

        foreach ($this->experimentRepository->listRecent(100) as $row) {
            if ((string)$row['state'] !== 'ACCEPTED' || (string)$row['eligibility'] !== 'WINNER') {
                continue;
            }

            try {
                $experiment = $this->experimentRepository->getCompleted((string)$row['experiment_uuid']);
                $identities = $experiment->getInputIdentities();
                $candidateUuid = $identities['candidate_configuration_uuid'] ?? null;

                if (!is_string($candidateUuid) || $candidateUuid === '') {
                    continue;
                }

                $candidate = $this->candidateRepository->get($candidateUuid);
                $current = $this->liveActivationRepository->getCurrent($experiment->getStoreId());

                if (
                    $current !== null
                    && $current->getCandidateUuid() === $candidate->getConfigurationUuid()
                    && $current->getCandidateHash() === $candidate->getConfigurationHash()
                    && $current->getIndexEvidenceHash() === (string)($identities['index_evidence_sha256'] ?? '')
                    && $current->getTransformation() === $candidate->getTransformation()
                ) {
                    continue;
                }

                $candidates[] = [
                    'experiment_uuid' => $experiment->getExperimentUuid(),
                    'store_id' => $experiment->getStoreId(),
                    'candidate_uuid' => $candidate->getConfigurationUuid(),
                    'candidate_sha256' => $candidate->getConfigurationHash(),
                    'index_evidence_sha256' => (string)($identities['index_evidence_sha256'] ?? ''),
                    'transformation' => $candidate->getTransformation(),
                ];
            } catch (Throwable) {
                continue;
            }
        }

        return $candidates;
    }

    /**
     * @param array<string, mixed> $preflight
     * @param array<string, mixed> $preview
     * @param list<array<string, mixed>> $liveStates
     * @param list<array<string, mixed>> $activationCandidates
     * @return array{recommended_step: string, states: array<string, string>}
     */
    public function getWorkflowProgress(
        array $preflight,
        array $preview,
        array $liveStates,
        array $activationCandidates
    ): array {
        $approvedSnapshots = array_values(array_filter(
            $this->snapshotRepository->listRecent(100),
            static fn (array $snapshot): bool =>
                (string)$snapshot['status'] === 'APPROVED'
                && (int)$snapshot['selected_count'] >= 5
        ));
        $approvedStores = array_fill_keys(array_map(
            static fn (array $snapshot): int => (int)$snapshot['store_id'],
            $approvedSnapshots
        ), true);
        // Query snapshots are store-scoped demand sets. Their index identity is
        // intentionally bound later, when a judgment is created for a baseline.
        $hasRunnableCandidate = count(array_filter(
            $this->candidateRepository->listRecent(100),
            static fn (array $candidate): bool =>
                (string)$candidate['validation_state'] === 'VALID'
                && isset($approvedStores[(int)$candidate['store_id']])
        )) > 0;
        $eligibleInputs = $this->getEligibleExperimentInputs();
        $hasAcceptedWinner = $this->hasAcceptedWinnerForInputs($eligibleInputs);
        $hasLiveCandidate = count(array_filter(
            $liveStates,
            static fn (array $state): bool => ($state['transformation']['type'] ?? 'STOCK') !== 'STOCK'
        )) > 0;
        $hasDurableProgress = $approvedSnapshots !== []
            || $hasRunnableCandidate
            || $eligibleInputs !== []
            || $hasAcceptedWinner
            || $hasLiveCandidate;
        $preflightBlocked = $preflight !== [] && empty($preflight['human_workflow_ready']);
        $complete = [
            'readiness' => !$preflightBlocked && (
                !empty($preflight['human_workflow_ready'])
                || $preview !== []
                || $hasDurableProgress
            ),
            'snapshot' => $approvedSnapshots !== [],
            'tune' => $hasRunnableCandidate,
            'judge' => $eligibleInputs !== [],
            'compare' => $hasAcceptedWinner || $hasLiveCandidate,
            'activate' => $hasLiveCandidate && $activationCandidates === [],
        ];
        $recommendedStep = 'activate';

        foreach (['readiness', 'snapshot', 'tune', 'judge', 'compare', 'activate'] as $step) {
            if (!$complete[$step]) {
                $recommendedStep = $step;
                break;
            }
        }

        if ($activationCandidates !== []) {
            $complete['activate'] = false;
            $recommendedStep = 'activate';
        }

        $states = [];

        foreach ($complete as $step => $isComplete) {
            $states[$step] = $isComplete ? 'complete' : ($step === $recommendedStep ? 'current' : 'pending');
        }

        return ['recommended_step' => $recommendedStep, 'states' => $states];
    }

    /**
     * @return list<array{
     *     store_id: int,
     *     store_name: string,
     *     activation_uuid: string|null,
     *     candidate_uuid: string|null,
     *     transformation: array{type: string, boosts?: array<string, float>},
     *     index_evidence_sha256: string|null,
     *     target_alias: string|null,
     *     actor_id: int|null,
     *     created_at: string|null
     * }>
     */
    public function getLiveStates(): array
    {
        $states = [];

        foreach ($this->getStoreViews() as $store) {
            $storeId = (int)$store->getId();

            try {
                $activation = $this->liveActivationRepository->getCurrent($storeId);
            } catch (Throwable) {
                $activation = null;
            }

            $states[] = [
                'store_id' => $storeId,
                'store_name' => (string)$store->getName(),
                'activation_uuid' => $activation?->getActivationUuid(),
                'candidate_uuid' => $activation?->getCandidateUuid(),
                'transformation' => $activation?->getTransformation() ?? ['type' => 'STOCK'],
                'index_evidence_sha256' => $activation?->getIndexEvidenceHash(),
                'target_alias' => $activation?->getTargetAlias(),
                'actor_id' => $activation?->getActorId(),
                'created_at' => $activation?->getCreatedAt(),
            ];
        }

        return $states;
    }

    /**
     * @return list<array<string, int|string|null>>
     */
    public function getRecentLiveActivations(): array
    {
        return $this->liveActivationRepository->listRecent();
    }

    /**
     * @return list<array{
     *     local_uuid: string,
     *     remote_id: string,
     *     resource_type: string,
     *     resource_kind: string,
     *     remote_name: string|null,
     *     eligible: bool,
     *     reason_codes: list<string>
     * }>
     */
    public function getOwnedResourceCleanupPreview(): array
    {
        if (!$this->canPreviewOwnedResourceCleanup()) {
            return [];
        }

        return $this->cleanupPreviewService->preview();
    }

    /**
     * @return list<array<string, int|string|null>>
     */
    public function getSnapshotSchedules(): array
    {
        return $this->snapshotScheduleRepository->listRecent();
    }

    /**
     * @return list<array{query_text: string, popularity: int, result_count: int}>
     */
    public function getDraftReviewEntries(string $snapshotUuid): array
    {
        return $this->snapshotRepository->getDraftReviewEntries($snapshotUuid);
    }

    /**
     * @return list<array<string, mixed>>
     */
    public function getRecentExperimentEvidence(): array
    {
        $details = [];

        foreach ($this->experimentRepository->listRecent(3) as $experiment) {
            if (!in_array((string)$experiment['state'], ['LOCAL_EVIDENCE_READY', 'ACCEPTED'], true)) {
                continue;
            }

            try {
                $details[] = $this->experimentEvidenceService->build(
                    (string)$experiment['experiment_uuid']
                );
            } catch (Throwable) {
                $details[] = [
                    'experiment_uuid' => (string)$experiment['experiment_uuid'],
                    'state' => (string)$experiment['state'],
                    'eligibility' => (string)$experiment['eligibility'],
                    'index_state' => 'UNAVAILABLE',
                    'product_context_state' => 'UNAVAILABLE',
                    'queries' => [],
                    'regressions' => [],
                ];
            }
        }

        return $details;
    }

    /**
     * @return list<array<string, int|string|null>>
     */
    public function getEligibleSnapshots(int $storeId): array
    {
        return array_values(array_filter(
            $this->snapshotRepository->listRecent(),
            static fn (array $snapshot): bool =>
                (int)$snapshot['store_id'] === $storeId
                && (string)$snapshot['status'] === 'APPROVED'
                && (int)$snapshot['selected_count'] >= 5
        ));
    }

    public function getDefaultWindowStart(): string
    {
        return gmdate('Y-m-d\T00:00', strtotime('-90 days'));
    }

    public function getDefaultWindowEnd(): string
    {
        return gmdate('Y-m-d\T23:59');
    }

    public function getDefaultScheduleFirstRun(): string
    {
        return gmdate('Y-m-d\T02:00', strtotime('+1 day'));
    }

    /**
     * @param list<array{snapshot_uuid: string, baseline_uuid: string, candidate_uuid: string, judgment_uuid: string}> $inputs
     */
    private function hasAcceptedWinnerForInputs(array $inputs): bool
    {
        $eligible = [];

        foreach ($inputs as $input) {
            $eligible[$this->workflowInputKey(
                $input['snapshot_uuid'],
                $input['baseline_uuid'],
                $input['candidate_uuid'],
                $input['judgment_uuid']
            )] = true;
        }

        if ($eligible === []) {
            return false;
        }

        foreach ($this->experimentRepository->listRecent(100) as $row) {
            if ((string)$row['state'] !== 'ACCEPTED' || (string)$row['eligibility'] !== 'WINNER') {
                continue;
            }

            try {
                $identities = $this->experimentRepository
                    ->getCompleted((string)$row['experiment_uuid'])
                    ->getInputIdentities();
                $key = $this->workflowInputKey(
                    (string)($identities['query_snapshot_id'] ?? ''),
                    (string)($identities['baseline_configuration_uuid'] ?? ''),
                    (string)($identities['candidate_configuration_uuid'] ?? ''),
                    (string)($identities['judgment_uuid'] ?? '')
                );

                if (isset($eligible[$key])) {
                    return true;
                }
            } catch (Throwable) {
                continue;
            }
        }

        return false;
    }

    private function workflowInputKey(
        string $snapshotUuid,
        string $baselineUuid,
        string $candidateUuid,
        string $judgmentUuid
    ): string {
        return strtolower(implode(':', [$snapshotUuid, $baselineUuid, $candidateUuid, $judgmentUuid]));
    }
}
