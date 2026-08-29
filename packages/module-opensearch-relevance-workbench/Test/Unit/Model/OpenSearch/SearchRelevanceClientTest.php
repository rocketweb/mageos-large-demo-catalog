<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\OpenSearch;

use LengthException;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\ConfiguredOpenSearchClientProvider;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\SearchRelevanceClient;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\SearchRelevanceRequestFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\SearchRelevanceTransportException;
use OpenSearch\Client;
use OpenSearch\Exception\ForbiddenHttpException;
use OpenSearch\Exception\ServiceUnavailableHttpException;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;
use UnexpectedValueException;

class SearchRelevanceClientTest extends TestCase
{
    private ConfiguredOpenSearchClientProvider $clientProvider;
    private Client&MockObject $openSearchClient;
    private SearchRelevanceClient $client;

    protected function setUp(): void
    {
        $this->clientProvider = $this->createStub(ConfiguredOpenSearchClientProvider::class);
        $this->openSearchClient = $this->getMockBuilder(Client::class)
            ->disableOriginalConstructor()
            ->onlyMethods(['request'])
            ->getMock();
        $this->clientProvider
            ->method('get')
            ->willReturn($this->openSearchClient);
        $this->client = new SearchRelevanceClient(
            $this->clientProvider,
            new SearchRelevanceRequestFactory()
        );
    }

    public function testSendsCreatePayloadUnchangedThroughMageOsClient(): void
    {
        $payload = [
            'name' => 'osrw-query-set',
            'querySetQueries' => [
                ['queryText' => 'winter boots', 'category' => 'women'],
            ],
        ];
        $response = ['query_set_id' => '7f9af483-a45a-4f1f-9d76-a7dff9715e38'];
        $this->openSearchClient
            ->expects($this->once())
            ->method('request')
            ->with(
                'PUT',
                '/_plugins/_search_relevance/query_sets',
                [
                    'options' => [
                        'headers' => [
                            'client' => [
                                'connect_timeout' => 5,
                                'timeout' => 30,
                            ],
                        ],
                    ],
                    'body' => $payload,
                ]
            )
            ->willReturn($response);

        self::assertSame($response, $this->client->createQuerySet($payload));
    }

    public function testOmitsBodyForReadAndValidationRequests(): void
    {
        $resourceId = '7f9af483-a45a-4f1f-9d76-a7dff9715e38';
        $response = ['status' => 'VALID'];
        $this->openSearchClient
            ->expects($this->once())
            ->method('request')
            ->with(
                'GET',
                '/_plugins/_search_relevance/experiments/' . $resourceId . '/validate',
                [
                    'options' => [
                        'headers' => [
                            'client' => [
                                'connect_timeout' => 5,
                                'timeout' => 30,
                            ],
                        ],
                    ],
                ]
            )
            ->willReturn($response);

        self::assertSame($response, $this->client->validateExperiment($resourceId));
    }

    public function testPassesBoundedConnectionAndOverallDeadlinesToRawTransport(): void
    {
        $response = ['status' => 'available'];
        $this->openSearchClient
            ->expects($this->once())
            ->method('request')
            ->with(
                'GET',
                '/_plugins/_search_relevance/stats/',
                [
                    'options' => [
                        'headers' => [
                            'client' => [
                                'connect_timeout' => 5,
                                'timeout' => 30,
                            ],
                        ],
                    ],
                ]
            )
            ->willReturn($response);

        self::assertSame($response, $this->client->stats());
    }

    public function testRejectsUnexpectedNonObjectResponses(): void
    {
        $this->openSearchClient
            ->expects($this->once())
            ->method('request')
            ->willReturn('not-an-object');

        $this->expectException(UnexpectedValueException::class);
        $this->expectExceptionMessage('Search Relevance response must be a JSON object');

        $this->client->stats();
    }

    public function testRejectsListResponses(): void
    {
        $this->openSearchClient
            ->expects($this->once())
            ->method('request')
            ->willReturn([['status' => 'VALID']]);

        $this->expectException(UnexpectedValueException::class);
        $this->expectExceptionMessage('Search Relevance response must be a JSON object');

        $this->client->stats();
    }

    public function testRejectsOversizedRequestBeforeCallingTransport(): void
    {
        $client = new SearchRelevanceClient(
            $this->clientProvider,
            new SearchRelevanceRequestFactory(),
            maxRequestBytes: 32
        );
        $this->openSearchClient
            ->expects($this->never())
            ->method('request');

        $this->expectException(LengthException::class);
        $this->expectExceptionMessage('Search Relevance request exceeds the configured byte limit');

        $client->createQuerySet(['name' => str_repeat('x', 64)]);
    }

    public function testRejectsOversizedResponseBeforeReturningIt(): void
    {
        $client = new SearchRelevanceClient(
            $this->clientProvider,
            new SearchRelevanceRequestFactory(),
            maxResponseBytes: 32
        );
        $this->openSearchClient
            ->expects($this->once())
            ->method('request')
            ->willReturn(['data' => str_repeat('x', 64)]);

        $this->expectException(LengthException::class);
        $this->expectExceptionMessage('Search Relevance response exceeds the configured byte limit');

        $client->stats();
    }

    public function testMapsForbiddenResponseWithoutLeakingRemotePayload(): void
    {
        $this->openSearchClient
            ->expects($this->once())
            ->method('request')
            ->willThrowException(new ForbiddenHttpException('secret query text from remote response'));

        try {
            $this->client->stats();
            self::fail('Forbidden response unexpectedly succeeded');
        } catch (SearchRelevanceTransportException $exception) {
            self::assertSame(SearchRelevanceTransportException::AUTHORIZATION_FAILED, $exception->getReasonCode());
            self::assertSame(403, $exception->getStatusCode());
            self::assertFalse($exception->isRetryable());
            self::assertStringNotContainsString('secret query text', $exception->getMessage());
        }
    }

    public function testMapsUnavailableResponseAsRetryable(): void
    {
        $this->openSearchClient
            ->expects($this->once())
            ->method('request')
            ->willThrowException(new ServiceUnavailableHttpException('upstream details'));

        try {
            $this->client->stats();
            self::fail('Unavailable response unexpectedly succeeded');
        } catch (SearchRelevanceTransportException $exception) {
            self::assertSame(SearchRelevanceTransportException::REMOTE_UNAVAILABLE, $exception->getReasonCode());
            self::assertSame(503, $exception->getStatusCode());
            self::assertTrue($exception->isRetryable());
            self::assertSame('OpenSearch Search Relevance is temporarily unavailable', $exception->getMessage());
        }
    }
}
