<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Judgment;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;

class JudgmentCacheIdentityFactory
{
    private const SHA256_PATTERN = '/\A[0-9a-f]{64}\z/D';

    public function __construct(private readonly CanonicalJson $canonicalJson)
    {
    }

    /**
     * Raw prompt and context values are hashed here and are not retained by the identity.
     *
     * @param list<string> $contextFields
     * @param list<array<string, scalar|null>> $contextValues
     */
    public function create(
        string $modelId,
        string $prompt,
        string $ratingType,
        array $contextFields,
        array $contextValues,
        string $querySnapshotHash,
        string $searchConfigurationHash,
        string $indexEvidenceHash
    ): JudgmentCacheIdentity {
        $this->requireNonEmpty($modelId, 'Model ID');
        $this->requireNonEmpty($prompt, 'Prompt');
        $this->requireNonEmpty($ratingType, 'Rating type');
        $this->requireSha256($querySnapshotHash, 'Query snapshot hash');
        $this->requireSha256($searchConfigurationHash, 'Search configuration hash');
        $this->requireSha256($indexEvidenceHash, 'Index evidence hash');
        $contextFields = $this->normalizeContextFields($contextFields);
        $promptHash = $this->canonicalJson->hash($prompt);
        $contextValuesHash = $this->canonicalJson->hash($contextValues);
        $identity = [
            'model_id' => $modelId,
            'prompt_hash' => $promptHash,
            'rating_type' => $ratingType,
            'context_fields' => $contextFields,
            'context_values_hash' => $contextValuesHash,
            'query_snapshot_hash' => $querySnapshotHash,
            'search_configuration_hash' => $searchConfigurationHash,
            'index_evidence_hash' => $indexEvidenceHash,
        ];

        return new JudgmentCacheIdentity(
            $modelId,
            $promptHash,
            $ratingType,
            $contextFields,
            $contextValuesHash,
            $querySnapshotHash,
            $searchConfigurationHash,
            $indexEvidenceHash,
            $this->canonicalJson->hash($identity)
        );
    }

    /**
     * @param list<string> $contextFields
     * @return list<string>
     */
    private function normalizeContextFields(array $contextFields): array
    {
        foreach ($contextFields as $contextField) {
            $this->requireNonEmpty($contextField, 'Context field');
        }

        $normalized = array_values(array_unique($contextFields));
        sort($normalized, SORT_STRING);

        return $normalized;
    }

    private function requireNonEmpty(string $value, string $label): void
    {
        if (trim($value) === '') {
            throw new InvalidArgumentException($label . ' must not be empty');
        }
    }

    private function requireSha256(string $value, string $label): void
    {
        if (preg_match(self::SHA256_PATTERN, $value) !== 1) {
            throw new InvalidArgumentException($label . ' must be a lowercase SHA-256 value');
        }
    }
}
