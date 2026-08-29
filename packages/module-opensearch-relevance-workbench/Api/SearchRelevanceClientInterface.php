<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Api;

interface SearchRelevanceClientInterface
{
    /**
     * Create a manual query set.
     *
     * @param array<string, mixed> $body
     * @return array<string, mixed>
     */
    public function createQuerySet(array $body): array;

    /**
     * Retrieve a query set.
     *
     * @return array<string, mixed>
     */
    public function getQuerySet(string $resourceId): array;

    /**
     * Search query sets using a bounded plugin query.
     *
     * @param array<string, mixed> $body
     * @return array<string, mixed>
     */
    public function searchQuerySets(array $body): array;

    /**
     * Delete an owned query set.
     *
     * @return array<string, mixed>
     */
    public function deleteQuerySet(string $resourceId): array;

    /**
     * Create a search configuration.
     *
     * @param array<string, mixed> $body
     * @return array<string, mixed>
     */
    public function createSearchConfiguration(array $body): array;

    /**
     * Retrieve a search configuration.
     *
     * @return array<string, mixed>
     */
    public function getSearchConfiguration(string $resourceId): array;

    /**
     * Search configurations using a bounded plugin query.
     *
     * @param array<string, mixed> $body
     * @return array<string, mixed>
     */
    public function searchSearchConfigurations(array $body): array;

    /**
     * Delete an owned search configuration.
     *
     * @return array<string, mixed>
     */
    public function deleteSearchConfiguration(string $resourceId): array;

    /**
     * Create a judgment.
     *
     * @param array<string, mixed> $body
     * @return array<string, mixed>
     */
    public function createJudgment(array $body): array;

    /**
     * Retrieve a judgment.
     *
     * @return array<string, mixed>
     */
    public function getJudgment(string $resourceId): array;

    /**
     * Search judgments using a bounded plugin query.
     *
     * @param array<string, mixed> $body
     * @return array<string, mixed>
     */
    public function searchJudgments(array $body): array;

    /**
     * Delete an owned judgment.
     *
     * @return array<string, mixed>
     */
    public function deleteJudgment(string $resourceId): array;

    /**
     * Create an experiment.
     *
     * @param array<string, mixed> $body
     * @return array<string, mixed>
     */
    public function createExperiment(array $body): array;

    /**
     * Retrieve or poll an experiment.
     *
     * @return array<string, mixed>
     */
    public function getExperiment(string $resourceId): array;

    /**
     * Search experiments using a bounded plugin query.
     *
     * @param array<string, mixed> $body
     * @return array<string, mixed>
     */
    public function searchExperiments(array $body): array;

    /**
     * Delete an owned experiment.
     *
     * @return array<string, mixed>
     */
    public function deleteExperiment(string $resourceId): array;

    /**
     * Validate the stored inputs for an experiment.
     *
     * @return array<string, mixed>
     */
    public function validateExperiment(string $resourceId): array;

    /**
     * Read Search Relevance plugin statistics for capability probing.
     *
     * @return array<string, mixed>
     */
    public function stats(): array;
}
