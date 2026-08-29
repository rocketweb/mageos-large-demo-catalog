<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\SecurityIntegration\OpenSearch;

use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\ConfiguredOpenSearchClientProvider;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\IndexEvidenceCapture;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\SearchRelevanceClient;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\SearchRelevanceRequestFactory;
use OpenSearch\Client;
use OpenSearch\ClientBuilder;
use OpenSearch\Exception\ForbiddenHttpException;
use PHPUnit\Framework\TestCase;

class SearchRelevancePermissionsTest extends TestCase
{
    private const ROLE_NAME = 'osrw_integration_queryset_role';
    private const USERNAME = 'osrw_integration_user';
    private const DEFAULT_ADMIN_PASSWORD = 'Kite7!River9@Quartz3#Plum';
    private const DEFAULT_USER_PASSWORD = 'Cedar4!Orbit8@Lake6#Mint';

    private Client $adminClient;
    private Client $restrictedClient;
    private ConfiguredOpenSearchClientProvider $clientProvider;
    private SearchRelevanceClient $searchRelevanceClient;

    protected function setUp(): void
    {
        $url = getenv('OSRW_SECURITY_URL');

        if ($url === false || $url === '') {
            self::markTestSkipped('Set OSRW_SECURITY_URL to run OpenSearch security integration tests.');
        }

        $adminPassword = getenv('OSRW_SECURITY_ADMIN_PASSWORD') ?: self::DEFAULT_ADMIN_PASSWORD;
        $userPassword = getenv('OSRW_SECURITY_USER_PASSWORD') ?: self::DEFAULT_USER_PASSWORD;
        $this->adminClient = $this->buildClient($url, 'admin', $adminPassword);
        $this->configureRestrictedUser($userPassword);
        $this->restrictedClient = $this->buildClient($url, self::USERNAME, $userPassword);

        $this->clientProvider = $this->createStub(ConfiguredOpenSearchClientProvider::class);
        $this->clientProvider
            ->method('get')
            ->willReturn($this->restrictedClient);
        $this->searchRelevanceClient = new SearchRelevanceClient(
            $this->clientProvider,
            new SearchRelevanceRequestFactory()
        );
    }

    protected function tearDown(): void
    {
        if (!isset($this->adminClient)) {
            return;
        }

        $this->adminClient->request(
            'DELETE',
            '/_plugins/_security/api/rolesmapping/' . self::ROLE_NAME
        );
        $this->adminClient->request(
            'DELETE',
            '/_plugins/_security/api/internalusers/' . self::USERNAME
        );
        $this->adminClient->request(
            'DELETE',
            '/_plugins/_security/api/roles/' . self::ROLE_NAME
        );
    }

    public function testRestrictedRoleCanManageQuerySetsButCannotReadClusterSettings(): void
    {
        $querySetId = null;
        $name = 'osrw-sec-' . bin2hex(random_bytes(6));

        try {
            $stats = $this->searchRelevanceClient->stats();
            self::assertNotSame([], $stats);

            $created = $this->searchRelevanceClient->createQuerySet([
                'name' => $name,
                'description' => 'Disposable least-privilege fixture',
                'sampling' => 'manual',
                'querySetQueries' => [
                    ['queryText' => 'winter boots'],
                ],
            ]);
            $querySetId = $created['query_set_id'] ?? null;
            self::assertIsString($querySetId);

            $retrieved = $this->searchRelevanceClient->getQuerySet($querySetId);
            $searched = $this->searchRelevanceClient->searchQuerySets([
                'size' => 100,
                'query' => ['match_all' => new \stdClass()],
            ]);

            self::assertSame($name, $retrieved['hits']['hits'][0]['_source']['name'] ?? null);
            self::assertContains(
                $querySetId,
                array_column($searched['hits']['hits'] ?? [], '_id')
            );

            try {
                $this->restrictedClient->request('GET', '/_cluster/settings');
                self::fail('Restricted Search Relevance role unexpectedly read cluster settings');
            } catch (ForbiddenHttpException $exception) {
                self::assertSame(403, $exception->getStatusCode());
            }
        } finally {
            if (is_string($querySetId)) {
                $deleted = $this->searchRelevanceClient->deleteQuerySet($querySetId);
                self::assertSame('deleted', $deleted['result'] ?? null);
            }
        }
    }

    public function testRestrictedRoleCanRunHumanPointwiseExperiment(): void
    {
        $suffix = bin2hex(random_bytes(6));
        $indexName = 'osrw-security-' . $suffix;
        $querySetId = null;
        $configurationId = null;
        $judgmentId = null;
        $experimentId = null;
        $this->adminClient->indices()->create([
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
            $this->adminClient->index([
                'index' => $indexName,
                'id' => 'winter-boots',
                'body' => ['name' => 'Winter hiking boots'],
                'refresh' => true,
            ]);

            $querySet = $this->searchRelevanceClient->createQuerySet([
                'name' => 'osrw-sec-query-' . $suffix,
                'description' => 'Disposable secure query fixture',
                'sampling' => 'manual',
                'querySetQueries' => [
                    ['queryText' => 'winter boots'],
                ],
            ]);
            $querySetId = $querySet['query_set_id'] ?? null;
            self::assertIsString($querySetId);

            $configuration = $this->searchRelevanceClient->createSearchConfiguration([
                'name' => 'osrw-sec-config-' . $suffix,
                'description' => 'Disposable secure configuration fixture',
                'index' => $indexName,
                'query' => '{"query":{"match":{"name":"{{queryText}}"}}}',
                'searchPipeline' => '',
            ]);
            $configurationId = $configuration['search_configuration_id'] ?? null;
            self::assertIsString($configurationId);

            $judgment = $this->searchRelevanceClient->createJudgment([
                'name' => 'osrw-sec-rating-' . $suffix,
                'description' => 'Disposable secure merchant rating fixture',
                'type' => 'IMPORT_JUDGMENT',
                'judgmentRatings' => [
                    [
                        'query' => 'winter boots',
                        'ratings' => [
                            ['docId' => 'winter-boots', 'rating' => '1.0'],
                        ],
                    ],
                ],
            ]);
            $judgmentId = $judgment['judgment_id'] ?? null;
            self::assertIsString($judgmentId);
            $this->pollResourceSource(
                fn (): array => $this->searchRelevanceClient->getJudgment($judgmentId),
                'COMPLETED'
            );

            $experiment = $this->searchRelevanceClient->createExperiment([
                'name' => 'osrw-sec-experiment-' . $suffix,
                'description' => 'Disposable secure pointwise experiment fixture',
                'querySetId' => $querySetId,
                'searchConfigurationList' => [$configurationId],
                'judgmentList' => [$judgmentId],
                'size' => 1,
                'type' => 'POINTWISE_EVALUATION',
            ]);
            $experimentId = $experiment['experiment_id'] ?? null;
            self::assertIsString($experimentId);
            $experimentSource = $this->pollResourceSource(
                fn (): array => $this->searchRelevanceClient->getExperiment($experimentId),
                'COMPLETED'
            );

            self::assertCount(1, $experimentSource['results'] ?? []);
            $validation = $this->searchRelevanceClient->validateExperiment($experimentId);
            self::assertSame('VALID', $validation['status'] ?? null);
        } finally {
            if (is_string($experimentId)) {
                $this->searchRelevanceClient->deleteExperiment($experimentId);
            }
            if (is_string($judgmentId)) {
                $this->searchRelevanceClient->deleteJudgment($judgmentId);
            }
            if (is_string($configurationId)) {
                $this->searchRelevanceClient->deleteSearchConfiguration($configurationId);
            }
            if (is_string($querySetId)) {
                $this->searchRelevanceClient->deleteQuerySet($querySetId);
            }

            $this->adminClient->indices()->delete(['index' => $indexName]);
        }
    }

    public function testRestrictedRoleCanCaptureTargetIndexEvidence(): void
    {
        $suffix = bin2hex(random_bytes(6));
        $indexName = 'osrw-security-evidence-' . $suffix;
        $aliasName = 'osrw-security-catalog-' . $suffix;
        $this->adminClient->indices()->create([
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
                'aliases' => [$aliasName => new \stdClass()],
            ],
        ]);

        try {
            $this->adminClient->index([
                'index' => $indexName,
                'id' => 'winter-boots',
                'body' => ['name' => 'Winter hiking boots'],
                'refresh' => true,
            ]);
            $evidence = (new IndexEvidenceCapture($this->clientProvider, new CanonicalJson()))
                ->capture($aliasName);

            self::assertSame($aliasName, $evidence->getAlias());
            self::assertSame($indexName, $evidence->getPhysicalIndex());
            self::assertSame(1, $evidence->getDocumentCount());

            try {
                $this->restrictedClient->search([
                    'index' => $indexName,
                    'body' => ['query' => ['match_all' => new \stdClass()]],
                ]);
                self::fail('Evidence-only role unexpectedly read catalog documents');
            } catch (ForbiddenHttpException $exception) {
                self::assertSame(403, $exception->getStatusCode());
            }
        } finally {
            $this->adminClient->indices()->delete(['index' => $indexName]);
        }
    }

    private function configureRestrictedUser(string $password): void
    {
        $this->adminClient->request(
            'PUT',
            '/_plugins/_security/api/roles/' . self::ROLE_NAME,
            [
                'body' => [
                    'cluster_permissions' => [
                        'cluster:admin/search_relevance_stats_action',
                        'cluster:admin/opensearch/search_relevance/queryset/put',
                        'cluster:admin/opensearch/search_relevance/queryset/get',
                        'cluster:admin/opensearch/search_relevance/queryset/search',
                        'cluster:admin/opensearch/search_relevance/queryset/delete',
                        'cluster:admin/opensearch/search_relevance/search_configuration/create',
                        'cluster:admin/opensearch/search_relevance/search_configuration/get',
                        'cluster:admin/opensearch/search_relevance/search_configuration/search',
                        'cluster:admin/opensearch/search_relevance/search_configuration/delete',
                        'cluster:admin/opensearch/search_relevance/judgment/create',
                        'cluster:admin/opensearch/search_relevance/judgment/get',
                        'cluster:admin/opensearch/search_relevance/judgment/search',
                        'cluster:admin/opensearch/search_relevance/judgment/delete',
                        'cluster:admin/opensearch/search_relevance/experiment/create',
                        'cluster:admin/opensearch/search_relevance/experiment/get',
                        'cluster:admin/opensearch/search_relevance/experiment/search',
                        'cluster:admin/opensearch/search_relevance/experiment/delete',
                        'cluster:admin/opensearch/search_relevance/experiment/validate',
                    ],
                    'index_permissions' => [
                        [
                            'index_patterns' => ['osrw-security-*'],
                            'allowed_actions' => [
                                'indices:admin/aliases/get',
                                'indices:admin/mappings/get',
                                'indices:monitor/settings/get',
                                'indices:monitor/stats',
                            ],
                        ],
                    ],
                    'tenant_permissions' => [],
                ],
            ]
        );
        $this->adminClient->request(
            'PUT',
            '/_plugins/_security/api/internalusers/' . self::USERNAME,
            [
                'body' => [
                    'password' => $password,
                    'backend_roles' => [],
                    'attributes' => new \stdClass(),
                ],
            ]
        );
        $this->adminClient->request(
            'PUT',
            '/_plugins/_security/api/rolesmapping/' . self::ROLE_NAME,
            [
                'body' => [
                    'backend_roles' => [],
                    'hosts' => [],
                    'users' => [self::USERNAME],
                ],
            ]
        );
    }

    private function buildClient(string $url, string $username, string $password): Client
    {
        return ClientBuilder::create()
            ->setHosts([$url])
            ->setBasicAuthentication($username, $password)
            ->setSSLVerification(false)
            ->build();
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
