<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Experiment;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Api\IndexEvidenceCaptureInterface;
use MageOS\OpenSearchRelevanceWorkbench\Api\SearchRelevanceClientInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\BoundedTemplateSearch;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\PersistedBaselineConfiguration;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\PersistedCandidateConfiguration;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\PersistedHumanJudgment;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\CandidateConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\HumanJudgmentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\RemoteArtifactRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\ApprovedQuerySnapshot;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\QuerySetContentIdentityFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\OwnedResourceNameFactory;
use RuntimeException;
use UnexpectedValueException;

class HumanExperimentRunService
{
    private const RESULT_DEPTH = 10;
    private const MINIMUM_JUDGED_COVERAGE = 1.0;
    private const MINIMUM_IMPROVEMENT = 0.01;
    private const POLL_ATTEMPTS = 100;
    private const POLL_DELAY_MICROSECONDS = 100_000;

    public function __construct(
        private readonly QuerySnapshotRepository $snapshotRepository,
        private readonly BaselineConfigurationRepository $baselineRepository,
        private readonly CandidateConfigurationRepository $candidateRepository,
        private readonly HumanJudgmentRepository $judgmentRepository,
        private readonly RemoteArtifactRepository $remoteArtifactRepository,
        private readonly ExperimentRepository $experimentRepository,
        private readonly SearchRelevanceClientInterface $searchRelevanceClient,
        private readonly IndexEvidenceCaptureInterface $indexEvidenceCapture,
        private readonly HumanExperimentPlanFactory $planFactory,
        private readonly BoundedTemplateSearch $boundedSearch,
        private readonly OfflineEvidenceEvaluator $evidenceEvaluator,
        private readonly QuerySetContentIdentityFactory $querySetContentIdentityFactory,
        private readonly OwnedResourceNameFactory $ownedResourceNameFactory,
        private readonly CanonicalJson $canonicalJson
    ) {
    }

    public function run(
        string $snapshotUuid,
        string $baselineUuid,
        string $candidateUuid,
        string $judgmentUuid,
        int $actorId,
        string $requestedAt,
        string $correlationId
    ): PersistedExperiment {
        if ($actorId < 1) {
            throw new InvalidArgumentException('Experiment execution requires an admin actor');
        }

        $snapshot = $this->snapshotRepository->getApproved($snapshotUuid);
        $baseline = $this->baselineRepository->get($baselineUuid);
        $candidate = $this->candidateRepository->get($candidateUuid);
        $judgment = $this->judgmentRepository->get($judgmentUuid);
        $this->assertCompatibleInputs(
            $snapshotUuid,
            $snapshot,
            $baseline,
            $candidate,
            $judgment
        );
        $beforeEvidence = $this->indexEvidenceCapture->capture($baseline->getTargetAlias());

        if (!hash_equals($baseline->getIndexEvidenceHash(), $beforeEvidence->getEvidenceHash())) {
            throw new RuntimeException('Experiment cannot start because the baseline index evidence is stale');
        }

        $remoteQuerySetId = $this->materializeQuerySet(
            $snapshotUuid,
            $snapshot,
            $actorId,
            $requestedAt,
            $correlationId
        );
        $baselineRemoteId = $this->materializeSearchConfiguration(
            $baseline->getConfigurationUuid(),
            'baseline',
            $baseline,
            $baseline->getTemplate()->getTemplate()['body'],
            $actorId,
            $requestedAt,
            $correlationId
        );
        $candidateRemoteId = $this->materializeSearchConfiguration(
            $candidate->getConfigurationUuid(),
            'candidate',
            $baseline,
            $candidate->getTemplate()->getTemplate()['body'],
            $actorId,
            $requestedAt,
            $correlationId
        );
        $remoteJudgmentId = $this->materializeJudgment(
            $judgment,
            $actorId,
            $requestedAt,
            $correlationId
        );
        $plan = $this->planFactory->create(
            $snapshotUuid,
            $snapshot->getSnapshotHash(),
            $remoteQuerySetId,
            $baselineRemoteId,
            $baseline->getConfigurationHash(),
            $candidateRemoteId,
            $candidate->getConfigurationHash(),
            $remoteJudgmentId,
            $judgment->getJudgmentHash(),
            $baseline->getIndexEvidenceHash(),
            self::RESULT_DEPTH,
            self::MINIMUM_JUDGED_COVERAGE,
            'NDCG@10',
            self::MINIMUM_IMPROVEMENT,
            $baseline->getConfigurationUuid(),
            $candidate->getConfigurationUuid(),
            $judgment->getJudgmentUuid()
        );
        $experimentUuid = $this->experimentRepository->createOrGet(
            $plan,
            $baseline->getStoreId(),
            $actorId,
            $requestedAt,
            $correlationId
        );
        $remoteExperimentIds = $this->runRemoteExperiments(
            $experimentUuid,
            $plan,
            $actorId,
            $requestedAt,
            $correlationId
        );
        [$baselineRankings, $candidateRankings, $ratings, $queryHashes] = $this->buildEvidenceInputs(
            $snapshot,
            $baseline,
            $candidate,
            $judgment
        );
        $afterEvidence = $this->indexEvidenceCapture->capture($baseline->getTargetAlias());
        $indexFresh = hash_equals($beforeEvidence->getEvidenceHash(), $afterEvidence->getEvidenceHash())
            && hash_equals($baseline->getIndexEvidenceHash(), $afterEvidence->getEvidenceHash());
        $evidence = $this->evidenceEvaluator->evaluate(
            $baselineRankings,
            $candidateRankings,
            $ratings,
            self::RESULT_DEPTH,
            self::MINIMUM_JUDGED_COVERAGE,
            self::MINIMUM_IMPROVEMENT,
            $queryHashes,
            $indexFresh,
            false
        );
        $this->experimentRepository->complete(
            $experimentUuid,
            $evidence,
            $remoteExperimentIds,
            $actorId,
            $requestedAt,
            $correlationId
        );

        return $this->experimentRepository->getCompleted($experimentUuid);
    }

    private function materializeQuerySet(
        string $snapshotUuid,
        ApprovedQuerySnapshot $snapshot,
        int $actorId,
        string $requestedAt,
        string $correlationId
    ): string {
        $remoteId = $this->remoteArtifactRepository->getQuerySetId($snapshotUuid);
        $payload = [
            'name' => $this->ownedResourceNameFactory->create('query-set', $snapshotUuid),
            'description' => 'Owned MageOS relevance workbench query snapshot',
            'sampling' => 'manual',
            'querySetQueries' => $snapshot->getRemoteQuerySetEntries(),
        ];

        if ($remoteId === null) {
            $response = $this->searchRelevanceClient->createQuerySet($payload);
            $remoteId = $this->extractUuid($response, 'query_set_id');
            $this->remoteArtifactRepository->bindQuerySetId(
                $snapshotUuid,
                $remoteId,
                $actorId,
                $requestedAt,
                $correlationId
            );
        }

        $source = $this->readSource($this->searchRelevanceClient->getQuerySet($remoteId), $remoteId);
        $remotePayload = [
            'description' => $source['description'] ?? null,
            'sampling' => $source['sampling'] ?? null,
            'querySetQueries' => $source['querySetQueries'] ?? null,
        ];

        if (
            ($source['name'] ?? null) !== $payload['name']
            || !hash_equals(
                $this->querySetContentIdentityFactory->hash($payload),
                $this->querySetContentIdentityFactory->hash($remotePayload)
            )
        ) {
            throw new RuntimeException('Bound remote query set no longer matches the approved snapshot');
        }

        return $remoteId;
    }

    /**
     * @param array<string, mixed> $body
     */
    private function materializeSearchConfiguration(
        string $configurationUuid,
        string $kind,
        PersistedBaselineConfiguration $baseline,
        array $body,
        int $actorId,
        string $requestedAt,
        string $correlationId
    ): string {
        $remoteId = $this->remoteArtifactRepository->getSearchConfigurationId($configurationUuid);
        $payload = [
            'name' => $this->ownedResourceNameFactory->create($kind, $configurationUuid),
            'description' => 'Owned MageOS relevance workbench ' . $kind . ' configuration',
            'index' => $baseline->getPhysicalIndex(),
            'query' => $this->canonicalJson->encode($body),
            'searchPipeline' => $baseline->getPipelineIdentity(),
        ];

        if ($remoteId === null) {
            $response = $this->searchRelevanceClient->createSearchConfiguration($payload);
            $remoteId = $this->extractUuid($response, 'search_configuration_id');
            $this->remoteArtifactRepository->bindSearchConfigurationId(
                $configurationUuid,
                $remoteId,
                $actorId,
                $requestedAt,
                $correlationId
            );
        }

        $source = $this->readSource(
            $this->searchRelevanceClient->getSearchConfiguration($remoteId),
            $remoteId
        );

        foreach (['name', 'index', 'query', 'searchPipeline'] as $field) {
            if (($source[$field] ?? null) !== $payload[$field]) {
                throw new RuntimeException('Bound remote search configuration no longer matches local evidence');
            }
        }

        return $remoteId;
    }

    private function materializeJudgment(
        PersistedHumanJudgment $judgment,
        int $actorId,
        string $requestedAt,
        string $correlationId
    ): string {
        $remoteId = $this->remoteArtifactRepository->getJudgmentId($judgment->getJudgmentUuid());
        $payload = [
            'name' => $this->ownedResourceNameFactory->create('human', $judgment->getJudgmentUuid()),
            'description' => 'Owned MageOS relevance workbench merchant ratings',
            'type' => 'IMPORT_JUDGMENT',
            'judgmentRatings' => $judgment->toJudgmentSet()->getRemoteJudgmentRatings(),
        ];

        if ($remoteId === null) {
            $response = $this->searchRelevanceClient->createJudgment($payload);
            $remoteId = $this->extractUuid($response, 'judgment_id');
            $this->remoteArtifactRepository->bindJudgmentId(
                $judgment->getJudgmentUuid(),
                $remoteId,
                $actorId,
                $requestedAt,
                $correlationId
            );
        }

        $source = $this->pollCompleted(
            fn (): array => $this->searchRelevanceClient->getJudgment($remoteId)
        );
        $remoteIdentity = [
            'type' => $source['type'] ?? null,
            'judgmentRatings' => $source['judgmentRatings'] ?? null,
        ];
        $expectedIdentity = [
            'type' => $payload['type'],
            'judgmentRatings' => $payload['judgmentRatings'],
        ];

        if (
            ($source['name'] ?? null) !== $payload['name']
            || !hash_equals(
                $this->canonicalJson->hash($expectedIdentity),
                $this->canonicalJson->hash($remoteIdentity)
            )
        ) {
            throw new RuntimeException('Bound remote judgment no longer matches reviewed human ratings');
        }

        $this->remoteArtifactRepository->markJudgmentCompleted($judgment->getJudgmentUuid(), $remoteId);

        return $remoteId;
    }

    /**
     * @return array<string, string>
     */
    private function runRemoteExperiments(
        string $experimentUuid,
        HumanExperimentPlan $plan,
        int $actorId,
        string $requestedAt,
        string $correlationId
    ): array {
        $remoteIds = $this->experimentRepository->getRemoteExperimentIds($experimentUuid);

        foreach ($plan->getRemotePayloads() as $kind => $payload) {
            $remoteId = $remoteIds[$kind] ?? null;

            if ($remoteId === null) {
                $response = $this->searchRelevanceClient->createExperiment([
                    'name' => $this->ownedResourceNameFactory->create(strtolower($kind), $experimentUuid),
                    'description' => 'Owned MageOS relevance workbench offline experiment',
                ] + $payload);
                $remoteId = $this->extractUuid($response, 'experiment_id');
                $this->experimentRepository->bindRemoteExperimentId(
                    $experimentUuid,
                    $kind,
                    $remoteId,
                    $actorId,
                    $requestedAt,
                    $correlationId
                );
                $remoteIds[$kind] = $remoteId;
            }

            $source = $this->pollCompleted(
                fn (): array => $this->searchRelevanceClient->getExperiment($remoteId)
            );

            foreach ($payload as $field => $value) {
                if (($source[$field] ?? null) !== $value) {
                    throw new RuntimeException('Bound remote experiment no longer matches the frozen plan');
                }
            }

            if (($source['results'] ?? []) === []) {
                throw new UnexpectedValueException('Completed remote experiment contains no results');
            }

            $validation = $this->searchRelevanceClient->validateExperiment($remoteId);

            if (($validation['status'] ?? null) !== 'VALID') {
                throw new RuntimeException('Remote experiment validation detected input drift');
            }
        }

        ksort($remoteIds, SORT_STRING);

        return $remoteIds;
    }

    /**
     * @return array{
     *     array<string, list<string>>,
     *     array<string, list<string>>,
     *     array<string, array<string, float>>,
     *     list<string>
     * }
     */
    private function buildEvidenceInputs(
        ApprovedQuerySnapshot $snapshot,
        PersistedBaselineConfiguration $baseline,
        PersistedCandidateConfiguration $candidate,
        PersistedHumanJudgment $judgment
    ): array {
        $entries = [];

        foreach ($snapshot->getEntries() as $entry) {
            $entries[$entry->getQueryHash()] = $entry;
        }

        $ratings = [];

        foreach ($judgment->getRatings() as $rating) {
            if (!isset($entries[$rating['query_hash']])) {
                throw new UnexpectedValueException('Human judgment references a query outside the snapshot');
            }

            $ratings[$rating['query_hash']][$rating['document_id']] = $rating['rating'];
        }

        $queryHashes = array_keys($ratings);
        sort($queryHashes, SORT_STRING);
        $baselineRankings = [];
        $candidateRankings = [];

        foreach ($queryHashes as $queryHash) {
            $entry = $entries[$queryHash];
            $baselineResult = $this->boundedSearch->execute(
                $baseline->getTemplate(),
                $entry->getQueryText(),
                $baseline->getPhysicalIndex(),
                self::RESULT_DEPTH
            );
            $candidateResult = $this->boundedSearch->execute(
                $candidate->getTemplate(),
                $entry->getQueryText(),
                $candidate->getPhysicalIndex(),
                self::RESULT_DEPTH
            );
            $baselineRankings[$queryHash] = array_map(
                static fn (array $hit): string => $hit['document_id'],
                $baselineResult['hits']
            );
            $candidateRankings[$queryHash] = array_map(
                static fn (array $hit): string => $hit['document_id'],
                $candidateResult['hits']
            );
        }

        return [$baselineRankings, $candidateRankings, $ratings, $queryHashes];
    }

    private function assertCompatibleInputs(
        string $snapshotUuid,
        ApprovedQuerySnapshot $snapshot,
        PersistedBaselineConfiguration $baseline,
        PersistedCandidateConfiguration $candidate,
        PersistedHumanJudgment $judgment
    ): void {
        if (
            $snapshot->getStoreId() !== $baseline->getStoreId()
            || $candidate->getStoreId() !== $baseline->getStoreId()
            || $candidate->getParentBaselineUuid() !== $baseline->getConfigurationUuid()
            || $candidate->getIndexEvidenceUuid() !== $baseline->getIndexEvidenceUuid()
            || $candidate->getPhysicalIndex() !== $baseline->getPhysicalIndex()
            || $judgment->getSnapshotUuid() !== strtolower($snapshotUuid)
            || $judgment->getSnapshotHash() !== $snapshot->getSnapshotHash()
            || $judgment->getIndexEvidenceUuid() !== $baseline->getIndexEvidenceUuid()
            || $judgment->getIndexEvidenceHash() !== $baseline->getIndexEvidenceHash()
        ) {
            throw new InvalidArgumentException('Experiment inputs do not share one frozen store, snapshot, and index');
        }
    }

    /**
     * @param array<string, mixed> $response
     */
    private function extractUuid(array $response, string $field): string
    {
        $value = $response[$field] ?? null;

        if (
            !is_string($value)
            || preg_match('/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/iD', $value) !== 1
        ) {
            throw new UnexpectedValueException('Search Relevance create response contains no resource UUID');
        }

        return strtolower($value);
    }

    /**
     * @param array<string, mixed> $response
     * @return array<string, mixed>
     */
    private function readSource(array $response, string $expectedId): array
    {
        $hit = $response['hits']['hits'][0] ?? null;

        if (!is_array($hit) || ($hit['_id'] ?? null) !== $expectedId || !is_array($hit['_source'] ?? null)) {
            throw new UnexpectedValueException('Search Relevance resource read returned no exact owned resource');
        }

        return $hit['_source'];
    }

    /**
     * @param callable(): array<string, mixed> $readResource
     * @return array<string, mixed>
     */
    private function pollCompleted(callable $readResource): array
    {
        $lastStatus = 'UNAVAILABLE';

        for ($attempt = 0; $attempt < self::POLL_ATTEMPTS; $attempt++) {
            $response = $readResource();
            $hit = $response['hits']['hits'][0] ?? null;
            $source = is_array($hit) ? ($hit['_source'] ?? null) : null;

            if (is_array($source)) {
                $status = $source['status'] ?? null;
                $lastStatus = is_string($status) ? $status : 'UNAVAILABLE';

                if ($lastStatus === 'COMPLETED') {
                    return $source;
                }

                if (in_array($lastStatus, ['ERROR', 'TIMEOUT'], true)) {
                    throw new RuntimeException('Remote resource entered terminal status ' . $lastStatus);
                }
            }

            usleep(self::POLL_DELAY_MICROSECONDS);
        }

        throw new RuntimeException('Remote resource did not complete; last status was ' . $lastStatus);
    }

}
