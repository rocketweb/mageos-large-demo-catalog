<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model;

use InvalidArgumentException;
use JsonException;
use Normalizer;
use stdClass;

class CanonicalJson
{
    private const JSON_FLAGS = JSON_PRESERVE_ZERO_FRACTION
        | JSON_THROW_ON_ERROR
        | JSON_UNESCAPED_SLASHES
        | JSON_UNESCAPED_UNICODE;

    public function encode(mixed $value): string
    {
        try {
            return json_encode($this->normalize($value), self::JSON_FLAGS);
        } catch (JsonException $exception) {
            throw new InvalidArgumentException(
                'Canonical JSON accepts only valid JSON values',
                0,
                $exception
            );
        }
    }

    public function hash(mixed $value): string
    {
        return hash('sha256', $this->encode($value));
    }

    private function normalize(mixed $value): mixed
    {
        if (is_array($value)) {
            return $this->normalizeArray($value);
        }

        if (is_string($value)) {
            return $this->normalizeString($value);
        }

        if ($value === null || is_bool($value) || is_int($value)) {
            return $value;
        }

        if (is_float($value) && is_finite($value)) {
            return $value;
        }

        throw new InvalidArgumentException('Canonical JSON accepts only JSON values');
    }

    /**
     * @param array<array-key, mixed> $value
     * @return array<int, mixed>|stdClass
     */
    private function normalizeArray(array $value): array|stdClass
    {
        if (array_is_list($value)) {
            $normalizedList = [];

            foreach ($value as $item) {
                $normalizedList[] = $this->normalize($item);
            }

            return $normalizedList;
        }

        $normalizedProperties = [];

        foreach ($value as $key => $item) {
            $normalizedKey = $this->normalizeString((string)$key);

            if (array_key_exists($normalizedKey, $normalizedProperties)) {
                throw new InvalidArgumentException('Duplicate object key after Unicode normalization');
            }

            $normalizedProperties[$normalizedKey] = $this->normalize($item);
        }

        ksort($normalizedProperties, SORT_STRING);
        $normalizedObject = new stdClass();

        foreach ($normalizedProperties as $key => $item) {
            $normalizedObject->{(string)$key} = $item;
        }

        return $normalizedObject;
    }

    private function normalizeString(string $value): string
    {
        $normalized = Normalizer::normalize($value, Normalizer::FORM_C);

        if ($normalized === false) {
            throw new InvalidArgumentException('Canonical JSON contains invalid Unicode');
        }

        return $normalized;
    }
}
