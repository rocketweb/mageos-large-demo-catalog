<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\OpenSearch;

use LogicException;
use Magento\AdvancedSearch\Model\Client\ClientInterface;
use Magento\AdvancedSearch\Model\Client\ClientResolver;
use Magento\OpenSearch\Model\SearchClient as MageOsSearchClient;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\ConfiguredOpenSearchClientProvider;
use OpenSearch\Client;
use PHPUnit\Framework\TestCase;

class ConfiguredOpenSearchClientProviderTest extends TestCase
{
    public function testResolvesConfiguredStockOpenSearchClient(): void
    {
        $openSearchClient = $this->createStub(Client::class);
        $mageOsSearchClient = $this->createStub(MageOsSearchClient::class);
        $mageOsSearchClient
            ->method('getOpenSearchClient')
            ->willReturn($openSearchClient);
        $clientResolver = $this->createMock(ClientResolver::class);
        $clientResolver
            ->method('getCurrentEngine')
            ->willReturn('opensearch');
        $clientResolver
            ->expects($this->once())
            ->method('create')
            ->with('opensearch')
            ->willReturn($mageOsSearchClient);

        $provider = new ConfiguredOpenSearchClientProvider($clientResolver);

        self::assertSame($openSearchClient, $provider->get());
        self::assertSame($openSearchClient, $provider->get());
    }

    public function testRejectsUnexpectedClientImplementation(): void
    {
        $clientResolver = $this->createStub(ClientResolver::class);
        $clientResolver
            ->method('getCurrentEngine')
            ->willReturn('opensearch');
        $clientResolver
            ->method('create')
            ->willReturn($this->createStub(ClientInterface::class));

        $this->expectException(LogicException::class);
        $this->expectExceptionMessage('Configured search engine client is not the stock MageOS OpenSearch client');

        (new ConfiguredOpenSearchClientProvider($clientResolver))->get();
    }

    public function testRejectsNonStockSelectedSearchEngine(): void
    {
        $clientResolver = $this->createMock(ClientResolver::class);
        $clientResolver
            ->expects($this->once())
            ->method('getCurrentEngine')
            ->willReturn('third_party_engine');
        $clientResolver
            ->expects($this->never())
            ->method('create');

        $this->expectException(LogicException::class);
        $this->expectExceptionMessage('The selected MageOS search engine is not stock OpenSearch');

        (new ConfiguredOpenSearchClientProvider($clientResolver))->get();
    }
}
