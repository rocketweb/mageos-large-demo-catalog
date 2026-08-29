<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Configuration;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\ApprovedQuerySnapshot;

class CandidateValidationService
{
    public function __construct(
        private readonly FieldBoostCompiler $compiler,
        private readonly BoundedTemplateSearch $boundedSearch
    ) {
    }

    /**
     * @param array<string, float> $boosts
     */
    public function build(
        PersistedBaselineConfiguration $baseline,
        ApprovedQuerySnapshot $snapshot,
        array $boosts
    ): ValidatedCandidateConfiguration {
        if ($baseline->getStoreId() !== $snapshot->getStoreId()) {
            throw new InvalidArgumentException('Candidate baseline and validation snapshot must use the same store');
        }

        $validationEntries = array_slice($snapshot->getEntries(), 0, 5);

        if (count($validationEntries) < 5) {
            throw new InvalidArgumentException('Candidate validation requires at least five approved queries');
        }

        $candidate = $this->compiler->compile(
            $baseline->getTemplate(),
            $baseline->getFieldCapabilities(),
            $boosts,
            $baseline->getConfigurationHash()
        );
        $candidateTemplate = new BaselineTemplate(
            $candidate->getTemplate(),
            $baseline->getTemplate()->getQueryTextPaths(),
            $candidate->getConfigurationHash()
        );
        $validationEvidence = [];

        foreach ($validationEntries as $entry) {
            $result = $this->boundedSearch->execute(
                $candidateTemplate,
                $entry->getQueryText(),
                $baseline->getPhysicalIndex(),
                20
            );

            $validationEvidence[] = [
                'query_text_hash' => $entry->getQueryHash(),
                'rendered_request_hash' => $result['request_hash'],
                'result_count' => $result['total'],
            ];
        }

        return new ValidatedCandidateConfiguration($candidate, $baseline, $validationEvidence);
    }
}
