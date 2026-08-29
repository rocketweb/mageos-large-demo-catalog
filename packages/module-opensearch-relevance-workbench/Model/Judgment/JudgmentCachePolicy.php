<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Judgment;

class JudgmentCachePolicy
{
    public function decide(
        JudgmentCacheIdentity $current,
        ?JudgmentCacheIdentity $previousAccepted
    ): JudgmentCacheDecision {
        if ($previousAccepted === null) {
            return new JudgmentCacheDecision(true, ['NO_ACCEPTED_PRIOR_RUN']);
        }

        $reasonCodes = [];

        foreach ($this->protectedComponents($current) as $name => $value) {
            if ($value !== $this->protectedComponents($previousAccepted)[$name]) {
                $reasonCodes[] = $name . '_CHANGED';
            }
        }

        return new JudgmentCacheDecision($reasonCodes !== [], $reasonCodes);
    }

    /**
     * @return array<string, string|list<string>>
     */
    private function protectedComponents(JudgmentCacheIdentity $identity): array
    {
        return [
            'MODEL' => $identity->getModelId(),
            'PROMPT' => $identity->getPromptHash(),
            'RATING_TYPE' => $identity->getRatingType(),
            'CONTEXT_FIELDS' => $identity->getContextFields(),
            'CONTEXT_VALUES' => $identity->getContextValuesHash(),
            'QUERY_SNAPSHOT' => $identity->getQuerySnapshotHash(),
            'SEARCH_CONFIGURATION' => $identity->getSearchConfigurationHash(),
            'INDEX_EVIDENCE' => $identity->getIndexEvidenceHash(),
        ];
    }
}
