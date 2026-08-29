<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Configuration;

use UnexpectedValueException;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\ConfiguredOpenSearchClientProvider;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\IndexEvidence;

class MappedFieldCapabilityProvider
{
    public function __construct(
        private readonly ConfiguredOpenSearchClientProvider $clientProvider,
        private readonly MappedFieldCapabilityRegistry $registry,
        private readonly SearchableAttributeProvider $searchableAttributeProvider
    ) {
    }

    /**
     * @return array<string, array{searchable: bool, sensitive: bool, dynamic: bool, type: string}>
     */
    public function getForCapture(BaselineTemplate $template, IndexEvidence $indexEvidence): array
    {
        $physicalIndex = $indexEvidence->getPhysicalIndex();
        $response = $this->clientProvider->get()->indices()->getMapping(['index' => $physicalIndex]);
        $mapping = $response[$physicalIndex]['mappings'] ?? null;

        if (!is_array($mapping)) {
            throw new UnexpectedValueException('Target physical index returned no usable mapping');
        }

        return $this->registry->build(
            $template,
            $mapping,
            $this->searchableAttributeProvider->getAttributeCodes()
        );
    }
}
