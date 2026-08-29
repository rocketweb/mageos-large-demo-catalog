<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Baseline;

use InvalidArgumentException;
use Magento\CatalogSearch\Model\ResourceModel\Fulltext\Collection;
use Magento\Store\Model\App\Emulation;
use MageOS\OpenSearchRelevanceWorkbench\Api\IndexEvidenceCaptureInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\MappedFieldCapabilityProvider;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\UuidGenerator;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\ApprovedQuerySnapshot;
use UnexpectedValueException;

class StockBaselineCaptureService
{
    public function __construct(
        private readonly BaselineCaptureHarness $captureHarness,
        private readonly SearchCollectionFactory $collectionFactory,
        private readonly Emulation $appEmulation,
        private readonly IndexEvidenceCaptureInterface $indexEvidenceCapture,
        private readonly MappedFieldCapabilityProvider $fieldCapabilityProvider,
        private readonly CanonicalJson $canonicalJson,
        private readonly UuidGenerator $uuidGenerator
    ) {
    }

    public function capture(ApprovedQuerySnapshot $snapshot): StockBaselineCapture
    {
        $validationQueries = array_map(
            static fn ($entry): string => $entry->getQueryText(),
            array_slice($snapshot->getEntries(), 0, 5)
        );

        if (count($validationQueries) < 5) {
            throw new InvalidArgumentException('Baseline capture requires at least five approved snapshot queries');
        }

        $firstSentinel = 'osrw-' . $this->uuidGenerator->generate();
        $secondSentinel = 'osrw-' . $this->uuidGenerator->generate();
        $this->appEmulation->startEnvironmentEmulation($snapshot->getStoreId(), 'frontend', true);

        try {
            $captureResult = $this->captureHarness->capture(
                function (string $queryText): void {
                    $collection = $this->collectionFactory->create([
                        'searchRequestName' => 'quick_search_container',
                    ]);
                    $collection->addSearchFilter($queryText);
                    $collection->setPageSize(12);
                    $collection->setCurPage(1);
                    $collection->getSize();
                },
                $firstSentinel,
                $secondSentinel,
                $validationQueries
            );
        } finally {
            $this->appEmulation->stopEnvironmentEmulation();
        }

        $template = $captureResult->getTemplate();
        $templateArray = $template->getTemplate();
        $targetIndex = $templateArray['index'] ?? null;
        $body = $templateArray['body'] ?? null;

        if (!is_string($targetIndex) || $targetIndex === '' || !is_array($body)) {
            throw new UnexpectedValueException('Captured stock request has no bounded index and body');
        }

        $indexEvidence = $this->indexEvidenceCapture->capture($targetIndex);
        $fieldCapabilities = $this->fieldCapabilityProvider->getForCapture($template, $indexEvidence);
        $remoteConfiguration = [
            'index' => $indexEvidence->getPhysicalIndex(),
            'query' => $this->canonicalJson->encode($body),
            'searchPipeline' => '',
        ];
        $configurationHash = $this->canonicalJson->hash([
            'kind' => 'BASELINE',
            'captured_template_sha256' => $template->getTemplateHash(),
            'index_evidence_sha256' => $indexEvidence->getEvidenceHash(),
            'remote_configuration' => $remoteConfiguration,
            'field_capabilities' => $fieldCapabilities,
            'validation_evidence' => $captureResult->getValidationEvidence(),
        ]);

        return new StockBaselineCapture(
            $captureResult,
            $indexEvidence,
            $fieldCapabilities,
            $remoteConfiguration,
            $configurationHash
        );
    }
}
