<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Experiment;

use InvalidArgumentException;

class OfflineEvidenceEvaluator
{
    /**
     * @param array<string, list<string>> $baselineRankings
     * @param array<string, list<string>> $candidateRankings
     * @param array<string, array<string, float>> $ratings
     * @param list<string> $knownItemQueryHashes
     */
    public function evaluate(
        array $baselineRankings,
        array $candidateRankings,
        array $ratings,
        int $resultDepth,
        float $minimumJudgedCoverage,
        float $minimumImprovement,
        array $knownItemQueryHashes,
        bool $indexFresh,
        bool $merchantAccepted
    ): EvidenceReport {
        if ($resultDepth < 1 || $resultDepth > 100) {
            throw new InvalidArgumentException('Evidence result depth must be between 1 and 100');
        }

        if ($minimumJudgedCoverage < 0.0 || $minimumJudgedCoverage > 1.0) {
            throw new InvalidArgumentException('Evidence coverage floor must be between 0.0 and 1.0');
        }

        $queryHashes = array_values(array_unique(array_merge(
            array_keys($baselineRankings),
            array_keys($candidateRankings)
        )));
        sort($queryHashes, SORT_STRING);

        if ($queryHashes === []) {
            throw new InvalidArgumentException('Evidence requires at least one query');
        }

        $perQuery = [];
        $baselineTotal = 0.0;
        $candidateTotal = 0.0;
        $judgedPairs = 0;
        $totalPairs = 0;
        $knownItemRegression = false;

        foreach ($queryHashes as $queryHash) {
            $queryRatings = $ratings[$queryHash] ?? [];
            $baseline = array_slice($baselineRankings[$queryHash] ?? [], 0, $resultDepth);
            $candidate = array_slice($candidateRankings[$queryHash] ?? [], 0, $resultDepth);
            $union = array_values(array_unique(array_merge($baseline, $candidate)));

            foreach ($union as $documentId) {
                $totalPairs++;

                if (array_key_exists($documentId, $queryRatings)) {
                    $judgedPairs++;
                }
            }

            $baselineMetric = $this->ndcg($baseline, $queryRatings, min(10, $resultDepth));
            $candidateMetric = $this->ndcg($candidate, $queryRatings, min(10, $resultDepth));
            $queryKnownItemRegression = in_array($queryHash, $knownItemQueryHashes, true)
                && $this->knownItemRegressed($baseline, $candidate, $queryRatings);
            $baselineTotal += $baselineMetric;
            $candidateTotal += $candidateMetric;
            $perQuery[] = [
                'query_hash' => $queryHash,
                'baseline_ndcg_at_10' => $baselineMetric,
                'candidate_ndcg_at_10' => $candidateMetric,
                'delta' => $candidateMetric - $baselineMetric,
                'judged_union_count' => count(array_intersect($union, array_keys($queryRatings))),
                'union_count' => count($union),
                'known_item_regression' => $queryKnownItemRegression,
                'baseline_document_ids' => $baseline,
                'candidate_document_ids' => $candidate,
            ];

            $knownItemRegression = $knownItemRegression || $queryKnownItemRegression;
        }

        $queryCount = count($queryHashes);
        $baselineMetric = $baselineTotal / $queryCount;
        $candidateMetric = $candidateTotal / $queryCount;
        $metricDelta = $candidateMetric - $baselineMetric;
        $coverage = $totalPairs === 0 ? 0.0 : $judgedPairs / $totalPairs;
        [$eligibility, $reasonCodes] = $this->eligibility(
            $indexFresh,
            $coverage,
            $minimumJudgedCoverage,
            $merchantAccepted,
            $knownItemRegression,
            $metricDelta,
            $minimumImprovement
        );

        return new EvidenceReport(
            'NDCG@10',
            $baselineMetric,
            $candidateMetric,
            $metricDelta,
            $coverage,
            $perQuery,
            $eligibility,
            $reasonCodes
        );
    }

    /**
     * @param list<string> $ranking
     * @param array<string, float> $ratings
     */
    private function ndcg(array $ranking, array $ratings, int $depth): float
    {
        $dcg = 0.0;

        foreach (array_slice($ranking, 0, $depth) as $index => $documentId) {
            $rating = $ratings[$documentId] ?? 0.0;
            $dcg += (2 ** $rating - 1) / log($index + 2, 2);
        }

        $idealRatings = array_values($ratings);
        rsort($idealRatings, SORT_NUMERIC);
        $idealDcg = 0.0;

        foreach (array_slice($idealRatings, 0, $depth) as $index => $rating) {
            $idealDcg += (2 ** $rating - 1) / log($index + 2, 2);
        }

        return $idealDcg === 0.0 ? 0.0 : $dcg / $idealDcg;
    }

    /**
     * @param list<string> $baseline
     * @param list<string> $candidate
     * @param array<string, float> $ratings
     */
    private function knownItemRegressed(array $baseline, array $candidate, array $ratings): bool
    {
        if ($ratings === []) {
            return false;
        }

        $maximumRating = max($ratings);
        $bestDocuments = array_keys(array_filter(
            $ratings,
            static fn (float $rating): bool => $rating === $maximumRating
        ));
        $baselineRank = $this->bestRank($baseline, $bestDocuments);
        $candidateRank = $this->bestRank($candidate, $bestDocuments);

        return $candidateRank > $baselineRank;
    }

    /**
     * @param list<string> $ranking
     * @param list<string> $documents
     */
    private function bestRank(array $ranking, array $documents): int
    {
        $bestRank = PHP_INT_MAX;

        foreach ($documents as $documentId) {
            $rank = array_search($documentId, $ranking, true);

            if (is_int($rank)) {
                $bestRank = min($bestRank, $rank + 1);
            }
        }

        return $bestRank;
    }

    /**
     * @return array{string, list<string>}
     */
    private function eligibility(
        bool $indexFresh,
        float $coverage,
        float $minimumCoverage,
        bool $merchantAccepted,
        bool $knownItemRegression,
        float $metricDelta,
        float $minimumImprovement
    ): array {
        if (!$indexFresh) {
            return ['STALE', ['INDEX_EVIDENCE_CHANGED']];
        }

        if ($coverage < $minimumCoverage) {
            return ['PARTIAL', ['JUDGED_COVERAGE_BELOW_FLOOR']];
        }

        if ($knownItemRegression) {
            return ['INCONCLUSIVE', ['KNOWN_ITEM_REGRESSION']];
        }

        if ($metricDelta < $minimumImprovement) {
            return ['INCONCLUSIVE', ['PRIMARY_METRIC_THRESHOLD_NOT_MET']];
        }

        if (!$merchantAccepted) {
            return ['EXPLORATORY', ['MERCHANT_ACCEPTANCE_REQUIRED']];
        }

        return ['WINNER', []];
    }
}
