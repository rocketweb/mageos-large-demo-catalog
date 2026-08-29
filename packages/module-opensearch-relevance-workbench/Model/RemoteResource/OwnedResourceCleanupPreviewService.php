<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource;

use MageOS\OpenSearchRelevanceWorkbench\Api\SearchRelevanceClientInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\PersistedBaselineConfiguration;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\CandidateConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\HumanJudgmentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\RemoteArtifactRepository;
use Throwable;
use UnexpectedValueException;

class OwnedResourceCleanupPreviewService
{
    public function __construct(
        private readonly RemoteArtifactRepository $remoteArtifactRepository,
        private readonly QuerySnapshotRepository $snapshotRepository,
        private readonly BaselineConfigurationRepository $baselineRepository,
        private readonly CandidateConfigurationRepository $candidateRepository,
        private readonly HumanJudgmentRepository $judgmentRepository,
        private readonly ExperimentRepository $experimentRepository,
        private readonly SearchRelevanceClientInterface $searchRelevanceClient,
        private readonly QuerySetContentIdentityFactory $querySetIdentityFactory,
        private readonly OwnedResourceNameFactory $nameFactory,
        private readonly CanonicalJson $canonicalJson,
        private readonly OwnedResourceCleanupGuard $cleanupGuard
    ) {
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
    public function preview(int $limit = 20): array
    {
        $preview = [];

        foreach ($this->remoteArtifactRepository->listBoundResources($limit) as $binding) {
            try {
                $preview[] = $this->previewBinding($binding);
            } catch (Throwable) {
                $preview[] = $this->row($binding, null, false, ['REMOTE_READ_FAILED']);
            }
        }

        return $preview;
    }

    /**
     * @param array{local_uuid: string, remote_id: string, resource_type: string, resource_kind: string} $binding
     * @return array{
     *     local_uuid: string,
     *     remote_id: string,
     *     resource_type: string,
     *     resource_kind: string,
     *     remote_name: string|null,
     *     eligible: bool,
     *     reason_codes: list<string>
     * }
     */
    private function previewBinding(array $binding): array
    {
        return match ($binding['resource_type']) {
            'QUERY_SET' => $this->previewQuerySet($binding),
            'SEARCH_CONFIGURATION' => $this->previewSearchConfiguration($binding),
            'JUDGMENT' => $this->previewJudgment($binding),
            'EXPERIMENT' => $this->previewExperiment($binding),
            default => $this->row($binding, null, false, ['UNSUPPORTED_RESOURCE_TYPE']),
        };
    }

    /**
     * @param array{local_uuid: string, remote_id: string, resource_type: string, resource_kind: string} $binding
     * @return array{
     *     local_uuid: string,
     *     remote_id: string,
     *     resource_type: string,
     *     resource_kind: string,
     *     remote_name: string|null,
     *     eligible: bool,
     *     reason_codes: list<string>
     * }
     */
    private function previewQuerySet(array $binding): array
    {
        $snapshot = $this->snapshotRepository->getApproved($binding['local_uuid']);
        $expected = [
            'description' => 'Owned MageOS relevance workbench query snapshot',
            'sampling' => 'manual',
            'querySetQueries' => $snapshot->getRemoteQuerySetEntries(),
        ];
        $source = $this->readSource(
            $this->searchRelevanceClient->getQuerySet($binding['remote_id']),
            $binding['remote_id']
        );
        $remote = [
            'description' => $source['description'] ?? null,
            'sampling' => $source['sampling'] ?? null,
            'querySetQueries' => $source['querySetQueries'] ?? null,
        ];

        return $this->decide(
            $binding,
            $this->nameFactory->create('query-set', $binding['local_uuid']),
            $this->querySetIdentityFactory->hash($expected),
            $source,
            $this->querySetIdentityFactory->hash($remote)
        );
    }

    /**
     * @param array{local_uuid: string, remote_id: string, resource_type: string, resource_kind: string} $binding
     * @return array{
     *     local_uuid: string,
     *     remote_id: string,
     *     resource_type: string,
     *     resource_kind: string,
     *     remote_name: string|null,
     *     eligible: bool,
     *     reason_codes: list<string>
     * }
     */
    private function previewSearchConfiguration(array $binding): array
    {
        if ($binding['resource_kind'] === 'baseline') {
            $configuration = $this->baselineRepository->get($binding['local_uuid']);
            $baseline = $configuration;
        } elseif ($binding['resource_kind'] === 'candidate') {
            $configuration = $this->candidateRepository->get($binding['local_uuid']);
            $baseline = $this->baselineRepository->get($configuration->getParentBaselineUuid());
        } else {
            throw new UnexpectedValueException('Bound search configuration kind is unsupported');
        }

        $expected = $this->configurationContent(
            $configuration->getTemplate()->getTemplate()['body'],
            $baseline,
            $binding['resource_kind']
        );
        $source = $this->readSource(
            $this->searchRelevanceClient->getSearchConfiguration($binding['remote_id']),
            $binding['remote_id']
        );

        return $this->decide(
            $binding,
            $this->nameFactory->create($binding['resource_kind'], $binding['local_uuid']),
            $this->canonicalJson->hash($expected),
            $source,
            $this->canonicalJson->hash($this->selectFields($source, array_keys($expected)))
        );
    }

    /**
     * @param array{local_uuid: string, remote_id: string, resource_type: string, resource_kind: string} $binding
     * @return array{
     *     local_uuid: string,
     *     remote_id: string,
     *     resource_type: string,
     *     resource_kind: string,
     *     remote_name: string|null,
     *     eligible: bool,
     *     reason_codes: list<string>
     * }
     */
    private function previewJudgment(array $binding): array
    {
        $judgment = $this->judgmentRepository->get($binding['local_uuid']);
        $expected = [
            'type' => 'IMPORT_JUDGMENT',
            'judgmentRatings' => $judgment->toJudgmentSet()->getRemoteJudgmentRatings(),
        ];
        $source = $this->readSource(
            $this->searchRelevanceClient->getJudgment($binding['remote_id']),
            $binding['remote_id']
        );

        return $this->decide(
            $binding,
            $this->nameFactory->create('human', $binding['local_uuid']),
            $this->canonicalJson->hash($expected),
            $source,
            $this->canonicalJson->hash($this->selectFields($source, array_keys($expected)))
        );
    }

    /**
     * @param array{local_uuid: string, remote_id: string, resource_type: string, resource_kind: string} $binding
     * @return array{
     *     local_uuid: string,
     *     remote_id: string,
     *     resource_type: string,
     *     resource_kind: string,
     *     remote_name: string|null,
     *     eligible: bool,
     *     reason_codes: list<string>
     * }
     */
    private function previewExperiment(array $binding): array
    {
        $experiment = $this->experimentRepository->getCompleted($binding['local_uuid']);
        $identities = $experiment->getInputIdentities();
        $kind = $binding['resource_kind'];
        $payload = match ($kind) {
            'PAIRWISE_COMPARISON' => [
                'querySetId' => $this->identity($identities, 'remote_query_set_id'),
                'searchConfigurationList' => [
                    $this->identity($identities, 'baseline_remote_configuration_id'),
                    $this->identity($identities, 'candidate_remote_configuration_id'),
                ],
                'size' => $this->integerIdentity($identities, 'result_depth'),
                'type' => 'PAIRWISE_COMPARISON',
            ],
            'POINTWISE_BASELINE' => $this->pointwisePayload($identities, 'baseline_remote_configuration_id'),
            'POINTWISE_CANDIDATE' => $this->pointwisePayload($identities, 'candidate_remote_configuration_id'),
            default => throw new UnexpectedValueException('Bound experiment kind is unsupported'),
        };
        $expected = ['description' => 'Owned MageOS relevance workbench offline experiment'] + $payload;
        $source = $this->readSource(
            $this->searchRelevanceClient->getExperiment($binding['remote_id']),
            $binding['remote_id']
        );

        return $this->decide(
            $binding,
            $this->nameFactory->create(strtolower($kind), $binding['local_uuid']),
            $this->canonicalJson->hash($expected),
            $source,
            $this->canonicalJson->hash($this->selectFields($source, array_keys($expected)))
        );
    }

    /**
     * @param array<string, mixed> $body
     * @return array{description: string, index: string, query: string, searchPipeline: string}
     */
    private function configurationContent(
        array $body,
        PersistedBaselineConfiguration $baseline,
        string $kind
    ): array
    {
        return [
            'description' => 'Owned MageOS relevance workbench ' . $kind . ' configuration',
            'index' => $baseline->getPhysicalIndex(),
            'query' => $this->canonicalJson->encode($body),
            'searchPipeline' => $baseline->getPipelineIdentity(),
        ];
    }

    /**
     * @param array<string, float|int|string> $identities
     * @return array<string, int|string|list<string>>
     */
    private function pointwisePayload(array $identities, string $configurationKey): array
    {
        return [
            'querySetId' => $this->identity($identities, 'remote_query_set_id'),
            'searchConfigurationList' => [$this->identity($identities, $configurationKey)],
            'judgmentList' => [$this->identity($identities, 'remote_judgment_id')],
            'size' => $this->integerIdentity($identities, 'result_depth'),
            'type' => 'POINTWISE_EVALUATION',
        ];
    }

    /**
     * @param array<string, float|int|string> $identities
     */
    private function identity(array $identities, string $key): string
    {
        $value = $identities[$key] ?? null;

        if (!is_string($value) || $value === '') {
            throw new UnexpectedValueException('Experiment cleanup identity is missing: ' . $key);
        }

        return $value;
    }

    /**
     * @param array<string, float|int|string> $identities
     */
    private function integerIdentity(array $identities, string $key): int
    {
        $value = $identities[$key] ?? null;

        if (!is_int($value)) {
            throw new UnexpectedValueException('Experiment cleanup integer identity is missing: ' . $key);
        }

        return $value;
    }

    /**
     * @param array<string, mixed> $response
     * @return array<string, mixed>
     */
    private function readSource(array $response, string $expectedId): array
    {
        $hit = $response['hits']['hits'][0] ?? null;

        if (!is_array($hit) || ($hit['_id'] ?? null) !== $expectedId || !is_array($hit['_source'] ?? null)) {
            throw new UnexpectedValueException('Cleanup preview found no exact bound remote resource');
        }

        return $hit['_source'];
    }

    /**
     * @param array<string, mixed> $source
     * @param list<string> $fields
     * @return array<string, mixed>
     */
    private function selectFields(array $source, array $fields): array
    {
        $selected = [];

        foreach ($fields as $field) {
            $selected[$field] = $source[$field] ?? null;
        }

        return $selected;
    }

    /**
     * @param array{local_uuid: string, remote_id: string, resource_type: string, resource_kind: string} $binding
     * @param array<string, mixed> $source
     * @return array{
     *     local_uuid: string,
     *     remote_id: string,
     *     resource_type: string,
     *     resource_kind: string,
     *     remote_name: string|null,
     *     eligible: bool,
     *     reason_codes: list<string>
     * }
     */
    private function decide(
        array $binding,
        string $expectedName,
        string $expectedHash,
        array $source,
        string $remoteHash
    ): array {
        $remoteName = $source['name'] ?? null;

        if (!is_string($remoteName) || $remoteName === '') {
            return $this->row($binding, null, false, ['REMOTE_NAME_MISSING']);
        }

        $decision = $this->cleanupGuard->preview(
            new OwnedResourceIdentity(
                $binding['remote_id'],
                $binding['resource_type'],
                $expectedName,
                $expectedHash
            ),
            new RemoteResourceSnapshot(
                $binding['remote_id'],
                $binding['resource_type'],
                $remoteName,
                $remoteHash
            )
        );

        return $this->row(
            $binding,
            $remoteName,
            $decision->isEligible(),
            $decision->getReasonCodes()
        );
    }

    /**
     * @param array{local_uuid: string, remote_id: string, resource_type: string, resource_kind: string} $binding
     * @param list<string> $reasonCodes
     * @return array{
     *     local_uuid: string,
     *     remote_id: string,
     *     resource_type: string,
     *     resource_kind: string,
     *     remote_name: string|null,
     *     eligible: bool,
     *     reason_codes: list<string>
     * }
     */
    private function row(array $binding, ?string $remoteName, bool $eligible, array $reasonCodes): array
    {
        return $binding + [
            'remote_name' => $remoteName,
            'eligible' => $eligible,
            'reason_codes' => $reasonCodes,
        ];
    }
}
