<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Experiment;

use MageOS\OpenSearchRelevanceWorkbench\Api\IndexEvidenceCaptureInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\ProductContextProvider;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use RuntimeException;
use Throwable;
use UnexpectedValueException;

class ExperimentEvidenceService
{
    private const CONTEXT_BATCH_SIZE = 100;

    public function __construct(
        private readonly ExperimentRepository $experimentRepository,
        private readonly QuerySnapshotRepository $snapshotRepository,
        private readonly BaselineConfigurationRepository $baselineRepository,
        private readonly IndexEvidenceCaptureInterface $indexEvidenceCapture,
        private readonly ProductContextProvider $productContextProvider,
        private readonly ProductMovementClassifier $movementClassifier
    ) {
    }

    /**
     * @return array<string, mixed>
     */
    public function build(string $experimentUuid): array
    {
        $experiment = $this->experimentRepository->getCompleted($experimentUuid);
        $identities = $experiment->getInputIdentities();
        $snapshotUuid = $this->identity($identities, 'query_snapshot_id');
        $baselineUuid = $this->identity($identities, 'baseline_configuration_uuid');
        $snapshot = $this->snapshotRepository->getApproved($snapshotUuid);
        $baseline = $this->baselineRepository->get($baselineUuid);
        $this->assertFrozenInputs($experiment, $snapshot->getSnapshotHash(), $baseline);
        $queryTextByHash = [];

        foreach ($snapshot->getEntries() as $entry) {
            $queryTextByHash[$entry->getQueryHash()] = $entry->getQueryText();
        }

        $documentIds = $this->documentIds($experiment->getEvidence()->getPerQueryEvidence());
        [$productContext, $productContextState] = $this->productContext(
            $baseline->getPhysicalIndex(),
            $documentIds
        );
        $queries = [];
        $regressions = [];

        foreach ($experiment->getEvidence()->getPerQueryEvidence() as $entry) {
            $queryHash = $entry['query_hash'] ?? null;

            if (!is_string($queryHash) || !isset($queryTextByHash[$queryHash])) {
                throw new UnexpectedValueException('Experiment query evidence is not part of its frozen snapshot');
            }

            $baselineIds = $this->documentIdList($entry['baseline_document_ids'] ?? []);
            $candidateIds = $this->documentIdList($entry['candidate_document_ids'] ?? []);
            $delta = $this->floatValue($entry['delta'] ?? null, 'delta');
            $knownItemRegression = ($entry['known_item_regression'] ?? false) === true;
            $detail = $entry + [
                'query_text' => $queryTextByHash[$queryHash],
                'is_regression' => $knownItemRegression || $delta < 0.0,
                'products' => $this->movementClassifier->classify(
                    $baselineIds,
                    $candidateIds,
                    $productContext
                ),
            ];
            $queries[] = $detail;

            if ($detail['is_regression'] === true) {
                $regressions[] = $detail;
            }
        }

        return [
            'experiment_uuid' => $experiment->getExperimentUuid(),
            'state' => $experiment->getState(),
            'eligibility' => $experiment->getEvidence()->getEligibility(),
            'index_state' => $this->indexState($baseline->getTargetAlias(), $baseline->getIndexEvidenceHash()),
            'product_context_state' => $productContextState,
            'queries' => $queries,
            'regressions' => $regressions,
        ];
    }

    /**
     * @param array<string, float|int|string> $identities
     */
    private function identity(array $identities, string $key): string
    {
        $value = $identities[$key] ?? null;

        if (!is_string($value) || $value === '') {
            throw new UnexpectedValueException('Experiment is missing frozen identity ' . $key);
        }

        return $value;
    }

    private function assertFrozenInputs(
        PersistedExperiment $experiment,
        string $snapshotHash,
        \MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\PersistedBaselineConfiguration $baseline
    ): void {
        $identities = $experiment->getInputIdentities();

        if (
            $experiment->getStoreId() !== $baseline->getStoreId()
            || !hash_equals($this->identity($identities, 'query_snapshot_sha256'), $snapshotHash)
            || !hash_equals(
                $this->identity($identities, 'baseline_configuration_sha256'),
                $baseline->getConfigurationHash()
            )
            || !hash_equals(
                $this->identity($identities, 'index_evidence_sha256'),
                $baseline->getIndexEvidenceHash()
            )
        ) {
            throw new RuntimeException('Experiment evidence no longer matches its frozen local inputs');
        }
    }

    /**
     * @param list<array<string, bool|float|string|int|list<string>>> $perQueryEvidence
     * @return list<string>
     */
    private function documentIds(array $perQueryEvidence): array
    {
        $documentIds = [];

        foreach ($perQueryEvidence as $entry) {
            $documentIds = array_merge(
                $documentIds,
                $this->documentIdList($entry['baseline_document_ids'] ?? []),
                $this->documentIdList($entry['candidate_document_ids'] ?? [])
            );
        }

        return array_values(array_unique($documentIds));
    }

    /**
     * @return list<string>
     */
    private function documentIdList(mixed $value): array
    {
        if (!is_array($value) || !array_is_list($value)) {
            throw new UnexpectedValueException('Experiment ranking evidence is invalid');
        }

        foreach ($value as $documentId) {
            if (!is_string($documentId) || $documentId === '') {
                throw new UnexpectedValueException('Experiment document identity is invalid');
            }
        }

        return $value;
    }

    /**
     * @param list<string> $documentIds
     * @return array{array<string, array{name: string, sku: string}>, string}
     */
    private function productContext(string $physicalIndex, array $documentIds): array
    {
        if ($documentIds === []) {
            return [[], 'NOT_RECORDED'];
        }

        $context = [];

        try {
            foreach (array_chunk($documentIds, self::CONTEXT_BATCH_SIZE) as $batch) {
                $context += $this->productContextProvider->get($physicalIndex, $batch);
            }
        } catch (Throwable) {
            return [[], 'UNAVAILABLE'];
        }

        return [$context, count($context) === count($documentIds) ? 'AVAILABLE' : 'PARTIAL'];
    }

    private function indexState(string $targetAlias, string $expectedHash): string
    {
        try {
            $current = $this->indexEvidenceCapture->capture($targetAlias);

            return hash_equals($expectedHash, $current->getEvidenceHash()) ? 'FRESH' : 'STALE';
        } catch (Throwable) {
            return 'UNAVAILABLE';
        }
    }

    private function floatValue(mixed $value, string $field): float
    {
        if (!is_int($value) && !is_float($value)) {
            throw new UnexpectedValueException('Experiment evidence field is invalid: ' . $field);
        }

        return (float)$value;
    }
}
