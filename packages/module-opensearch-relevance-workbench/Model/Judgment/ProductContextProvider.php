<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Judgment;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\ConfiguredOpenSearchClientProvider;
use UnexpectedValueException;

class ProductContextProvider
{
    private const MAX_DOCUMENTS = 100;

    public function __construct(private readonly ConfiguredOpenSearchClientProvider $clientProvider)
    {
    }

    /**
     * @param list<string> $documentIds
     * @return array<string, array{name: string, sku: string}>
     */
    public function get(string $physicalIndex, array $documentIds): array
    {
        $documentIds = array_values(array_unique($documentIds, SORT_STRING));

        if ($documentIds === [] || count($documentIds) > self::MAX_DOCUMENTS) {
            throw new InvalidArgumentException('Product context requires 1 to 100 document identities');
        }

        $response = $this->clientProvider->get()->mget([
            'index' => $physicalIndex,
            '_source_includes' => ['name', 'sku'],
            'body' => ['ids' => $documentIds],
            'client' => ['connect_timeout' => 3, 'timeout' => 10],
        ]);
        $documents = $response['docs'] ?? null;

        if (!is_array($documents)) {
            throw new UnexpectedValueException('Product context lookup returned no document list');
        }

        $context = [];

        foreach ($documents as $document) {
            $documentId = is_array($document) ? ($document['_id'] ?? null) : null;
            $source = is_array($document) ? ($document['_source'] ?? null) : null;

            if (
                (!is_string($documentId) && !is_int($documentId))
                || (string)$documentId === ''
                || !is_array($source)
            ) {
                continue;
            }

            $context[(string)$documentId] = [
                'name' => $this->normalizeScalar($source['name'] ?? ''),
                'sku' => $this->normalizeScalar($source['sku'] ?? ''),
            ];
        }

        return $context;
    }

    private function normalizeScalar(mixed $value): string
    {
        return is_string($value) || is_int($value) || is_float($value)
            ? (string)$value
            : '';
    }
}
