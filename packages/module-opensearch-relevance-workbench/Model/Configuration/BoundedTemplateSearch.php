<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Configuration;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\ConfiguredOpenSearchClientProvider;
use UnexpectedValueException;

class BoundedTemplateSearch
{
    private const MAX_REQUEST_BYTES = 1_048_576;
    private const MAX_RESULT_SIZE = 20;

    public function __construct(
        private readonly ConfiguredOpenSearchClientProvider $clientProvider,
        private readonly CanonicalJson $canonicalJson
    ) {
    }

    /**
     * @return array{
     *     request_hash: string,
     *     total: int,
     *     hits: list<array{document_id: string, score: float|null}>
     * }
     */
    public function execute(
        BaselineTemplate $template,
        string $queryText,
        string $physicalIndex,
        int $resultSize
    ): array {
        if ($resultSize < 1 || $resultSize > self::MAX_RESULT_SIZE) {
            throw new InvalidArgumentException('Search result size must be between 1 and 20');
        }

        $request = $template->render($queryText);
        $body = $request['body'] ?? null;

        if (!is_array($body)) {
            throw new UnexpectedValueException('Search template has no request body');
        }

        $capturedSize = $body['size'] ?? null;

        if (!is_int($capturedSize) || $capturedSize < 1 || $capturedSize > self::MAX_RESULT_SIZE) {
            throw new UnexpectedValueException('Search template result size is outside the validation bound');
        }

        $legacyType = $request['type'] ?? null;

        if ($legacyType !== null && $legacyType !== 'document') {
            throw new UnexpectedValueException('Search template contains an unknown legacy document type');
        }

        unset($request['type']);
        $request['index'] = $physicalIndex;
        $request['body']['size'] = min($capturedSize, $resultSize);
        $encodedRequest = $this->canonicalJson->encode($request);

        if (strlen($encodedRequest) > self::MAX_REQUEST_BYTES) {
            throw new UnexpectedValueException('Search request exceeds the validation byte limit');
        }

        $response = $this->clientProvider->get()->search($request + [
            'client' => ['connect_timeout' => 3, 'timeout' => 10],
        ]);
        $resultCount = $response['hits']['total']['value'] ?? null;
        $responseHits = $response['hits']['hits'] ?? null;

        if (!is_int($resultCount) || $resultCount < 0 || !is_array($responseHits)) {
            throw new UnexpectedValueException('Search validation returned no bounded hit result');
        }

        $hits = [];

        foreach (array_slice($responseHits, 0, $resultSize) as $hit) {
            $documentId = $hit['_id'] ?? null;

            if ($documentId === null) {
                $fieldIds = $hit['fields']['_id'] ?? null;
                $documentId = is_array($fieldIds) ? ($fieldIds[0] ?? null) : null;
            }
            $score = $hit['_score'] ?? null;

            if ((!is_string($documentId) && !is_int($documentId)) || (string)$documentId === '') {
                throw new UnexpectedValueException(sprintf(
                    'Search validation returned an invalid document identity of type %s',
                    get_debug_type($documentId)
                ));
            }

            if ($score !== null && !is_int($score) && !is_float($score)) {
                throw new UnexpectedValueException('Search validation returned an invalid document score');
            }

            $hits[] = [
                'document_id' => (string)$documentId,
                'score' => $score === null ? null : (float)$score,
            ];
        }

        return [
            'request_hash' => hash('sha256', $encodedRequest),
            'total' => $resultCount,
            'hits' => $hits,
        ];
    }
}
