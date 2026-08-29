<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Experiment;

use InvalidArgumentException;

class ProductMovementClassifier
{
    /**
     * @param array<array-key, mixed> $baselineDocumentIds
     * @param array<array-key, mixed> $candidateDocumentIds
     * @param array<string, array{name: string, sku: string}> $productContext
     * @return list<array{
     *     document_id: string,
     *     name: string,
     *     sku: string,
     *     available: bool,
     *     baseline_rank: int|null,
     *     candidate_rank: int|null,
     *     movement: string,
     *     rank_delta: int|null
     * }>
     */
    public function classify(
        array $baselineDocumentIds,
        array $candidateDocumentIds,
        array $productContext
    ): array {
        $baselineDocumentIds = $this->normalizeDocumentIds($baselineDocumentIds);
        $candidateDocumentIds = $this->normalizeDocumentIds($candidateDocumentIds);
        $baselineRanks = $this->ranks($baselineDocumentIds);
        $candidateRanks = $this->ranks($candidateDocumentIds);
        $orderedDocumentIds = array_values(array_unique(array_merge(
            $candidateDocumentIds,
            $baselineDocumentIds
        )));
        $rows = [];

        foreach ($orderedDocumentIds as $documentId) {
            $baselineRank = $baselineRanks[$documentId] ?? null;
            $candidateRank = $candidateRanks[$documentId] ?? null;
            $context = $productContext[$documentId] ?? null;
            $available = is_array($context);
            [$movement, $rankDelta] = $this->movement($baselineRank, $candidateRank);
            $rows[] = [
                'document_id' => $documentId,
                'name' => $available ? $context['name'] : 'Product unavailable',
                'sku' => $available ? $context['sku'] : '',
                'available' => $available,
                'baseline_rank' => $baselineRank,
                'candidate_rank' => $candidateRank,
                'movement' => $movement,
                'rank_delta' => $rankDelta,
            ];
        }

        return $rows;
    }

    /**
     * @param array<array-key, mixed> $documentIds
     * @return list<string>
     */
    private function normalizeDocumentIds(array $documentIds): array
    {
        foreach ($documentIds as $documentId) {
            if (!is_string($documentId) || $documentId === '') {
                throw new InvalidArgumentException('Product movement requires non-empty document identities');
            }
        }

        return array_values(array_unique($documentIds));
    }

    /**
     * @param list<string> $documentIds
     * @return array<string, int>
     */
    private function ranks(array $documentIds): array
    {
        $ranks = [];

        foreach ($documentIds as $index => $documentId) {
            $ranks[$documentId] = $index + 1;
        }

        return $ranks;
    }

    /**
     * @return array{string, int|null}
     */
    private function movement(?int $baselineRank, ?int $candidateRank): array
    {
        if ($baselineRank === null) {
            return ['ADDED', null];
        }

        if ($candidateRank === null) {
            return ['DROPPED', null];
        }

        $delta = $baselineRank - $candidateRank;

        if ($delta > 0) {
            return ['MOVED_UP', $delta];
        }

        if ($delta < 0) {
            return ['MOVED_DOWN', $delta];
        }

        return ['UNCHANGED', 0];
    }
}
