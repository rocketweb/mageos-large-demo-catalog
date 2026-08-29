<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Integration\OpenSearch;

use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\FieldBoostCompiler;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\HumanExperimentPlanFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\OfflineEvidenceEvaluator;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\HumanJudgmentSetFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\CapabilityDetector;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\ConfiguredOpenSearchClientProvider;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\IndexEvidenceCapture;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\SearchRelevanceClient;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\SearchRelevanceRequestFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\SearchRelevanceTransportException;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\UuidGenerator;
use MageOS\OpenSearchRelevanceWorkbench\Model\Proposal\ProposalExporter;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\PrivacyDetector;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\QuerySnapshotPreviewer;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPolicy;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\OwnedResourceCleanupGuard;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\OwnedResourceIdentity;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\QuerySetContentIdentityFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\RemoteResourceSnapshot;
use OpenSearch\Client;
use OpenSearch\ClientBuilder;
use PHPUnit\Framework\TestCase;

class SearchRelevanceContractTest extends TestCase
{
    private ConfiguredOpenSearchClientProvider $clientProvider;
    private Client $openSearchClient;
    private SearchRelevanceClient $searchRelevanceClient;

    protected function setUp(): void
    {
        $openSearchUrl = getenv('OSRW_OPENSEARCH_URL');

        if ($openSearchUrl === false || $openSearchUrl === '') {
            self::markTestSkipped('Set OSRW_OPENSEARCH_URL to run OpenSearch integration tests.');
        }

        $this->openSearchClient = ClientBuilder::create()
            ->setHosts([$openSearchUrl])
            ->build();

        $this->clientProvider = $this->createStub(ConfiguredOpenSearchClientProvider::class);
        $this->clientProvider
            ->method('get')
            ->willReturn($this->openSearchClient);

        $this->searchRelevanceClient = new SearchRelevanceClient(
            $this->clientProvider,
            new SearchRelevanceRequestFactory()
        );
    }

    public function testPinnedClusterHasRequiredWorkbenchCapabilities(): void
    {
        $clusterInfo = $this->openSearchClient->info();
        $plugins = $this->openSearchClient->cat()->plugins(['format' => 'json']);
        $pluginVersions = [];

        foreach ($plugins as $plugin) {
            $component = $plugin['component'] ?? null;
            $version = $plugin['version'] ?? null;

            if (is_string($component) && is_string($version)) {
                $pluginVersions[$component] = $version;
            }
        }

        $workbenchStats = $this->searchRelevanceClient->stats();
        $report = (new CapabilityDetector())->detect(
            (string)($clusterInfo['version']['number'] ?? ''),
            array_keys($pluginVersions),
            $workbenchStats !== []
        );

        self::assertSame('3.8.0', $clusterInfo['version']['number'] ?? null);
        self::assertSame('3.8.0.0', $pluginVersions['opensearch-search-relevance'] ?? null);
        self::assertSame('3.8.0.0', $pluginVersions['opensearch-ml'] ?? null);
        self::assertTrue($report->isCoreReady());
        self::assertTrue($report->isLlmReady());
        self::assertSame([], $report->getReasonCodes());
    }

    public function testOwnedQuerySetCreateReadSearchAndDeleteLifecycle(): void
    {
        $name = 'osrw-it-' . bin2hex(random_bytes(6));
        $created = $this->searchRelevanceClient->createQuerySet([
            'name' => $name,
            'description' => 'Disposable module integration fixture',
            'sampling' => 'manual',
            'querySetQueries' => [
                ['queryText' => 'winter boots'],
                ['queryText' => 'red running shoes'],
            ],
        ]);
        $querySetId = $created['query_set_id'] ?? null;

        self::assertIsString($querySetId);
        self::assertMatchesRegularExpression(
            '/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/',
            $querySetId
        );

        try {
            $retrieved = $this->searchRelevanceClient->getQuerySet($querySetId);
            $searched = $this->searchRelevanceClient->searchQuerySets([
                'size' => 100,
                'query' => ['match_all' => new \stdClass()],
            ]);

            self::assertSame($querySetId, $retrieved['hits']['hits'][0]['_id'] ?? null);
            self::assertSame($name, $retrieved['hits']['hits'][0]['_source']['name'] ?? null);

            $searchedIds = array_column($searched['hits']['hits'] ?? [], '_id');
            self::assertContains($querySetId, $searchedIds);
        } finally {
            $deleted = $this->searchRelevanceClient->deleteQuerySet($querySetId);
        }

        self::assertSame('deleted', $deleted['result'] ?? null);
    }

    public function testOwnedResourceCleanupDryRunRequiresExactRemoteIdentity(): void
    {
        $canonicalJson = new CanonicalJson();
        $content = [
            'description' => 'Disposable owned-resource cleanup fixture',
            'sampling' => 'manual',
            'querySetQueries' => [['queryText' => 'winter boots']],
        ];
        $contentIdentityFactory = new QuerySetContentIdentityFactory($canonicalJson);
        $contentHash = $contentIdentityFactory->hash($content);
        $name = 'osrw-store-1-query-set-' . substr($contentHash, 0, 16);
        $created = $this->searchRelevanceClient->createQuerySet(['name' => $name] + $content);
        $querySetId = $created['query_set_id'] ?? null;
        self::assertIsString($querySetId);

        try {
            $retrieved = $this->searchRelevanceClient->getQuerySet($querySetId);
            $source = $retrieved['hits']['hits'][0]['_source'] ?? null;
            self::assertIsArray($source);
            $remoteContent = [
                'description' => $source['description'] ?? null,
                'sampling' => $source['sampling'] ?? null,
                'querySetQueries' => $source['querySetQueries'] ?? null,
            ];
            $ownership = new OwnedResourceIdentity($querySetId, 'QUERY_SET', $name, $contentHash);
            $remote = new RemoteResourceSnapshot(
                $querySetId,
                'QUERY_SET',
                (string)($source['name'] ?? ''),
                $contentIdentityFactory->hash($remoteContent)
            );
            $guard = new OwnedResourceCleanupGuard();
            $eligible = $guard->preview($ownership, $remote);

            self::assertTrue($eligible->isEligible(), implode(', ', $eligible->getReasonCodes()));
            self::assertSame([], $eligible->getReasonCodes());

            $changed = $guard->preview(
                $ownership,
                new RemoteResourceSnapshot(
                    $querySetId,
                    'QUERY_SET',
                    $name,
                    str_repeat('b', 64)
                )
            );
            self::assertFalse($changed->isEligible());
            self::assertSame(['CONTENT_HASH_MISMATCH'], $changed->getReasonCodes());

            $deleted = $this->searchRelevanceClient->deleteQuerySet($eligible->getRemoteId());
            self::assertSame('deleted', $deleted['result'] ?? null);
            $querySetId = null;
        } finally {
            if (is_string($querySetId)) {
                $this->searchRelevanceClient->deleteQuerySet($querySetId);
            }
        }
    }

    public function testMustacheSearchConfigurationRoundTripsAgainstCatalogLikeIndex(): void
    {
        $indexName = 'osrw-products-' . bin2hex(random_bytes(6));
        $configurationName = 'osrw-mustache-' . bin2hex(random_bytes(6));
        $configurationId = null;
        $queryTemplate = json_encode([
            'query' => [
                'bool' => [
                    'must' => [
                        ['match' => ['name' => '{{queryText}}']],
                    ],
                    'filter' => [
                        ['term' => ['category' => '{{category}}']],
                    ],
                ],
            ],
        ], JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES);

        $this->openSearchClient->indices()->create([
            'index' => $indexName,
            'body' => [
                'settings' => [
                    'number_of_shards' => 1,
                    'number_of_replicas' => 0,
                ],
                'mappings' => [
                    'properties' => [
                        'name' => ['type' => 'text'],
                        'category' => ['type' => 'keyword'],
                    ],
                ],
            ],
        ]);

        try {
            $this->openSearchClient->index([
                'index' => $indexName,
                'id' => 'winter-boots',
                'body' => ['name' => 'Winter hiking boots', 'category' => 'boots'],
            ]);
            $this->openSearchClient->index([
                'index' => $indexName,
                'id' => 'winter-gloves',
                'body' => ['name' => 'Winter gloves', 'category' => 'accessories'],
            ]);
            $this->openSearchClient->indices()->refresh(['index' => $indexName]);

            $created = $this->searchRelevanceClient->createSearchConfiguration([
                'name' => $configurationName,
                'description' => 'Disposable parameterized catalog search fixture',
                'index' => $indexName,
                'query' => $queryTemplate,
                'searchPipeline' => '',
            ]);
            $configurationId = $created['search_configuration_id'] ?? null;

            self::assertIsString($configurationId);
            self::assertMatchesRegularExpression(
                '/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/',
                $configurationId
            );

            $retrieved = $this->searchRelevanceClient->getSearchConfiguration($configurationId);
            $searched = $this->searchRelevanceClient->searchSearchConfigurations([
                'size' => 100,
                'query' => ['match_all' => new \stdClass()],
            ]);
            $storedConfiguration = $retrieved['hits']['hits'][0]['_source'] ?? [];

            self::assertSame($configurationName, $storedConfiguration['name'] ?? null);
            self::assertSame($indexName, $storedConfiguration['index'] ?? null);
            self::assertSame($queryTemplate, $storedConfiguration['query'] ?? null);
            self::assertContains(
                $configurationId,
                array_column($searched['hits']['hits'] ?? [], '_id')
            );

            $rendered = $this->openSearchClient->renderSearchTemplate([
                'body' => [
                    'source' => json_decode($queryTemplate, true, flags: JSON_THROW_ON_ERROR),
                    'params' => [
                        'queryText' => 'winter',
                        'category' => 'boots',
                    ],
                ],
            ]);
            $renderedQuery = $rendered['template_output'] ?? null;

            self::assertIsArray($renderedQuery);
            self::assertSame('winter', $renderedQuery['query']['bool']['must'][0]['match']['name'] ?? null);
            self::assertSame('boots', $renderedQuery['query']['bool']['filter'][0]['term']['category'] ?? null);

            $searchResult = $this->openSearchClient->search([
                'index' => $indexName,
                'body' => $renderedQuery,
            ]);

            self::assertSame(1, $searchResult['hits']['total']['value'] ?? null);
            self::assertSame('winter-boots', $searchResult['hits']['hits'][0]['_id'] ?? null);
        } finally {
            if (is_string($configurationId)) {
                $deleted = $this->searchRelevanceClient->deleteSearchConfiguration($configurationId);
                self::assertSame('deleted', $deleted['result'] ?? null);
            }

            $this->openSearchClient->indices()->delete(['index' => $indexName]);
        }
    }

    public function testIndependentIndexEvidenceDetectsCatalogDocumentDrift(): void
    {
        $indexName = 'osrw-evidence-' . bin2hex(random_bytes(6));
        $aliasName = 'osrw-catalog-' . bin2hex(random_bytes(6));
        $this->openSearchClient->indices()->create([
            'index' => $indexName,
            'body' => [
                'settings' => [
                    'number_of_shards' => 1,
                    'number_of_replicas' => 0,
                    'analysis' => [
                        'analyzer' => [
                            'catalog_text' => ['type' => 'standard'],
                        ],
                    ],
                ],
                'mappings' => [
                    'properties' => [
                        'name' => ['type' => 'text', 'analyzer' => 'catalog_text'],
                    ],
                ],
                'aliases' => [$aliasName => new \stdClass()],
            ],
        ]);

        try {
            $this->openSearchClient->index([
                'index' => $indexName,
                'id' => 'first-product',
                'body' => ['name' => 'Winter boots'],
                'refresh' => true,
            ]);

            $capture = new IndexEvidenceCapture($this->clientProvider, new CanonicalJson());
            $before = $capture->capture($aliasName);
            $unchanged = $capture->capture($aliasName);

            self::assertSame($indexName, $before->getPhysicalIndex());
            self::assertSame(1, $before->getDocumentCount());
            self::assertSame($before->getEvidenceHash(), $unchanged->getEvidenceHash());

            $this->openSearchClient->index([
                'index' => $indexName,
                'id' => 'second-product',
                'body' => ['name' => 'Winter gloves'],
                'refresh' => true,
            ]);
            $after = $capture->capture($aliasName);

            self::assertSame(2, $after->getDocumentCount());
            self::assertSame($before->getIndexUuid(), $after->getIndexUuid());
            self::assertSame($before->getMappingHash(), $after->getMappingHash());
            self::assertSame($before->getRelevantSettingsHash(), $after->getRelevantSettingsHash());
            self::assertNotSame($before->getPrimaryShardBoundaries(), $after->getPrimaryShardBoundaries());
            self::assertNotSame($before->getEvidenceHash(), $after->getEvidenceHash());
        } finally {
            $this->openSearchClient->indices()->delete(['index' => $indexName]);
        }
    }

    public function testImportedHumanJudgmentRunsValidatedPointwiseExperiment(): void
    {
        $suffix = bin2hex(random_bytes(6));
        $indexName = 'osrw-human-' . $suffix;
        $querySetId = null;
        $configurationId = null;
        $judgmentId = null;
        $experimentId = null;
        $this->openSearchClient->indices()->create([
            'index' => $indexName,
            'body' => [
                'settings' => [
                    'number_of_shards' => 1,
                    'number_of_replicas' => 0,
                ],
                'mappings' => [
                    'properties' => [
                        'name' => ['type' => 'text'],
                    ],
                ],
            ],
        ]);

        try {
            foreach ([
                'boots-best' => 'Winter hiking boots',
                'boots-fashion' => 'Winter leather boots',
                'gloves' => 'Winter gloves',
            ] as $documentId => $name) {
                $this->openSearchClient->index([
                    'index' => $indexName,
                    'id' => $documentId,
                    'body' => ['name' => $name],
                ]);
            }
            $this->openSearchClient->indices()->refresh(['index' => $indexName]);

            $querySet = $this->searchRelevanceClient->createQuerySet([
                'name' => 'osrw-human-query-' . $suffix,
                'description' => 'Disposable human judgment query fixture',
                'sampling' => 'manual',
                'querySetQueries' => [
                    ['queryText' => 'winter boots'],
                ],
            ]);
            $querySetId = $querySet['query_set_id'] ?? null;
            self::assertIsString($querySetId);

            $configuration = $this->searchRelevanceClient->createSearchConfiguration([
                'name' => 'osrw-human-config-' . $suffix,
                'description' => 'Disposable human judgment configuration fixture',
                'index' => $indexName,
                'query' => '{"query":{"match":{"name":"{{queryText}}"}}}',
                'searchPipeline' => '',
            ]);
            $configurationId = $configuration['search_configuration_id'] ?? null;
            self::assertIsString($configurationId);

            $judgment = $this->searchRelevanceClient->createJudgment([
                'name' => 'osrw-human-rating-' . $suffix,
                'description' => 'Disposable merchant ratings',
                'type' => 'IMPORT_JUDGMENT',
                'judgmentRatings' => [
                    [
                        'query' => 'winter boots',
                        'ratings' => [
                            ['docId' => 'boots-best', 'rating' => '1.0'],
                            ['docId' => 'boots-fashion', 'rating' => '0.7'],
                            ['docId' => 'gloves', 'rating' => '0.0'],
                        ],
                    ],
                ],
            ]);
            $judgmentId = $judgment['judgment_id'] ?? null;
            self::assertIsString($judgmentId);

            $judgmentSource = $this->pollResourceSource(
                fn (): array => $this->searchRelevanceClient->getJudgment($judgmentId),
                'COMPLETED'
            );
            self::assertSame('IMPORT_JUDGMENT', $judgmentSource['type'] ?? null);
            self::assertCount(1, $judgmentSource['judgmentRatings'] ?? []);
            $searchedJudgments = $this->searchRelevanceClient->searchJudgments([
                'size' => 100,
                'query' => ['match_all' => new \stdClass()],
            ]);
            self::assertContains(
                $judgmentId,
                array_column($searchedJudgments['hits']['hits'] ?? [], '_id')
            );

            $experiment = $this->searchRelevanceClient->createExperiment([
                'name' => 'osrw-human-experiment-' . $suffix,
                'description' => 'Disposable pointwise experiment fixture',
                'querySetId' => $querySetId,
                'searchConfigurationList' => [$configurationId],
                'judgmentList' => [$judgmentId],
                'size' => 3,
                'type' => 'POINTWISE_EVALUATION',
            ]);
            $experimentId = $experiment['experiment_id'] ?? null;
            self::assertIsString($experimentId);

            $experimentSource = $this->pollResourceSource(
                fn (): array => $this->searchRelevanceClient->getExperiment($experimentId),
                'COMPLETED'
            );
            self::assertSame('POINTWISE_EVALUATION', $experimentSource['type'] ?? null);
            self::assertSame($querySetId, $experimentSource['querySetId'] ?? null);
            self::assertSame([$configurationId], $experimentSource['searchConfigurationList'] ?? null);
            self::assertSame([$judgmentId], $experimentSource['judgmentList'] ?? null);
            self::assertCount(1, $experimentSource['results'] ?? []);
            self::assertIsString($experimentSource['results'][0]['evaluationId'] ?? null);

            $validation = $this->searchRelevanceClient->validateExperiment($experimentId);
            self::assertSame('VALID', $validation['status'] ?? null);
            self::assertSame([], $validation['drifted_inputs'] ?? null);

            $searched = $this->searchRelevanceClient->searchExperiments([
                'size' => 100,
                'query' => ['match_all' => new \stdClass()],
            ]);
            self::assertContains(
                $experimentId,
                array_column($searched['hits']['hits'] ?? [], '_id')
            );

            $this->openSearchClient->update([
                'index' => 'search-relevance-queryset',
                'id' => $querySetId,
                'body' => [
                    'doc' => [
                        'querySetQueries' => [
                            ['queryText' => 'changed after experiment'],
                        ],
                    ],
                ],
                'refresh' => true,
            ]);
            $driftedValidation = $this->searchRelevanceClient->validateExperiment($experimentId);

            self::assertSame('DRIFTED', $driftedValidation['status'] ?? null);
            self::assertContains('query_set', $driftedValidation['drifted_inputs'] ?? []);

            // The plugin API protects referenced judgments. This direct fixture mutation characterizes
            // the response when an operator or external process removes the backing document.
            $deleted = $this->openSearchClient->delete([
                'index' => 'search-relevance-judgment',
                'id' => $judgmentId,
                'refresh' => true,
            ]);
            self::assertSame('deleted', $deleted['result'] ?? null);
            $judgmentId = null;

            try {
                $this->searchRelevanceClient->validateExperiment($experimentId);
                self::fail('Missing judgment unexpectedly returned a validation response');
            } catch (SearchRelevanceTransportException $exception) {
                self::assertSame(SearchRelevanceTransportException::REMOTE_FAILURE, $exception->getReasonCode());
                self::assertSame(500, $exception->getStatusCode());
                self::assertTrue($exception->isRetryable());
                self::assertSame('OpenSearch Search Relevance returned a server error', $exception->getMessage());
                self::assertStringNotContainsString('Document not found', $exception->getMessage());
            }
        } finally {
            if (is_string($experimentId)) {
                $deleted = $this->searchRelevanceClient->deleteExperiment($experimentId);
                self::assertSame('deleted', $deleted['result'] ?? null);
            }
            if (is_string($judgmentId)) {
                $deleted = $this->searchRelevanceClient->deleteJudgment($judgmentId);
                self::assertSame('deleted', $deleted['result'] ?? null);
            }
            if (is_string($configurationId)) {
                $deleted = $this->searchRelevanceClient->deleteSearchConfiguration($configurationId);
                self::assertSame('deleted', $deleted['result'] ?? null);
            }
            if (is_string($querySetId)) {
                $deleted = $this->searchRelevanceClient->deleteQuerySet($querySetId);
                self::assertSame('deleted', $deleted['result'] ?? null);
            }

            $this->openSearchClient->indices()->delete(['index' => $indexName]);
        }
    }

    public function testHumanJudgedCandidateRunsCompleteExportOnlyExperimentLoop(): void
    {
        $suffix = bin2hex(random_bytes(6));
        $indexName = 'osrw-loop-' . $suffix;
        $aliasName = 'osrw-loop-alias-' . $suffix;
        $querySetId = null;
        $judgmentId = null;
        $configurationIds = [];
        $experimentIds = [];
        $this->openSearchClient->indices()->create([
            'index' => $indexName,
            'body' => [
                'settings' => [
                    'number_of_shards' => 1,
                    'number_of_replicas' => 0,
                ],
                'mappings' => [
                    'properties' => [
                        'name' => ['type' => 'text'],
                        'keywords' => ['type' => 'text'],
                    ],
                ],
                'aliases' => [$aliasName => new \stdClass()],
            ],
        ]);

        try {
            $documents = [
                'boots-best' => ['name' => 'Waterproof trail footwear', 'keywords' => 'winter boots hiking'],
                'boots-decoy' => ['name' => 'Winter boots decorative ornament', 'keywords' => 'home decor'],
                'boots-bad' => ['name' => 'Winter gloves', 'keywords' => 'cold weather accessory'],
                'dress-best' => ['name' => 'Evening garment', 'keywords' => 'red dress formal'],
                'dress-decoy' => ['name' => 'Red dress costume poster', 'keywords' => 'wall art'],
                'dress-bad' => ['name' => 'Red running shoes', 'keywords' => 'athletic footwear'],
            ];

            foreach ($documents as $documentId => $document) {
                $this->openSearchClient->index([
                    'index' => $indexName,
                    'id' => $documentId,
                    'body' => $document,
                ]);
            }

            $this->openSearchClient->indices()->refresh(['index' => $indexName]);
            $canonicalJson = new CanonicalJson();
            $sourceRows = [
                [
                    'query_id' => 1,
                    'query_text' => 'winter boots',
                    'popularity' => 20,
                    'num_results' => 3,
                    'redirect' => null,
                    'store_id' => 1,
                    'is_active' => 1,
                    'updated_at' => '2026-08-26 12:00:00',
                ],
                [
                    'query_id' => 2,
                    'query_text' => 'red dress',
                    'popularity' => 10,
                    'num_results' => 3,
                    'redirect' => null,
                    'store_id' => 1,
                    'is_active' => 1,
                    'updated_at' => '2026-08-26 12:01:00',
                ],
            ];
            $preview = (new QuerySnapshotPreviewer(new PrivacyDetector(), $canonicalJson))->preview(
                1,
                $sourceRows,
                new SnapshotPolicy(1, 10, 10, 20, false, 128, 'osrw-privacy-v1')
            );
            $snapshot = $preview->approve(
                $preview->getSnapshotHash(),
                1,
                '2026-08-26T12:30:00+00:00'
            );
            $querySet = $this->searchRelevanceClient->createQuerySet([
                'name' => 'osrw-loop-query-' . $suffix,
                'description' => 'Disposable complete human workflow query set',
                'sampling' => 'manual',
                'querySetQueries' => $snapshot->getRemoteQuerySetEntries(),
            ]);
            $querySetId = $querySet['query_set_id'] ?? null;
            self::assertIsString($querySetId);

            $baselineTemplateArray = [
                'index' => $indexName,
                'body' => [
                    'query' => [
                        'multi_match' => [
                            'query' => '{{queryText}}',
                            'fields' => ['name^5', 'keywords'],
                        ],
                    ],
                ],
            ];
            $baseline = new BaselineTemplate(
                $baselineTemplateArray,
                ['/body/query/multi_match/query'],
                $canonicalJson->hash($baselineTemplateArray)
            );
            $candidate = (new FieldBoostCompiler($canonicalJson))->compile(
                $baseline,
                [
                    'name' => [
                        'searchable' => true,
                        'sensitive' => false,
                        'dynamic' => false,
                        'type' => 'text',
                    ],
                    'keywords' => [
                        'searchable' => true,
                        'sensitive' => false,
                        'dynamic' => false,
                        'type' => 'text',
                    ],
                ],
                ['keywords' => 20.0]
            );

            foreach (
                [
                    'baseline' => [$baseline->getTemplate(), $baseline->getTemplateHash()],
                    'candidate' => [$candidate->getTemplate(), $candidate->getConfigurationHash()],
                ] as $kind => [$template, $configurationHash]
            ) {
                $created = $this->searchRelevanceClient->createSearchConfiguration([
                    'name' => 'osrw-loop-' . $kind . '-' . $suffix,
                    'description' => 'Disposable complete human workflow ' . $kind,
                    'index' => $template['index'],
                    'query' => json_encode($template['body'], JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES),
                    'searchPipeline' => '',
                ]);
                $configurationId = $created['search_configuration_id'] ?? null;
                self::assertIsString($configurationId);
                $configurationIds[$kind] = [
                    'remote_id' => $configurationId,
                    'hash' => $configurationHash,
                ];
            }

            $indexEvidence = (new IndexEvidenceCapture($this->clientProvider, $canonicalJson))->capture($aliasName);
            $bootsHash = hash('sha256', 'winter boots');
            $dressHash = hash('sha256', 'red dress');
            $ratingRows = [
                ['query_hash' => $bootsHash, 'document_id' => 'boots-best', 'rating' => 1.0],
                ['query_hash' => $bootsHash, 'document_id' => 'boots-decoy', 'rating' => 0.0],
                ['query_hash' => $bootsHash, 'document_id' => 'boots-bad', 'rating' => 0.0],
                ['query_hash' => $dressHash, 'document_id' => 'dress-best', 'rating' => 1.0],
                ['query_hash' => $dressHash, 'document_id' => 'dress-decoy', 'rating' => 0.0],
                ['query_hash' => $dressHash, 'document_id' => 'dress-bad', 'rating' => 0.0],
            ];
            $humanJudgments = (new HumanJudgmentSetFactory($canonicalJson))->create(
                $snapshot,
                $indexEvidence->getEvidenceHash(),
                $ratingRows,
                1,
                '2026-08-26T13:00:00+00:00'
            );
            $judgment = $this->searchRelevanceClient->createJudgment([
                'name' => 'osrw-loop-ratings-' . $suffix,
                'description' => 'Disposable complete merchant rating set',
                'type' => 'IMPORT_JUDGMENT',
                'judgmentRatings' => $humanJudgments->getRemoteJudgmentRatings(),
            ]);
            $judgmentId = $judgment['judgment_id'] ?? null;
            self::assertIsString($judgmentId);
            $this->pollResourceSource(
                fn (): array => $this->searchRelevanceClient->getJudgment($judgmentId),
                'COMPLETED'
            );

            $plan = (new HumanExperimentPlanFactory($canonicalJson))->create(
                (new UuidGenerator())->generate(),
                $snapshot->getSnapshotHash(),
                $querySetId,
                $configurationIds['baseline']['remote_id'],
                $configurationIds['baseline']['hash'],
                $configurationIds['candidate']['remote_id'],
                $configurationIds['candidate']['hash'],
                $judgmentId,
                $humanJudgments->getJudgmentHash(),
                $indexEvidence->getEvidenceHash(),
                3,
                1.0,
                'NDCG@10'
            );

            foreach ($plan->getRemotePayloads() as $kind => $payload) {
                $created = $this->searchRelevanceClient->createExperiment([
                    'name' => 'osrw-loop-' . strtolower($kind) . '-' . $suffix,
                    'description' => 'Disposable complete human workflow experiment',
                ] + $payload);
                $experimentId = $created['experiment_id'] ?? null;
                self::assertIsString($experimentId);
                $experimentIds[$kind] = $experimentId;
                $source = $this->pollResourceSource(
                    fn (): array => $this->searchRelevanceClient->getExperiment($experimentId),
                    'COMPLETED'
                );
                self::assertNotSame([], $source['results'] ?? []);
                $validation = $this->searchRelevanceClient->validateExperiment($experimentId);
                self::assertSame('VALID', $validation['status'] ?? null);
            }

            $baselineRankings = $this->rankingsForSnapshot($snapshot, $baseline->getTemplate(), 3);
            $candidateRankings = $this->rankingsForSnapshot($snapshot, $candidate->getTemplate(), 3);
            $ratings = [
                $bootsHash => ['boots-best' => 1.0, 'boots-decoy' => 0.0, 'boots-bad' => 0.0],
                $dressHash => ['dress-best' => 1.0, 'dress-decoy' => 0.0, 'dress-bad' => 0.0],
            ];
            $evidence = (new OfflineEvidenceEvaluator())->evaluate(
                $baselineRankings,
                $candidateRankings,
                $ratings,
                3,
                1.0,
                0.01,
                [$bootsHash, $dressHash],
                true,
                true
            );

            self::assertSame('WINNER', $evidence->getEligibility());
            self::assertGreaterThan(0.01, $evidence->getMetricDelta());
            $proposal = (new ProposalExporter($canonicalJson))->export(
                (new UuidGenerator())->generate(),
                '2026-08-26T14:00:00+00:00',
                1,
                $experimentIds['PAIRWISE_COMPARISON'],
                $snapshot->getSnapshotHash(),
                $humanJudgments->getJudgmentHash(),
                $indexEvidence->getEvidenceHash(),
                $baseline->getTemplateHash(),
                $candidate->getConfigurationHash(),
                $candidate->getTransformation(),
                $evidence,
                ['Offline relevance evidence does not establish revenue lift.']
            );

            self::assertSame(hash('sha256', $proposal->getCanonicalJson()), $proposal->getArtifactHash());
            self::assertStringNotContainsString('winter boots', $proposal->getCanonicalJson());
            self::assertStringNotContainsString('red dress', $proposal->getCanonicalJson());
            self::assertStringContainsString('"supported":false', $proposal->getCanonicalJson());
        } finally {
            foreach (array_reverse($experimentIds) as $experimentId) {
                $this->searchRelevanceClient->deleteExperiment($experimentId);
            }

            if (is_string($judgmentId)) {
                $this->searchRelevanceClient->deleteJudgment($judgmentId);
            }

            foreach (array_reverse($configurationIds) as $configuration) {
                $this->searchRelevanceClient->deleteSearchConfiguration($configuration['remote_id']);
            }

            if (is_string($querySetId)) {
                $this->searchRelevanceClient->deleteQuerySet($querySetId);
            }

            $this->openSearchClient->indices()->delete(['index' => $indexName]);
        }
    }

    /**
     * @param \MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\ApprovedQuerySnapshot $snapshot
     * @param array<array-key, mixed> $template
     * @return array<string, list<string>>
     */
    private function rankingsForSnapshot(
        \MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\ApprovedQuerySnapshot $snapshot,
        array $template,
        int $depth
    ): array {
        $rankings = [];

        foreach ($snapshot->getEntries() as $entry) {
            $rendered = $this->renderQueryText($template, $entry->getQueryText());
            $rendered['body']['size'] = $depth;
            $response = $this->openSearchClient->search($rendered);
            $rankings[$entry->getQueryHash()] = array_values(array_map(
                static fn (array $hit): string => (string)$hit['_id'],
                $response['hits']['hits'] ?? []
            ));
        }

        return $rankings;
    }

    /**
     * @param array<array-key, mixed> $value
     * @return array<array-key, mixed>
     */
    private function renderQueryText(array $value, string $queryText): array
    {
        array_walk_recursive(
            $value,
            static function (mixed &$item) use ($queryText): void {
                if ($item === BaselineTemplate::QUERY_TEXT_VARIABLE) {
                    $item = $queryText;
                }
            }
        );

        return $value;
    }

    /**
     * @param callable(): array<string, mixed> $readResource
     * @return array<string, mixed>
     */
    private function pollResourceSource(callable $readResource, string $terminalStatus): array
    {
        $lastStatus = null;

        for ($attempt = 0; $attempt < 100; $attempt++) {
            $response = $readResource();
            $source = $response['hits']['hits'][0]['_source'] ?? null;

            if (is_array($source)) {
                $lastStatus = $source['status'] ?? null;

                if ($lastStatus === $terminalStatus) {
                    return $source;
                }

                if (in_array($lastStatus, ['ERROR', 'TIMEOUT'], true)) {
                    self::fail(sprintf('Resource entered terminal failure status %s', $lastStatus));
                }
            }

            usleep(100_000);
        }

        self::fail(sprintf(
            'Resource did not reach %s; last status was %s',
            $terminalStatus,
            is_string($lastStatus) ? $lastStatus : 'unavailable'
        ));
    }
}
