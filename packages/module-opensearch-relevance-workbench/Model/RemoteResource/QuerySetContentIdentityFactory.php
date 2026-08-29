<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;

class QuerySetContentIdentityFactory
{
    public function __construct(private readonly CanonicalJson $canonicalJson)
    {
    }

    /**
     * @param array<string, mixed> $querySet
     */
    public function hash(array $querySet): string
    {
        return $this->canonicalJson->hash([
            'description' => $this->normalizedText($querySet['description'] ?? ''),
            'sampling' => $this->normalizedText($querySet['sampling'] ?? ''),
            'querySetQueries' => $this->normalizedQueries($querySet['querySetQueries'] ?? []),
        ]);
    }

    /**
     * @return list<array{queryText: string, customFields: array<string, string>}>
     */
    private function normalizedQueries(mixed $queries): array
    {
        if (!is_array($queries) || !array_is_list($queries)) {
            throw new InvalidArgumentException('Query set queries must be a list');
        }

        $normalized = [];

        foreach ($queries as $query) {
            if (!is_array($query) || !isset($query['queryText']) || !is_string($query['queryText'])) {
                throw new InvalidArgumentException('Each query set entry must contain queryText');
            }

            $normalized[] = [
                'queryText' => $query['queryText'],
                'customFields' => $this->normalizedCustomFields($query),
            ];
        }

        return $normalized;
    }

    /**
     * @param array<array-key, mixed> $query
     * @return array<string, string>
     */
    private function normalizedCustomFields(array $query): array
    {
        $fields = $query;

        if (array_key_exists('customFields', $query)) {
            $fields = $query['customFields'];

            if (!is_array($fields)) {
                throw new InvalidArgumentException('Query set customFields must be an object');
            }
        } else {
            unset($fields['queryText']);
        }

        $normalized = [];

        foreach ($fields as $name => $value) {
            if (!is_string($name) || !is_string($value)) {
                throw new InvalidArgumentException('Query set custom fields must contain strings');
            }

            $normalized[$name] = $value;
        }

        return $normalized;
    }

    private function normalizedText(mixed $value): string
    {
        if (!is_string($value)) {
            throw new InvalidArgumentException('Query set text fields must be strings');
        }

        return trim($value);
    }
}
