<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Experiment;

use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\OfflineEvidenceEvaluator;
use PHPUnit\Framework\TestCase;

class OfflineEvidenceEvaluatorTest extends TestCase
{
    public function testReportsAggregateAndPerQueryWinnerEvidence(): void
    {
        $boots = hash('sha256', 'winter boots');
        $dress = hash('sha256', 'red dress');
        $ratings = [
            $boots => ['boots-best' => 1.0, 'boots-other' => 0.5, 'gloves' => 0.0],
            $dress => ['dress-best' => 1.0, 'dress-other' => 0.5, 'shoes' => 0.0],
        ];

        $report = (new OfflineEvidenceEvaluator())->evaluate(
            baselineRankings: [
                $boots => ['gloves', 'boots-other', 'boots-best'],
                $dress => ['shoes', 'dress-other', 'dress-best'],
            ],
            candidateRankings: [
                $boots => ['boots-best', 'boots-other', 'gloves'],
                $dress => ['dress-best', 'dress-other', 'shoes'],
            ],
            ratings: $ratings,
            resultDepth: 10,
            minimumJudgedCoverage: 1.0,
            minimumImprovement: 0.05,
            knownItemQueryHashes: [$boots],
            indexFresh: true,
            merchantAccepted: true
        );

        self::assertSame('WINNER', $report->getEligibility());
        self::assertSame([], $report->getReasonCodes());
        self::assertSame(1.0, $report->getJudgedCoverage());
        self::assertGreaterThan($report->getBaselineMetric(), $report->getCandidateMetric());
        self::assertGreaterThan(0.05, $report->getMetricDelta());
        self::assertCount(2, $report->getPerQueryEvidence());
        self::assertSame('NDCG@10', $report->getPrimaryMetric());
        $perQuery = [];

        foreach ($report->getPerQueryEvidence() as $evidence) {
            $perQuery[$evidence['query_hash']] = $evidence;
        }

        self::assertSame(
            ['gloves', 'boots-other', 'boots-best'],
            $perQuery[$boots]['baseline_document_ids']
        );
        self::assertSame(
            ['boots-best', 'boots-other', 'gloves'],
            $perQuery[$boots]['candidate_document_ids']
        );
        self::assertFalse($perQuery[$boots]['known_item_regression']);
    }

    public function testStaleEvidenceCannotWin(): void
    {
        $query = hash('sha256', 'boots');
        $report = (new OfflineEvidenceEvaluator())->evaluate(
            [$query => ['bad', 'best']],
            [$query => ['best', 'bad']],
            [$query => ['best' => 1.0, 'bad' => 0.0]],
            10,
            1.0,
            0.01,
            [],
            false,
            true
        );

        self::assertSame('STALE', $report->getEligibility());
        self::assertSame(['INDEX_EVIDENCE_CHANGED'], $report->getReasonCodes());
    }

    public function testUnjudgedUnionDocumentsProducePartialEvidence(): void
    {
        $query = hash('sha256', 'boots');
        $report = (new OfflineEvidenceEvaluator())->evaluate(
            [$query => ['bad', 'best']],
            [$query => ['best', 'unrated']],
            [$query => ['best' => 1.0, 'bad' => 0.0]],
            10,
            1.0,
            0.01,
            [],
            true,
            true
        );

        self::assertSame('PARTIAL', $report->getEligibility());
        self::assertSame(['JUDGED_COVERAGE_BELOW_FLOOR'], $report->getReasonCodes());
        self::assertSame(2 / 3, $report->getJudgedCoverage());
    }

    public function testKnownItemRegressionBlocksOtherwiseImprovingCandidate(): void
    {
        $known = hash('sha256', 'known sku');
        $other = hash('sha256', 'other');
        $report = (new OfflineEvidenceEvaluator())->evaluate(
            [
                $known => ['best', 'bad'],
                $other => ['bad', 'best'],
            ],
            [
                $known => ['bad', 'best'],
                $other => ['best', 'bad'],
            ],
            [
                $known => ['best' => 1.0, 'bad' => 0.0],
                $other => ['best' => 1.0, 'bad' => 0.0],
            ],
            10,
            1.0,
            -1.0,
            [$known],
            true,
            true
        );

        self::assertSame('INCONCLUSIVE', $report->getEligibility());
        self::assertSame(['KNOWN_ITEM_REGRESSION'], $report->getReasonCodes());
        self::assertTrue($report->getPerQueryEvidence()[0]['known_item_regression']);
    }

    public function testObjectiveFailureIsReportedBeforeMerchantAcceptance(): void
    {
        $query = hash('sha256', 'boots');
        $report = (new OfflineEvidenceEvaluator())->evaluate(
            [$query => ['best', 'bad']],
            [$query => ['bad', 'best']],
            [$query => ['best' => 1.0, 'bad' => 0.0]],
            10,
            1.0,
            0.01,
            [$query],
            true,
            false
        );

        self::assertSame('INCONCLUSIVE', $report->getEligibility());
        self::assertSame(['KNOWN_ITEM_REGRESSION'], $report->getReasonCodes());
    }

    public function testOtherwiseWinningEvidenceRequiresMerchantAcceptance(): void
    {
        $query = hash('sha256', 'boots');
        $report = (new OfflineEvidenceEvaluator())->evaluate(
            [$query => ['bad', 'best']],
            [$query => ['best', 'bad']],
            [$query => ['best' => 1.0, 'bad' => 0.0]],
            10,
            1.0,
            0.01,
            [],
            true,
            false
        );

        self::assertSame('EXPLORATORY', $report->getEligibility());
        self::assertSame(['MERCHANT_ACCEPTANCE_REQUIRED'], $report->getReasonCodes());
    }
}
