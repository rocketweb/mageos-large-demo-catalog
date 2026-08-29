<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot;

class QuerySnapshotEntry
{
    /**
     * @var array<string, array{value: string, provenance: string}>
     */
    private readonly array $customFields;

    /**
     * @param array<array-key, mixed> $customFields
     */
    public function __construct(
        private readonly int $sourceQueryId,
        private readonly string $queryText,
        private readonly string $queryHash,
        private readonly int $popularity,
        private readonly int $resultCount,
        private readonly string $sourceUpdatedAt,
        array $customFields = []
    ) {
        $validatedFields = [];

        foreach ($customFields as $field => $metadata) {
            if (
                !in_array($field, ['brand_value', 'category_id'], true)
                || !is_array($metadata)
                || !is_string($metadata['value'] ?? null)
                || $metadata['value'] === ''
                || ($metadata['provenance'] ?? null) !== 'MERCHANT_CURATED'
            ) {
                throw new \InvalidArgumentException('Query snapshot custom-field provenance is invalid');
            }

            $validatedFields[$field] = [
                'value' => $metadata['value'],
                'provenance' => $metadata['provenance'],
            ];
        }

        $this->customFields = $validatedFields;
    }

    public function getSourceQueryId(): int
    {
        return $this->sourceQueryId;
    }

    public function getQueryText(): string
    {
        return $this->queryText;
    }

    public function getQueryHash(): string
    {
        return $this->queryHash;
    }

    public function getPopularity(): int
    {
        return $this->popularity;
    }

    public function getResultCount(): int
    {
        return $this->resultCount;
    }

    public function getSourceUpdatedAt(): string
    {
        return $this->sourceUpdatedAt;
    }

    /**
     * @return array<string, array{value: string, provenance: string}>
     */
    public function getCustomFields(): array
    {
        return $this->customFields;
    }

    /**
     * @return array{queryText: string, customFields?: array<string, string>}
     */
    public function toRemoteQuerySetEntry(): array
    {
        $entry = ['queryText' => $this->queryText];

        if ($this->customFields !== []) {
            $entry['customFields'] = array_map(
                static fn (array $metadata): string => $metadata['value'],
                $this->customFields
            );
        }

        return $entry;
    }

    /**
     * @param array<string, array{value: string, provenance: string}> $customFields
     */
    public function withCustomFields(array $customFields): self
    {
        return new self(
            $this->sourceQueryId,
            $this->queryText,
            $this->queryHash,
            $this->popularity,
            $this->resultCount,
            $this->sourceUpdatedAt,
            $customFields
        );
    }

    /**
     * @return array{
     *     source_query_id: int,
     *     query_text: string,
     *     query_hash: string,
     *     popularity: int,
     *     result_count: int,
     *     source_updated_at: string,
     *     custom_fields: array<string, array{value: string, provenance: string}>
     * }
     */
    public function toCanonicalArray(): array
    {
        return [
            'source_query_id' => $this->sourceQueryId,
            'query_text' => $this->queryText,
            'query_hash' => $this->queryHash,
            'popularity' => $this->popularity,
            'result_count' => $this->resultCount,
            'source_updated_at' => $this->sourceUpdatedAt,
            'custom_fields' => $this->customFields,
        ];
    }
}
