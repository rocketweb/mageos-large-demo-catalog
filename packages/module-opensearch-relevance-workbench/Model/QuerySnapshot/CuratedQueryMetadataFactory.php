<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot;

use InvalidArgumentException;
use Normalizer;

class CuratedQueryMetadataFactory
{
    private const QUERY_HASH_PATTERN = '/\A[0-9a-f]{64}\z/D';
    private const ALLOWED_FIELDS = ['brand_value', 'category_id'];
    private const PROVENANCE = 'MERCHANT_CURATED';

    /**
     * @param array<array-key, mixed> $input
     * @return array<string, array<string, array{value: string, provenance: string}>>
     */
    public function create(array $input): array
    {
        $metadata = [];

        foreach ($input as $queryHash => $fields) {
            if (
                !is_string($queryHash)
                || preg_match(self::QUERY_HASH_PATTERN, $queryHash) !== 1
                || !is_array($fields)
                || array_is_list($fields)
            ) {
                throw new InvalidArgumentException('Curated metadata requires an exact query hash and field object');
            }

            foreach ($fields as $field => $value) {
                if (!is_string($field) || !in_array($field, self::ALLOWED_FIELDS, true)) {
                    throw new InvalidArgumentException('Curated query metadata field is not allowlisted');
                }

                if (!is_string($value) && !is_int($value)) {
                    throw new InvalidArgumentException('Curated query metadata must contain scalar text values');
                }

                $normalizedValue = $this->normalize((string)$value);

                if ($normalizedValue === '') {
                    continue;
                }

                $this->validateValue($field, $normalizedValue);
                $metadata[$queryHash][$field] = [
                    'value' => $normalizedValue,
                    'provenance' => self::PROVENANCE,
                ];
            }

            if (isset($metadata[$queryHash])) {
                ksort($metadata[$queryHash], SORT_STRING);
            }
        }

        ksort($metadata, SORT_STRING);

        return $metadata;
    }

    private function normalize(string $value): string
    {
        $value = trim($value);
        $normalized = Normalizer::normalize($value, Normalizer::FORM_C);

        return $normalized === false ? $value : $normalized;
    }

    private function validateValue(string $field, string $value): void
    {
        if (preg_match('/[\x00-\x1F\x7F]/u', $value) === 1 || mb_strlen($value) > 128) {
            throw new InvalidArgumentException('Curated query metadata value is unsafe or too long');
        }

        if ($field === 'category_id' && preg_match('/\A[1-9][0-9]{0,19}\z/D', $value) !== 1) {
            throw new InvalidArgumentException('Curated category identity must be a positive decimal string');
        }
    }
}
