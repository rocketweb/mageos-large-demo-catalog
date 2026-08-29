<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\OpenSearch;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\SearchRelevanceRequest;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\SearchRelevanceRequestFactory;
use PHPUnit\Framework\TestCase;

class SearchRelevanceRequestFactoryTest extends TestCase
{
    private const RESOURCE_ID = '7f9af483-a45a-4f1f-9d76-a7dff9715e38';

    public function testCreatesExplicitRequestsForEveryOwnedResourceType(): void
    {
        $factory = new SearchRelevanceRequestFactory();
        $payload = ['name' => 'osrw-query-set', 'nested' => ['value' => '{{queryText}}']];

        $this->assertRequest(
            'PUT',
            '/_plugins/_search_relevance/query_sets',
            $payload,
            $factory->createQuerySet($payload)
        );
        $this->assertRequest(
            'PUT',
            '/_plugins/_search_relevance/search_configurations',
            $payload,
            $factory->createSearchConfiguration($payload)
        );
        $this->assertRequest(
            'PUT',
            '/_plugins/_search_relevance/judgments',
            $payload,
            $factory->createJudgment($payload)
        );
        $this->assertRequest(
            'PUT',
            '/_plugins/_search_relevance/experiments',
            $payload,
            $factory->createExperiment($payload)
        );
    }

    public function testCreatesReadPollValidateAndDeleteRequests(): void
    {
        $factory = new SearchRelevanceRequestFactory();
        $resources = [
            'query_sets' => [
                $factory->getQuerySet(self::RESOURCE_ID),
                $factory->deleteQuerySet(self::RESOURCE_ID),
            ],
            'search_configurations' => [
                $factory->getSearchConfiguration(self::RESOURCE_ID),
                $factory->deleteSearchConfiguration(self::RESOURCE_ID),
            ],
            'judgments' => [
                $factory->getJudgment(self::RESOURCE_ID),
                $factory->deleteJudgment(self::RESOURCE_ID),
            ],
            'experiments' => [
                $factory->getExperiment(self::RESOURCE_ID),
                $factory->deleteExperiment(self::RESOURCE_ID),
            ],
        ];

        foreach ($resources as $resource => [$read, $delete]) {
            $path = '/_plugins/_search_relevance/' . $resource . '/' . self::RESOURCE_ID;
            $this->assertRequest('GET', $path, null, $read);
            $this->assertRequest('DELETE', $path, null, $delete);
        }

        $this->assertRequest(
            'GET',
            '/_plugins/_search_relevance/experiments/' . self::RESOURCE_ID . '/validate',
            null,
            $factory->validateExperiment(self::RESOURCE_ID)
        );
        $this->assertRequest(
            'GET',
            '/_plugins/_search_relevance/stats/',
            null,
            $factory->stats()
        );
    }

    public function testCreatesBoundedSearchRequestsWithoutChangingPayloads(): void
    {
        $factory = new SearchRelevanceRequestFactory();
        $payload = ['query' => ['term' => ['name.keyword' => 'owned-resource']]];
        $requests = [
            'query_sets' => $factory->searchQuerySets($payload),
            'search_configurations' => $factory->searchSearchConfigurations($payload),
            'judgments' => $factory->searchJudgments($payload),
            'experiments' => $factory->searchExperiments($payload),
        ];

        foreach ($requests as $resource => $request) {
            $this->assertRequest(
                'POST',
                '/_plugins/_search_relevance/' . $resource . '/_search',
                $payload,
                $request
            );
        }
    }

    public function testRejectsResourceIdsThatAreNotPluginGeneratedUuids(): void
    {
        $factory = new SearchRelevanceRequestFactory();

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Search Relevance resource ID must be a UUID');

        $factory->getExperiment('../_cluster/settings');
    }

    public function testRejectsListPayloadsWherePluginRequiresAnObject(): void
    {
        $factory = new SearchRelevanceRequestFactory();

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Search Relevance request body must be a JSON object');

        $factory->createQuerySet([['queryText' => 'boots']]);
    }

    public function testRejectsIntegerKeysInObjectPayloads(): void
    {
        $factory = new SearchRelevanceRequestFactory();

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Search Relevance request body must be a JSON object');

        $factory->createQuerySet([2 => ['queryText' => 'boots']]);
    }

    private function assertRequest(
        string $method,
        string $path,
        ?array $body,
        SearchRelevanceRequest $request
    ): void {
        self::assertSame($method, $request->getMethod());
        self::assertSame($path, $request->getPath());
        self::assertSame($body, $request->getBody());
    }
}
