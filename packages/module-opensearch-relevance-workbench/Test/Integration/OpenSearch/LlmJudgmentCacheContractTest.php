<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Integration\OpenSearch;

use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\ConfiguredOpenSearchClientProvider;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\SearchRelevanceClient;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\SearchRelevanceRequestFactory;
use OpenSearch\Client;
use OpenSearch\ClientBuilder;
use PHPUnit\Framework\TestCase;
use RuntimeException;

class LlmJudgmentCacheContractTest extends TestCase
{
    private const PROMPT = 'SearchText: {{searchText}}; Hits: {{hits}}';

    private Client $openSearchClient;
    private SearchRelevanceClient $searchRelevanceClient;
    private string $stubUrl;

    protected function setUp(): void
    {
        if (getenv('OSRW_ENABLE_LLM_CACHE_PROBE') !== '1') {
            self::markTestSkipped(
                'Opt-in probe: the pinned OpenSearch 3.8.0 distribution crashes during SRW remote-model prediction. '
                . 'See PHASE-0-FINDINGS.md.'
            );
        }

        $openSearchUrl = getenv('OSRW_LLM_OPENSEARCH_URL');
        $stubUrl = getenv('OSRW_OPENAI_STUB_URL');

        if ($openSearchUrl === false || $openSearchUrl === '' || $stubUrl === false || $stubUrl === '') {
            self::markTestSkipped('Set OSRW_LLM_OPENSEARCH_URL and OSRW_OPENAI_STUB_URL to run LLM integration tests.');
        }

        $this->stubUrl = rtrim($stubUrl, '/');
        $this->openSearchClient = ClientBuilder::create()
            ->setHosts([$openSearchUrl])
            ->build();
        $clientProvider = $this->createStub(ConfiguredOpenSearchClientProvider::class);
        $clientProvider
            ->method('get')
            ->willReturn($this->openSearchClient);
        $this->searchRelevanceClient = new SearchRelevanceClient(
            $clientProvider,
            new SearchRelevanceRequestFactory()
        );
    }

    public function testTaggedCacheIgnoresDocumentAndModelChangesUnlessOverwriteIsEnabled(): void
    {
        $resources = [
            'connector' => null,
            'model_group' => null,
            'models' => [],
            'index' => 'osrw-llm-cache-' . bin2hex(random_bytes(6)),
            'query_set' => null,
            'configuration' => null,
            'judgments' => [],
        ];
        $this->configureFixtureConnectorAllowlist();
        $this->resetStub();

        try {
            $resources['connector'] = $this->createConnector();
            $resources['model_group'] = $this->createModelGroup();
            $resources['models'][] = $this->registerDeployedModel(
                $resources['connector'],
                $resources['model_group'],
                'fixture-model-a'
            );
            $resources['models'][] = $this->registerDeployedModel(
                $resources['connector'],
                $resources['model_group'],
                'fixture-model-b'
            );
            $this->createCatalogFixture($resources['index'], 'Original winter boots');
            $resources['query_set'] = $this->createQuerySet();
            $resources['configuration'] = $this->createSearchConfiguration(
                $resources['index'],
                $resources['query_set']
            );

            $resources['judgments'][] = $this->createAndPollJudgment(
                $resources['models'][0],
                $resources['query_set'],
                $resources['configuration'],
                true,
                'initial'
            );
            self::assertSame(1, $this->stubStats()['calls'] ?? null);

            $this->openSearchClient->update([
                'index' => $resources['index'],
                'id' => 'boots',
                'body' => ['doc' => ['name' => 'Changed sandals']],
                'refresh' => true,
            ]);
            $resources['judgments'][] = $this->createAndPollJudgment(
                $resources['models'][0],
                $resources['query_set'],
                $resources['configuration'],
                false,
                'document-change-cache-probe'
            );
            self::assertSame(
                1,
                $this->stubStats()['calls'] ?? null,
                'OpenSearch 3.8 unexpectedly included document content in its judgment cache lookup'
            );

            $resources['judgments'][] = $this->createAndPollJudgment(
                $resources['models'][1],
                $resources['query_set'],
                $resources['configuration'],
                false,
                'model-change-cache-probe'
            );
            self::assertSame(
                1,
                $this->stubStats()['calls'] ?? null,
                'OpenSearch 3.8 unexpectedly included model ID in its judgment cache lookup'
            );

            $resources['judgments'][] = $this->createAndPollJudgment(
                $resources['models'][1],
                $resources['query_set'],
                $resources['configuration'],
                true,
                'forced-overwrite'
            );
            self::assertSame(2, $this->stubStats()['calls'] ?? null);
        } finally {
            $this->cleanup($resources);
        }
    }

    private function configureFixtureConnectorAllowlist(): void
    {
        $this->openSearchClient->request('PUT', '/_cluster/settings', [
            'body' => [
                'persistent' => [
                    'plugins.ml_commons.connector.private_ip_enabled' => true,
                    'plugins.ml_commons.trusted_connector_endpoints_regex' => [
                        '^http://openai-stub:8000/.*$',
                    ],
                    'plugins.ml_commons.trusted_connector_private_endpoints_regex' => [
                        '^http://openai-stub:8000/.*$',
                    ],
                ],
            ],
        ]);
    }

    private function createConnector(): string
    {
        $response = $this->openSearchClient->request('POST', '/_plugins/_ml/connectors/_create', [
            'body' => [
                'name' => 'OSRW deterministic LLM fixture',
                'description' => 'Disposable local connector for cache contract tests',
                'version' => 1,
                'protocol' => 'http',
                'parameters' => [
                    'endpoint' => 'openai-stub:8000',
                    'model' => 'osrw-deterministic',
                ],
                'credential' => ['fixture_token' => 'not-a-secret'],
                'client_config' => [
                    'max_retry_times' => 1,
                    'retry_backoff_policy' => 'constant',
                ],
                'actions' => [
                    [
                        'action_type' => 'predict',
                        'method' => 'POST',
                        'url' => 'http://${parameters.endpoint}/v1/chat/completions',
                        'headers' => ['Content-Type' => 'application/json'],
                        'request_body' => '{"model":"${parameters.model}",'
                            . '"messages":[{"role":"system","content":"${parameters.system_prompt}"},'
                            . '{"role":"user","content":"${parameters.user_prompt}"}]}',
                        'post_process_function' => 'def text = params.choices[0].message.content; '
                            . 'return \'{"name":"response","dataAsMap":{"response":"\' '
                            . '+ escape(text) + \'"}}\';',
                    ],
                ],
            ],
        ]);
        $connectorId = $response['connector_id'] ?? null;
        self::assertIsString($connectorId);

        return $connectorId;
    }

    private function createModelGroup(): string
    {
        $response = $this->openSearchClient->request('POST', '/_plugins/_ml/model_groups/_register', [
            'body' => [
                'name' => 'osrw-fixture-' . bin2hex(random_bytes(6)),
                'description' => 'Disposable local LLM judgment fixture',
            ],
        ]);
        $modelGroupId = $response['model_group_id'] ?? null;
        self::assertIsString($modelGroupId);

        return $modelGroupId;
    }

    private function registerDeployedModel(string $connectorId, string $modelGroupId, string $name): string
    {
        $response = $this->openSearchClient->request('POST', '/_plugins/_ml/models/_register?deploy=true', [
            'body' => [
                'name' => $name,
                'function_name' => 'remote',
                'model_group_id' => $modelGroupId,
                'description' => 'Disposable local LLM judgment model',
                'connector_id' => $connectorId,
            ],
        ]);
        $taskId = $response['task_id'] ?? null;
        self::assertIsString($taskId);
        $task = $this->pollMlTask($taskId);
        $modelId = $task['model_id'] ?? $response['model_id'] ?? null;
        self::assertIsString($modelId);

        return $modelId;
    }

    /**
     * @return array<string, mixed>
     */
    private function pollMlTask(string $taskId): array
    {
        $lastState = null;

        for ($attempt = 0; $attempt < 100; $attempt++) {
            $task = $this->openSearchClient->request('GET', '/_plugins/_ml/tasks/' . rawurlencode($taskId));
            $lastState = $task['state'] ?? null;

            if ($lastState === 'COMPLETED') {
                return $task;
            }

            if (in_array($lastState, ['FAILED', 'COMPLETED_WITH_ERROR'], true)) {
                self::fail('ML model registration failed with state ' . $lastState);
            }

            usleep(100_000);
        }

        self::fail('ML model registration did not complete; last state was ' . (string)$lastState);
    }

    private function createCatalogFixture(string $indexName, string $name): void
    {
        $this->openSearchClient->indices()->create([
            'index' => $indexName,
            'body' => [
                'settings' => ['number_of_shards' => 1, 'number_of_replicas' => 0],
                'mappings' => ['properties' => ['name' => ['type' => 'text']]],
            ],
        ]);
        $this->openSearchClient->index([
            'index' => $indexName,
            'id' => 'boots',
            'body' => ['name' => $name],
            'refresh' => true,
        ]);
    }

    private function createQuerySet(): string
    {
        $response = $this->searchRelevanceClient->createQuerySet([
            'name' => 'osrw-llm-query-' . bin2hex(random_bytes(6)),
            'description' => 'Disposable LLM cache query fixture',
            'sampling' => 'manual',
            'querySetQueries' => [['queryText' => 'winter boots']],
        ]);
        $querySetId = $response['query_set_id'] ?? null;
        self::assertIsString($querySetId);

        return $querySetId;
    }

    private function createSearchConfiguration(string $indexName, string $querySetId): string
    {
        $response = $this->searchRelevanceClient->createSearchConfiguration([
            'name' => 'osrw-llm-config-' . bin2hex(random_bytes(6)),
            'description' => 'Disposable LLM cache search fixture for ' . $querySetId,
            'index' => $indexName,
            'query' => '{"query":{"match":{"name":"{{queryText}}"}}}',
            'searchPipeline' => '',
        ]);
        $configurationId = $response['search_configuration_id'] ?? null;
        self::assertIsString($configurationId);

        return $configurationId;
    }

    private function createAndPollJudgment(
        string $modelId,
        string $querySetId,
        string $configurationId,
        bool $overwriteCache,
        string $suffix
    ): string {
        $response = $this->searchRelevanceClient->createJudgment([
            'name' => 'osrw-llm-' . $suffix . '-' . bin2hex(random_bytes(4)),
            'description' => 'Disposable LLM cache contract probe',
            'type' => 'LLM_JUDGMENT',
            'modelId' => $modelId,
            'querySetId' => $querySetId,
            'searchConfigurationList' => [$configurationId],
            'size' => 1,
            'tokenLimit' => 1000,
            'contextFields' => ['name'],
            'ignoreFailure' => false,
            'llmJudgmentRatingType' => 'SCORE0_1',
            'promptTemplate' => self::PROMPT,
            'overwriteCache' => $overwriteCache,
        ]);
        $judgmentId = $response['judgment_id'] ?? null;
        self::assertIsString($judgmentId);
        $source = $this->pollJudgment($judgmentId);
        self::assertSame('COMPLETED', $source['status'] ?? null);
        self::assertSame([], $source['judgmentRatings'][0]['failures'] ?? []);

        return $judgmentId;
    }

    /**
     * @return array<string, mixed>
     */
    private function pollJudgment(string $judgmentId): array
    {
        $lastState = null;

        for ($attempt = 0; $attempt < 200; $attempt++) {
            $response = $this->searchRelevanceClient->getJudgment($judgmentId);
            $source = $response['hits']['hits'][0]['_source'] ?? null;

            if (is_array($source)) {
                $lastState = $source['status'] ?? null;

                if (in_array($lastState, ['COMPLETED', 'ERROR', 'TIMEOUT'], true)) {
                    return $source;
                }
            }

            usleep(100_000);
        }

        self::fail('LLM judgment did not complete; last state was ' . (string)$lastState);
    }

    private function resetStub(): void
    {
        $this->stubRequest('/__control__/reset', 'POST');
    }

    /**
     * @return array<string, mixed>
     */
    private function stubStats(): array
    {
        return $this->stubRequest('/__control__/stats', 'GET');
    }

    /**
     * @return array<string, mixed>
     */
    private function stubRequest(string $path, string $method): array
    {
        $context = stream_context_create([
            'http' => [
                'method' => $method,
                'ignore_errors' => true,
                'timeout' => 5,
            ],
        ]);
        $response = file_get_contents($this->stubUrl . $path, false, $context);

        if ($response === false) {
            throw new RuntimeException('OpenAI-compatible fixture request failed');
        }

        $decoded = json_decode($response, true, flags: JSON_THROW_ON_ERROR);

        if (!is_array($decoded)) {
            throw new RuntimeException('OpenAI-compatible fixture returned an invalid response');
        }

        return $decoded;
    }

    /**
     * @param array<string, mixed> $resources
     */
    private function cleanup(array $resources): void
    {
        foreach (array_reverse($resources['judgments']) as $judgmentId) {
            $this->searchRelevanceClient->deleteJudgment($judgmentId);
        }

        if (is_string($resources['configuration'])) {
            $this->searchRelevanceClient->deleteSearchConfiguration($resources['configuration']);
        }

        if (is_string($resources['query_set'])) {
            $this->searchRelevanceClient->deleteQuerySet($resources['query_set']);
        }

        if (is_string($resources['index']) && $this->openSearchClient->indices()->exists([
            'index' => $resources['index'],
        ])) {
            $this->openSearchClient->indices()->delete(['index' => $resources['index']]);
        }

        foreach (array_reverse($resources['models']) as $modelId) {
            $this->openSearchClient->request('POST', '/_plugins/_ml/models/' . rawurlencode($modelId) . '/_undeploy');
            $this->openSearchClient->request('DELETE', '/_plugins/_ml/models/' . rawurlencode($modelId));
        }

        if (is_string($resources['model_group'])) {
            $this->openSearchClient->request(
                'DELETE',
                '/_plugins/_ml/model_groups/' . rawurlencode($resources['model_group'])
            );
        }

        if (is_string($resources['connector'])) {
            $this->openSearchClient->request(
                'DELETE',
                '/_plugins/_ml/connectors/' . rawurlencode($resources['connector'])
            );
        }
    }
}
