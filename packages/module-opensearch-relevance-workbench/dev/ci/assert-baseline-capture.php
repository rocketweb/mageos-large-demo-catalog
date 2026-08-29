<?php

declare(strict_types=1);

use Composer\InstalledVersions;
use MageOS\OpenSearchRelevanceWorkbench\Api\SearchRelevanceClientInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineCaptureHarness;
use Magento\CatalogGraphQl\DataProvider\Product\SearchCriteriaBuilder as GraphQlSearchCriteriaBuilder;
use Magento\CatalogSearch\Model\ResourceModel\Fulltext\Collection as FulltextCollection;
use Magento\Framework\Api\Search\SearchInterface;
use Magento\Framework\App\Bootstrap;
use Magento\Framework\App\State;
use Magento\Framework\View\DesignInterface;
use Magento\Store\Model\StoreManagerInterface;

if ($argc < 2 || $argc > 3) {
    fwrite(STDERR, "Usage: php assert-baseline-capture.php /path/to/mageos [Vendor/theme]\n");
    exit(2);
}

$fixtureRoot = rtrim((string)$argv[1], DIRECTORY_SEPARATOR);
$expectedTheme = (string)($argv[2] ?? '');

if (!is_file($fixtureRoot . '/app/bootstrap.php')) {
    fwrite(STDERR, "Mage-OS bootstrap not found: {$fixtureRoot}\n");
    exit(2);
}

require $fixtureRoot . '/app/bootstrap.php';

$bootstrap = Bootstrap::create(BP, $_SERVER);
$objectManager = $bootstrap->getObjectManager();

try {
    $objectManager->get(State::class)->setAreaCode('frontend');
} catch (\Magento\Framework\Exception\LocalizedException) {
}

$objectManager->get(StoreManagerInterface::class)->setCurrentStore(1);
$design = $objectManager->get(DesignInterface::class);
$design->setDefaultDesignTheme();
$themePath = $design->getThemePath($design->getDesignTheme());

if ($expectedTheme !== '' && $themePath !== $expectedTheme) {
    throw new RuntimeException("Expected active theme {$expectedTheme}, got {$themePath}.");
}

$searchRelevanceStats = $objectManager->get(SearchRelevanceClientInterface::class)->stats();

if ($searchRelevanceStats === []) {
    throw new RuntimeException('The installed module returned an empty Search Relevance stats response.');
}

$validationQueries = ['boots', 'red dress', 'MUG-001', 'café table', 'winter coat'];
$firstSentinel = 'osrw-744466dd-a552-44ed-9263-3da65221c5a4';
$secondSentinel = 'osrw-96d12f79-9e90-4218-b633-f366033f247f';
/** @var BaselineCaptureHarness $captureHarness */
$captureHarness = $objectManager->get(BaselineCaptureHarness::class);

$storefront = $captureHarness->capture(
    static function (string $queryText) use ($objectManager): void {
        /** @var FulltextCollection $collection */
        $collection = $objectManager->create(
            FulltextCollection::class,
            ['searchRequestName' => 'quick_search_container']
        );
        $collection->addSearchFilter($queryText);
        $collection->setPageSize(12);
        $collection->setCurPage(1);
        $collection->getSize();
    },
    $firstSentinel,
    $secondSentinel,
    $validationQueries
);

$graphQl = $captureHarness->capture(
    static function (string $queryText) use ($objectManager): void {
        /** @var GraphQlSearchCriteriaBuilder $criteriaBuilder */
        $criteriaBuilder = $objectManager->create(GraphQlSearchCriteriaBuilder::class);
        $criteria = $criteriaBuilder->build(
            [
                'search' => $queryText,
                'pageSize' => 12,
                'currentPage' => 1,
            ],
            false
        );
        $objectManager->get(SearchInterface::class)->search($criteria);
    },
    $firstSentinel,
    $secondSentinel,
    $validationQueries
);

$storefrontTemplate = $storefront->getTemplate();
$graphQlTemplate = $graphQl->getTemplate();
$evidence = [
    'mageos_version' => '3.4.0',
    'opensearch_php_version' => InstalledVersions::getPrettyVersion('opensearch-project/opensearch-php'),
    'php_version' => PHP_VERSION,
    'search_relevance_transport' => 'PASS',
    'theme' => $themePath,
    'hyva_version' => InstalledVersions::isInstalled('hyva-themes/magento2-default-theme')
        ? InstalledVersions::getPrettyVersion('hyva-themes/magento2-default-theme')
        : null,
    'store_id' => 1,
    'validation_sample_count' => count($validationQueries),
    'storefront' => [
        'request_name' => 'quick_search_container',
        'template_digest' => $storefrontTemplate->getTemplateHash(),
        'query_text_paths' => $storefrontTemplate->getQueryTextPaths(),
        'validation' => $storefront->getValidationEvidence(),
    ],
    'graphql' => [
        'request_name' => 'graphql_product_search',
        'template_digest' => $graphQlTemplate->getTemplateHash(),
        'query_text_paths' => $graphQlTemplate->getQueryTextPaths(),
        'validation' => $graphQl->getValidationEvidence(),
    ],
    'surface_contract' => $storefrontTemplate->getTemplateHash() === $graphQlTemplate->getTemplateHash()
        ? 'SHARED'
        : 'DISTINCT',
];

fwrite(
    STDOUT,
    json_encode($evidence, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES) . "\n"
);
