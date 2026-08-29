<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Judgment;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Api\IndexEvidenceCaptureInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\BoundedTemplateSearch;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\PersistedBaselineConfiguration;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\PersistedCandidateConfiguration;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\ApprovedQuerySnapshot;
use UnexpectedValueException;

class HumanRatingQueueService
{
    private const QUERY_COUNT = 5;
    private const RESULT_DEPTH = 10;

    public function __construct(
        private readonly BoundedTemplateSearch $boundedSearch,
        private readonly ProductContextProvider $productContextProvider,
        private readonly IndexEvidenceCaptureInterface $indexEvidenceCapture
    ) {
    }

    /**
     * @return list<array{
     *     query_hash: string,
     *     query_text: string,
     *     document_id: string,
     *     name: string,
     *     sku: string,
     *     baseline_rank: int|null,
     *     candidate_rank: int|null
     * }>
     */
    public function build(
        PersistedBaselineConfiguration $baseline,
        PersistedCandidateConfiguration $candidate,
        ApprovedQuerySnapshot $snapshot
    ): array {
        $this->assertCompatibleInputs($baseline, $candidate, $snapshot);
        $freshEvidence = $this->indexEvidenceCapture->capture($baseline->getTargetAlias());

        if (!hash_equals($baseline->getIndexEvidenceHash(), $freshEvidence->getEvidenceHash())) {
            throw new UnexpectedValueException('Rating queue index evidence is stale');
        }

        $entries = array_slice($snapshot->getEntries(), 0, self::QUERY_COUNT);

        if (count($entries) < self::QUERY_COUNT) {
            throw new InvalidArgumentException('Human rating queue requires at least five approved queries');
        }

        $queue = [];
        $allDocumentIds = [];

        foreach ($entries as $entry) {
            $baselineResult = $this->boundedSearch->execute(
                $baseline->getTemplate(),
                $entry->getQueryText(),
                $baseline->getPhysicalIndex(),
                self::RESULT_DEPTH
            );
            $candidateResult = $this->boundedSearch->execute(
                $candidate->getTemplate(),
                $entry->getQueryText(),
                $candidate->getPhysicalIndex(),
                self::RESULT_DEPTH
            );
            $documents = [];

            foreach ($baselineResult['hits'] as $rank => $hit) {
                $documents['id:' . $hit['document_id']] = [
                    'document_id' => $hit['document_id'],
                    'baseline_rank' => $rank + 1,
                    'candidate_rank' => null,
                ];
            }

            foreach ($candidateResult['hits'] as $rank => $hit) {
                $documentKey = 'id:' . $hit['document_id'];
                $documents[$documentKey] ??= [
                    'document_id' => $hit['document_id'],
                    'baseline_rank' => null,
                    'candidate_rank' => null,
                ];
                $documents[$documentKey]['candidate_rank'] = $rank + 1;
            }

            uasort(
                $documents,
                static fn (array $left, array $right): int =>
                    [min($left['baseline_rank'] ?? 999, $left['candidate_rank'] ?? 999)]
                    <=> [min($right['baseline_rank'] ?? 999, $right['candidate_rank'] ?? 999)]
            );

            foreach ($documents as $ranks) {
                $documentId = $ranks['document_id'];
                $allDocumentIds[] = $documentId;
                $queue[] = [
                    'query_hash' => $entry->getQueryHash(),
                    'query_text' => $entry->getQueryText(),
                    'document_id' => $documentId,
                    'name' => '',
                    'sku' => '',
                    'baseline_rank' => $ranks['baseline_rank'],
                    'candidate_rank' => $ranks['candidate_rank'],
                ];
            }
        }

        if ($queue === []) {
            throw new UnexpectedValueException('Baseline and candidate returned no products to rate');
        }

        $productContext = $this->productContextProvider->get(
            $baseline->getPhysicalIndex(),
            $allDocumentIds
        );

        foreach ($queue as &$item) {
            $context = $productContext[$item['document_id']] ?? ['name' => '', 'sku' => ''];
            $item['name'] = $context['name'];
            $item['sku'] = $context['sku'];
        }
        unset($item);

        return $queue;
    }

    private function assertCompatibleInputs(
        PersistedBaselineConfiguration $baseline,
        PersistedCandidateConfiguration $candidate,
        ApprovedQuerySnapshot $snapshot
    ): void {
        if (
            $baseline->getStoreId() !== $snapshot->getStoreId()
            || $candidate->getStoreId() !== $baseline->getStoreId()
            || $candidate->getParentBaselineUuid() !== $baseline->getConfigurationUuid()
            || $candidate->getIndexEvidenceUuid() !== $baseline->getIndexEvidenceUuid()
            || $candidate->getPhysicalIndex() !== $baseline->getPhysicalIndex()
        ) {
            throw new InvalidArgumentException('Rating queue inputs do not share one frozen store and index identity');
        }
    }
}
