<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Api;

use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\IndexEvidence;

interface IndexEvidenceCaptureInterface
{
    /**
     * Capture a content identity for one alias that resolves to one physical index.
     */
    public function capture(string $targetAlias): IndexEvidence;
}
