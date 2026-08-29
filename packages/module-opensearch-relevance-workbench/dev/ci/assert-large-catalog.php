<?php

declare(strict_types=1);

use Magento\Catalog\Model\ResourceModel\Product\CollectionFactory as ProductCollectionFactory;
use Magento\CatalogSearch\Model\Indexer\Fulltext;
use Magento\Elasticsearch\SearchAdapter\SearchIndexNameResolver;
use Magento\Framework\App\Bootstrap;
use Magento\Framework\App\ResourceConnection;
use Magento\Framework\App\State;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\StockBaselineCaptureService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\CandidateValidationService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\HumanRatingQueueService;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\ConfiguredOpenSearchClientProvider;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\CandidateConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPreviewService;

const MINIMUM_CATALOG_PRODUCTS = 800;
const MINIMUM_INDEXED_DOCUMENTS = 800;
const SEEDED_QUERY_COUNT = 100;

if ($argc !== 2) {
    fwrite(STDERR, "Usage: php assert-large-catalog.php /path/to/mageos\n");
    exit(2);
}

$fixtureRoot = rtrim((string)$argv[1], DIRECTORY_SEPARATOR);

if (!is_file($fixtureRoot . '/app/bootstrap.php')) {
    fwrite(STDERR, "Mage-OS bootstrap not found: {$fixtureRoot}\n");
    exit(2);
}

require $fixtureRoot . '/app/bootstrap.php';

$bootstrap = Bootstrap::create(BP, $_SERVER);
$objectManager = $bootstrap->getObjectManager();

try {
    $objectManager->get(State::class)->setAreaCode('adminhtml');
} catch (\Magento\Framework\Exception\LocalizedException) {
}

/** @var ResourceConnection $resourceConnection */
$resourceConnection = $objectManager->get(ResourceConnection::class);
$connection = $resourceConnection->getConnection();
$catalogProductCount = (int)$connection->fetchOne(
    $connection->select()->from(
        $resourceConnection->getTableName('catalog_product_entity'),
        ['count' => 'COUNT(*)']
    )
);

if ($catalogProductCount < MINIMUM_CATALOG_PRODUCTS) {
    throw new RuntimeException(sprintf(
        'Large catalog fixture created %d products; expected at least %d.',
        $catalogProductCount,
        MINIMUM_CATALOG_PRODUCTS
    ));
}

/** @var ConfiguredOpenSearchClientProvider $clientProvider */
$clientProvider = $objectManager->get(ConfiguredOpenSearchClientProvider::class);
$openSearchClient = $clientProvider->get();
/** @var SearchIndexNameResolver $indexNameResolver */
$indexNameResolver = $objectManager->get(SearchIndexNameResolver::class);
$targetAlias = $indexNameResolver->getIndexName(1, Fulltext::INDEXER_ID);
$aliasResponse = $openSearchClient->indices()->getAlias(['name' => $targetAlias]);
$physicalIndices = array_keys($aliasResponse);

if (count($physicalIndices) !== 1) {
    throw new RuntimeException('Large catalog alias did not resolve to exactly one physical index.');
}

$physicalIndex = $physicalIndices[0];
$countResponse = $openSearchClient->count(['index' => $physicalIndex]);
$indexedDocumentCount = (int)($countResponse['count'] ?? 0);

if ($indexedDocumentCount < MINIMUM_INDEXED_DOCUMENTS) {
    throw new RuntimeException(sprintf(
        'Large catalog index contains %d documents; expected at least %d.',
        $indexedDocumentCount,
        MINIMUM_INDEXED_DOCUMENTS
    ));
}

/** @var ProductCollectionFactory $productCollectionFactory */
$productCollectionFactory = $objectManager->get(ProductCollectionFactory::class);
$productCollection = $productCollectionFactory->create();
$productCollection->setStoreId(1);
$productCollection->addAttributeToSelect(['name', 'sku']);
$productCollection->addAttributeToFilter('status', 1);
$productCollection->addAttributeToFilter('visibility', ['in' => [2, 3, 4]]);
$productCollection->setOrder('entity_id', 'ASC');
$productCollection->setPageSize(SEEDED_QUERY_COUNT);

$searchQueries = [];

foreach ($productCollection as $product) {
    $sku = trim((string)$product->getSku());

    if ($sku === '') {
        continue;
    }

    $searchQueries[$sku] = $sku;

    if (count($searchQueries) === SEEDED_QUERY_COUNT) {
        break;
    }
}

$searchQueries = array_values($searchQueries);

if (count($searchQueries) !== SEEDED_QUERY_COUNT) {
    throw new RuntimeException(sprintf(
        'Large catalog exposed %d distinct searchable SKUs; expected %d.',
        count($searchQueries),
        SEEDED_QUERY_COUNT
    ));
}

$searchQueryTable = $resourceConnection->getTableName('search_query');

foreach ($searchQueries as $ordinal => $queryText) {
    $fixtureRow = [
        'query_text' => $queryText,
        'num_results' => 1,
        'popularity' => SEEDED_QUERY_COUNT - $ordinal,
        'redirect' => null,
        'store_id' => 1,
        'display_in_terms' => 1,
        'is_active' => 1,
        'is_processed' => 1,
        'updated_at' => sprintf('2026-08-27 10:%02d:%02d', intdiv($ordinal, 60), $ordinal % 60),
    ];
    $connection->insertOnDuplicate($searchQueryTable, $fixtureRow, array_keys($fixtureRow));
}

$parameters = [
    'store_id' => 1,
    'source_window_start' => '2026-08-27T10:00:00+00:00',
    'source_window_end' => '2026-08-27T10:59:59+00:00',
    'minimum_popularity' => 1,
    'positive_result_limit' => SEEDED_QUERY_COUNT,
    'zero_result_limit' => 1,
    'total_limit' => SEEDED_QUERY_COUNT,
    'include_redirects' => '0',
];
/** @var SnapshotPreviewService $previewService */
$previewService = $objectManager->get(SnapshotPreviewService::class);
$preview = $previewService->create($parameters);

if (
    $preview->getSourceCount() !== SEEDED_QUERY_COUNT
    || $preview->getSelectedCount() !== SEEDED_QUERY_COUNT
    || $preview->getExcludedCounts() !== []
) {
    throw new RuntimeException('Large catalog query snapshot did not preserve all seeded product queries.');
}

$approved = $preview->approve(
    $preview->getSnapshotHash(),
    1,
    '2026-08-27T11:00:00+00:00'
);
/** @var QuerySnapshotRepository $snapshotRepository */
$snapshotRepository = $objectManager->get(QuerySnapshotRepository::class);
$snapshotUuid = $snapshotRepository->saveApproved(
    $preview,
    $approved,
    'large-catalog-snapshot'
);
$snapshot = $snapshotRepository->getApproved($snapshotUuid);

/** @var StockBaselineCaptureService $captureService */
$captureService = $objectManager->get(StockBaselineCaptureService::class);
$capture = $captureService->capture($snapshot);

if (count($capture->getCaptureResult()->getValidationEvidence()) !== 5) {
    throw new RuntimeException('Large catalog baseline did not pass five-query validation.');
}

/** @var BaselineConfigurationRepository $baselineRepository */
$baselineRepository = $objectManager->get(BaselineConfigurationRepository::class);
$baselineUuid = $baselineRepository->save(
    $capture,
    1,
    1,
    '2026-08-27T11:01:00+00:00',
    'large-catalog-baseline'
);
$baseline = $baselineRepository->get($baselineUuid);

/** @var CandidateValidationService $candidateValidationService */
$candidateValidationService = $objectManager->get(CandidateValidationService::class);
$validatedCandidate = $candidateValidationService->build(
    $baseline,
    $snapshot,
    ['name' => 2.0]
);

if (count($validatedCandidate->getValidationEvidence()) !== 5) {
    throw new RuntimeException('Large catalog candidate did not pass five-query validation.');
}

/** @var CandidateConfigurationRepository $candidateRepository */
$candidateRepository = $objectManager->get(CandidateConfigurationRepository::class);
$candidateUuid = $candidateRepository->save(
    $validatedCandidate,
    1,
    '2026-08-27T11:02:00+00:00',
    'large-catalog-candidate'
);
$candidate = $candidateRepository->get($candidateUuid);

/** @var HumanRatingQueueService $ratingQueueService */
$ratingQueueService = $objectManager->get(HumanRatingQueueService::class);
$ratingQueue = $ratingQueueService->build($baseline, $candidate, $snapshot);

if ($ratingQueue === []) {
    throw new RuntimeException('Large catalog did not produce any product pairs for human rating.');
}

fwrite(
    STDOUT,
    json_encode(
        [
            'large_catalog' => 'PASS',
            'profile' => 'small-catalog-only',
            'database_product_count' => $catalogProductCount,
            'indexed_document_count' => $indexedDocumentCount,
            'target_alias' => $targetAlias,
            'physical_index' => $physicalIndex,
            'seeded_query_count' => count($searchQueries),
            'snapshot_selected_count' => $preview->getSelectedCount(),
            'baseline_validation_sample_count' => count(
                $capture->getCaptureResult()->getValidationEvidence()
            ),
            'candidate_validation_sample_count' => count(
                $validatedCandidate->getValidationEvidence()
            ),
            'rating_queue_pair_count' => count($ratingQueue),
            'live_search_mutation' => false,
        ],
        JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES
    ) . "\n"
);
