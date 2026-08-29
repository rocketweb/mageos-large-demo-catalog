<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot;

use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use Normalizer;

class QuerySnapshotPreviewer
{
    public function __construct(
        private readonly PrivacyDetector $privacyDetector,
        private readonly CanonicalJson $canonicalJson
    ) {
    }

    /**
     * @param list<array<string, int|string|null>> $sourceRows
     * @param array<string, array<string, array{value: string, provenance: string}>> $metadataByQueryHash
     */
    public function preview(
        int $storeId,
        array $sourceRows,
        SnapshotPolicy $policy,
        array $metadataByQueryHash = []
    ): QuerySnapshotPreview {
        $storeRows = array_values(array_filter(
            $sourceRows,
            static fn (array $row): bool => (int)($row['store_id'] ?? -1) === $storeId
                && (int)($row['is_active'] ?? 0) === 1
        ));
        $highWaterBoundary = $this->highWaterBoundary($storeRows);
        $excludedCounts = [];
        $positiveEntries = [];
        $zeroEntries = [];

        foreach ($storeRows as $row) {
            $reasonCode = $this->exclusionReason($row, $policy);

            if ($reasonCode !== null) {
                $excludedCounts[$reasonCode] = ($excludedCounts[$reasonCode] ?? 0) + 1;
                continue;
            }

            $entry = $this->createEntry($row);

            if ($entry->getResultCount() > 0) {
                $positiveEntries[] = $entry;
            } else {
                $zeroEntries[] = $entry;
            }
        }

        $this->sortEntries($positiveEntries);
        $this->sortEntries($zeroEntries);
        $positiveEntries = $this->applyStratumLimit(
            $positiveEntries,
            $policy->getPositiveResultLimit(),
            'POSITIVE_RESULT_LIMIT_REACHED',
            $excludedCounts
        );
        $zeroEntries = $this->applyStratumLimit(
            $zeroEntries,
            $policy->getZeroResultLimit(),
            'ZERO_RESULT_LIMIT_REACHED',
            $excludedCounts
        );
        $entries = array_merge($positiveEntries, $zeroEntries);

        if (count($entries) > $policy->getTotalLimit()) {
            $excludedCounts['TOTAL_LIMIT_REACHED'] = count($entries) - $policy->getTotalLimit();
            $entries = array_slice($entries, 0, $policy->getTotalLimit());
        }

        $entries = $this->applyMetadata($entries, $metadataByQueryHash);

        ksort($excludedCounts, SORT_STRING);
        $snapshotHash = $this->canonicalJson->hash([
            'store_id' => $storeId,
            'entries' => array_map(
                static fn (QuerySnapshotEntry $entry): array => $entry->toCanonicalArray(),
                $entries
            ),
            'policy' => $policy->toCanonicalArray(),
            'high_water_boundary' => $highWaterBoundary,
        ]);

        return new QuerySnapshotPreview(
            $storeId,
            count($storeRows),
            $entries,
            $excludedCounts,
            $policy,
            $highWaterBoundary,
            $snapshotHash
        );
    }

    /**
     * @param list<QuerySnapshotEntry> $entries
     * @param array<string, array<string, array{value: string, provenance: string}>> $metadataByQueryHash
     * @return list<QuerySnapshotEntry>
     */
    private function applyMetadata(array $entries, array $metadataByQueryHash): array
    {
        $selectedQueryHashes = array_fill_keys(
            array_map(static fn (QuerySnapshotEntry $entry): string => $entry->getQueryHash(), $entries),
            true
        );

        foreach (array_keys($metadataByQueryHash) as $queryHash) {
            if (!isset($selectedQueryHashes[$queryHash])) {
                throw new \InvalidArgumentException(
                    'Curated metadata must belong to a query selected by the exact preview'
                );
            }
        }

        return array_map(
            static fn (QuerySnapshotEntry $entry): QuerySnapshotEntry => $entry->withCustomFields(
                $metadataByQueryHash[$entry->getQueryHash()] ?? []
            ),
            $entries
        );
    }

    /**
     * @param array<string, int|string|null> $row
     */
    private function exclusionReason(array $row, SnapshotPolicy $policy): ?string
    {
        if ((int)($row['popularity'] ?? 0) < $policy->getMinimumPopularity()) {
            return 'BELOW_MINIMUM_POPULARITY';
        }

        if (!$policy->includesRedirects() && trim((string)($row['redirect'] ?? '')) !== '') {
            return 'REDIRECT_EXCLUDED';
        }

        $inspection = $this->privacyDetector->inspect(
            (string)($row['query_text'] ?? ''),
            $policy->getMaximumTermLength()
        );

        return $inspection->getReasonCodes()[0] ?? null;
    }

    /**
     * @param array<string, int|string|null> $row
     */
    private function createEntry(array $row): QuerySnapshotEntry
    {
        $queryText = trim((string)$row['query_text']);
        $normalized = Normalizer::normalize($queryText, Normalizer::FORM_C);
        $queryText = $normalized === false ? $queryText : $normalized;

        return new QuerySnapshotEntry(
            (int)$row['query_id'],
            $queryText,
            hash('sha256', $queryText),
            (int)$row['popularity'],
            (int)$row['num_results'],
            (string)$row['updated_at']
        );
    }

    /**
     * @param list<QuerySnapshotEntry> $entries
     */
    private function sortEntries(array &$entries): void
    {
        usort(
            $entries,
            static fn (QuerySnapshotEntry $left, QuerySnapshotEntry $right): int =>
                [$right->getPopularity(), $left->getSourceQueryId()]
                <=> [$left->getPopularity(), $right->getSourceQueryId()]
        );
    }

    /**
     * @param list<QuerySnapshotEntry> $entries
     * @param array<string, int> $excludedCounts
     * @return list<QuerySnapshotEntry>
     */
    private function applyStratumLimit(
        array $entries,
        int $limit,
        string $reasonCode,
        array &$excludedCounts
    ): array {
        if (count($entries) <= $limit) {
            return $entries;
        }

        $excludedCounts[$reasonCode] = count($entries) - $limit;

        return array_slice($entries, 0, $limit);
    }

    /**
     * @param list<array<string, int|string|null>> $rows
     * @return array{updated_at: string, query_id: int}
     */
    private function highWaterBoundary(array $rows): array
    {
        $boundary = ['updated_at' => '', 'query_id' => 0];

        foreach ($rows as $row) {
            $candidate = [
                'updated_at' => (string)($row['updated_at'] ?? ''),
                'query_id' => (int)($row['query_id'] ?? 0),
            ];

            if ([$candidate['updated_at'], $candidate['query_id']] > [$boundary['updated_at'], $boundary['query_id']]) {
                $boundary = $candidate;
            }
        }

        return $boundary;
    }
}
