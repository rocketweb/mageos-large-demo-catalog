<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Experiment;

class EvidenceReport
{
    /**
     * @param list<array<string, bool|float|string|int|list<string>>> $perQueryEvidence
     * @param list<string> $reasonCodes
     */
    public function __construct(
        private readonly string $primaryMetric,
        private readonly float $baselineMetric,
        private readonly float $candidateMetric,
        private readonly float $metricDelta,
        private readonly float $judgedCoverage,
        private readonly array $perQueryEvidence,
        private readonly string $eligibility,
        private readonly array $reasonCodes
    ) {
    }

    public function getPrimaryMetric(): string
    {
        return $this->primaryMetric;
    }

    public function getBaselineMetric(): float
    {
        return $this->baselineMetric;
    }

    public function getCandidateMetric(): float
    {
        return $this->candidateMetric;
    }

    public function getMetricDelta(): float
    {
        return $this->metricDelta;
    }

    public function getJudgedCoverage(): float
    {
        return $this->judgedCoverage;
    }

    /**
     * @return list<array<string, bool|float|string|int|list<string>>>
     */
    public function getPerQueryEvidence(): array
    {
        return $this->perQueryEvidence;
    }

    public function getEligibility(): string
    {
        return $this->eligibility;
    }

    /**
     * @return list<string>
     */
    public function getReasonCodes(): array
    {
        return $this->reasonCodes;
    }
}
