<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch;

use InvalidArgumentException;
use JsonException;
use LengthException;
use MageOS\OpenSearchRelevanceWorkbench\Api\SearchRelevanceClientInterface;
use OpenSearch\Exception\OpenSearchExceptionInterface;
use UnexpectedValueException;

class SearchRelevanceClient implements SearchRelevanceClientInterface
{
    private const DEFAULT_CONNECT_TIMEOUT_SECONDS = 5;
    private const DEFAULT_MAX_REQUEST_BYTES = 2_097_152;
    private const DEFAULT_MAX_RESPONSE_BYTES = 16_777_216;
    private const DEFAULT_OVERALL_TIMEOUT_SECONDS = 30;

    public function __construct(
        private readonly ConfiguredOpenSearchClientProvider $clientProvider,
        private readonly \MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\SearchRelevanceRequestFactory $requestFactory,
        private readonly int $maxRequestBytes = self::DEFAULT_MAX_REQUEST_BYTES,
        private readonly int $maxResponseBytes = self::DEFAULT_MAX_RESPONSE_BYTES,
        private readonly int $connectTimeoutSeconds = self::DEFAULT_CONNECT_TIMEOUT_SECONDS,
        private readonly int $overallTimeoutSeconds = self::DEFAULT_OVERALL_TIMEOUT_SECONDS
    ) {
        if (
            $this->maxRequestBytes < 1
            || $this->maxResponseBytes < 1
            || $this->connectTimeoutSeconds < 1
            || $this->overallTimeoutSeconds < 1
        ) {
            throw new InvalidArgumentException('Search Relevance limits must be positive integers');
        }
    }

    /** @inheritDoc */
    public function createQuerySet(array $body): array
    {
        return $this->execute($this->requestFactory->createQuerySet($body));
    }

    /** @inheritDoc */
    public function getQuerySet(string $resourceId): array
    {
        return $this->execute($this->requestFactory->getQuerySet($resourceId));
    }

    /** @inheritDoc */
    public function searchQuerySets(array $body): array
    {
        return $this->execute($this->requestFactory->searchQuerySets($body));
    }

    /** @inheritDoc */
    public function deleteQuerySet(string $resourceId): array
    {
        return $this->execute($this->requestFactory->deleteQuerySet($resourceId));
    }

    /** @inheritDoc */
    public function createSearchConfiguration(array $body): array
    {
        return $this->execute($this->requestFactory->createSearchConfiguration($body));
    }

    /** @inheritDoc */
    public function getSearchConfiguration(string $resourceId): array
    {
        return $this->execute($this->requestFactory->getSearchConfiguration($resourceId));
    }

    /** @inheritDoc */
    public function searchSearchConfigurations(array $body): array
    {
        return $this->execute($this->requestFactory->searchSearchConfigurations($body));
    }

    /** @inheritDoc */
    public function deleteSearchConfiguration(string $resourceId): array
    {
        return $this->execute($this->requestFactory->deleteSearchConfiguration($resourceId));
    }

    /** @inheritDoc */
    public function createJudgment(array $body): array
    {
        return $this->execute($this->requestFactory->createJudgment($body));
    }

    /** @inheritDoc */
    public function getJudgment(string $resourceId): array
    {
        return $this->execute($this->requestFactory->getJudgment($resourceId));
    }

    /** @inheritDoc */
    public function searchJudgments(array $body): array
    {
        return $this->execute($this->requestFactory->searchJudgments($body));
    }

    /** @inheritDoc */
    public function deleteJudgment(string $resourceId): array
    {
        return $this->execute($this->requestFactory->deleteJudgment($resourceId));
    }

    /** @inheritDoc */
    public function createExperiment(array $body): array
    {
        return $this->execute($this->requestFactory->createExperiment($body));
    }

    /** @inheritDoc */
    public function getExperiment(string $resourceId): array
    {
        return $this->execute($this->requestFactory->getExperiment($resourceId));
    }

    /** @inheritDoc */
    public function searchExperiments(array $body): array
    {
        return $this->execute($this->requestFactory->searchExperiments($body));
    }

    /** @inheritDoc */
    public function deleteExperiment(string $resourceId): array
    {
        return $this->execute($this->requestFactory->deleteExperiment($resourceId));
    }

    /** @inheritDoc */
    public function validateExperiment(string $resourceId): array
    {
        return $this->execute($this->requestFactory->validateExperiment($resourceId));
    }

    /** @inheritDoc */
    public function stats(): array
    {
        return $this->execute($this->requestFactory->stats());
    }

    /**
     * @return array<string, mixed>
     */
    private function execute(SearchRelevanceRequest $request): array
    {
        $attributes = [
            'options' => [
                'headers' => [
                    'client' => [
                        'connect_timeout' => $this->connectTimeoutSeconds,
                        'timeout' => $this->overallTimeoutSeconds,
                    ],
                ],
            ],
        ];

        if ($request->getBody() !== null) {
            $this->assertJsonByteLimit(
                $request->getBody(),
                $this->maxRequestBytes,
                'Search Relevance request exceeds the configured byte limit'
            );
            $attributes['body'] = $request->getBody();
        }

        try {
            $response = $this->clientProvider->get()->request(
                $request->getMethod(),
                $request->getPath(),
                $attributes
            );
        } catch (OpenSearchExceptionInterface $exception) {
            throw SearchRelevanceTransportException::fromOpenSearch($exception);
        }

        $normalizedResponse = $this->normalizeResponse($response);
        $this->assertJsonByteLimit(
            $normalizedResponse,
            $this->maxResponseBytes,
            'Search Relevance response exceeds the configured byte limit'
        );

        return $normalizedResponse;
    }

    /**
     * @return array<string, mixed>
     */
    private function normalizeResponse(mixed $response): array
    {
        if (!is_array($response) || array_is_list($response)) {
            throw new UnexpectedValueException('Search Relevance response must be a JSON object');
        }

        $objectResponse = [];

        foreach ($response as $key => $value) {
            if (!is_string($key)) {
                throw new UnexpectedValueException('Search Relevance response must be a JSON object');
            }

            $objectResponse[$key] = $value;
        }

        return $objectResponse;
    }

    private function assertJsonByteLimit(mixed $payload, int $byteLimit, string $message): void
    {
        try {
            $encodedPayload = json_encode($payload, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
        } catch (JsonException $exception) {
            throw new InvalidArgumentException('Search Relevance payload must contain valid JSON values', 0, $exception);
        }

        if (strlen($encodedPayload) > $byteLimit) {
            throw new LengthException($message);
        }
    }
}
