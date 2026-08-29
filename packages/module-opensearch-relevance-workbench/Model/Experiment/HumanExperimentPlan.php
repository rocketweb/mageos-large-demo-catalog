<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Experiment;

class HumanExperimentPlan
{
    /**
     * @param array<string, array<string, int|string|list<string>>> $remotePayloads
     * @param array<string, float|int|string> $inputIdentities
     */
    public function __construct(
        private readonly array $remotePayloads,
        private readonly array $inputIdentities,
        private readonly string $inputHash,
        private readonly string $primaryMetric,
        private readonly float $minimumJudgedCoverage,
        private readonly float $minimumImprovement
    ) {
    }

    /**
     * @return array<string, array<string, int|string|list<string>>>
     */
    public function getRemotePayloads(): array
    {
        return $this->remotePayloads;
    }

    public function getInputHash(): string
    {
        return $this->inputHash;
    }

    /**
     * @return array<string, float|int|string>
     */
    public function getInputIdentities(): array
    {
        return $this->inputIdentities;
    }

    public function getPrimaryMetric(): string
    {
        return $this->primaryMetric;
    }

    public function getMinimumJudgedCoverage(): float
    {
        return $this->minimumJudgedCoverage;
    }

    public function getMinimumImprovement(): float
    {
        return $this->minimumImprovement;
    }
}
