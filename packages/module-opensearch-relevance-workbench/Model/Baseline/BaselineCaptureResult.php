<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Baseline;

class BaselineCaptureResult
{
    /**
     * @param list<array{query_text_hash: string, mapped_request_hash: string}> $validationEvidence
     */
    public function __construct(
        private readonly \MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate $template,
        private readonly array $validationEvidence
    ) {
    }

    public function getTemplate(): BaselineTemplate
    {
        return $this->template;
    }

    /**
     * @return list<array{query_text_hash: string, mapped_request_hash: string}>
     */
    public function getValidationEvidence(): array
    {
        return $this->validationEvidence;
    }
}
