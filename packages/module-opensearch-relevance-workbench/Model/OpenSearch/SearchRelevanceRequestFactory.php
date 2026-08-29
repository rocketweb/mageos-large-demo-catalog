<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch;

use InvalidArgumentException;

class SearchRelevanceRequestFactory
{
    private const BASE_PATH = '/_plugins/_search_relevance';
    private const QUERY_SETS_PATH = self::BASE_PATH . '/query_sets';
    private const SEARCH_CONFIGURATIONS_PATH = self::BASE_PATH . '/search_configurations';
    private const JUDGMENTS_PATH = self::BASE_PATH . '/judgments';
    private const EXPERIMENTS_PATH = self::BASE_PATH . '/experiments';
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/iD';

    /**
     * @param array<string, mixed> $body
     */
    public function createQuerySet(array $body): SearchRelevanceRequest
    {
        return $this->createRequest('PUT', self::QUERY_SETS_PATH, $body);
    }

    public function getQuerySet(string $resourceId): SearchRelevanceRequest
    {
        return $this->getResource(self::QUERY_SETS_PATH, $resourceId);
    }

    /**
     * @param array<string, mixed> $body
     */
    public function searchQuerySets(array $body): SearchRelevanceRequest
    {
        return $this->searchResources(self::QUERY_SETS_PATH, $body);
    }

    public function deleteQuerySet(string $resourceId): SearchRelevanceRequest
    {
        return $this->deleteResource(self::QUERY_SETS_PATH, $resourceId);
    }

    /**
     * @param array<string, mixed> $body
     */
    public function createSearchConfiguration(array $body): SearchRelevanceRequest
    {
        return $this->createRequest('PUT', self::SEARCH_CONFIGURATIONS_PATH, $body);
    }

    public function getSearchConfiguration(string $resourceId): SearchRelevanceRequest
    {
        return $this->getResource(self::SEARCH_CONFIGURATIONS_PATH, $resourceId);
    }

    /**
     * @param array<string, mixed> $body
     */
    public function searchSearchConfigurations(array $body): SearchRelevanceRequest
    {
        return $this->searchResources(self::SEARCH_CONFIGURATIONS_PATH, $body);
    }

    public function deleteSearchConfiguration(string $resourceId): SearchRelevanceRequest
    {
        return $this->deleteResource(self::SEARCH_CONFIGURATIONS_PATH, $resourceId);
    }

    /**
     * @param array<string, mixed> $body
     */
    public function createJudgment(array $body): SearchRelevanceRequest
    {
        return $this->createRequest('PUT', self::JUDGMENTS_PATH, $body);
    }

    public function getJudgment(string $resourceId): SearchRelevanceRequest
    {
        return $this->getResource(self::JUDGMENTS_PATH, $resourceId);
    }

    /**
     * @param array<string, mixed> $body
     */
    public function searchJudgments(array $body): SearchRelevanceRequest
    {
        return $this->searchResources(self::JUDGMENTS_PATH, $body);
    }

    public function deleteJudgment(string $resourceId): SearchRelevanceRequest
    {
        return $this->deleteResource(self::JUDGMENTS_PATH, $resourceId);
    }

    /**
     * @param array<string, mixed> $body
     */
    public function createExperiment(array $body): SearchRelevanceRequest
    {
        return $this->createRequest('PUT', self::EXPERIMENTS_PATH, $body);
    }

    public function getExperiment(string $resourceId): SearchRelevanceRequest
    {
        return $this->getResource(self::EXPERIMENTS_PATH, $resourceId);
    }

    /**
     * @param array<string, mixed> $body
     */
    public function searchExperiments(array $body): SearchRelevanceRequest
    {
        return $this->searchResources(self::EXPERIMENTS_PATH, $body);
    }

    public function deleteExperiment(string $resourceId): SearchRelevanceRequest
    {
        return $this->deleteResource(self::EXPERIMENTS_PATH, $resourceId);
    }

    public function validateExperiment(string $resourceId): SearchRelevanceRequest
    {
        $path = $this->resourcePath(self::EXPERIMENTS_PATH, $resourceId) . '/validate';

        return $this->createRequest('GET', $path);
    }

    public function stats(): SearchRelevanceRequest
    {
        return $this->createRequest('GET', self::BASE_PATH . '/stats/');
    }

    private function getResource(string $resourcePath, string $resourceId): SearchRelevanceRequest
    {
        return $this->createRequest('GET', $this->resourcePath($resourcePath, $resourceId));
    }

    /**
     * @param array<string, mixed> $body
     */
    private function searchResources(string $resourcePath, array $body): SearchRelevanceRequest
    {
        return $this->createRequest('POST', $resourcePath . '/_search', $body);
    }

    private function deleteResource(string $resourcePath, string $resourceId): SearchRelevanceRequest
    {
        return $this->createRequest('DELETE', $this->resourcePath($resourcePath, $resourceId));
    }

    private function resourcePath(string $resourcePath, string $resourceId): string
    {
        if (preg_match(self::UUID_PATTERN, $resourceId) !== 1) {
            throw new InvalidArgumentException('Search Relevance resource ID must be a UUID');
        }

        return $resourcePath . '/' . strtolower($resourceId);
    }

    /**
     * @param array<string, mixed>|null $body
     */
    private function createRequest(
        string $method,
        string $path,
        ?array $body = null
    ): SearchRelevanceRequest {
        return new SearchRelevanceRequest($method, $path, $body);
    }
}
