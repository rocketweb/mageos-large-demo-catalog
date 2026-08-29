<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch;

use LogicException;
use Magento\AdvancedSearch\Model\Client\ClientResolver;
use Magento\OpenSearch\Model\SearchClient as MageOsSearchClient;
use OpenSearch\Client;

class ConfiguredOpenSearchClientProvider
{
    private ?Client $client = null;

    public function __construct(
        private readonly ClientResolver $clientResolver
    ) {
    }

    public function get(): Client
    {
        if ($this->client !== null) {
            return $this->client;
        }

        if ($this->clientResolver->getCurrentEngine() !== 'opensearch') {
            throw new LogicException('The selected MageOS search engine is not stock OpenSearch');
        }

        $configuredClient = $this->clientResolver->create('opensearch');

        if (!$configuredClient instanceof MageOsSearchClient) {
            throw new LogicException('Configured search engine client is not the stock MageOS OpenSearch client');
        }

        $this->client = $configuredClient->getOpenSearchClient();

        return $this->client;
    }
}
