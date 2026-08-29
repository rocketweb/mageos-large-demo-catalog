<?php

declare(strict_types=1);

use Magento\Framework\App\Bootstrap;
use Magento\Framework\App\ResourceConnection;
use Magento\Framework\App\State;
use Magento\Store\Model\StoreManagerInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Activation\LiveActivationService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Activation\LiveQueryApplier;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\LiveActivationRepository;

if ($argc !== 2) {
    fwrite(STDERR, "Usage: php assert-live-activation.php /path/to/mageos\n");
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
    $objectManager->get(State::class)->setAreaCode('frontend');
} catch (\Magento\Framework\Exception\LocalizedException) {
}

/** @var StoreManagerInterface $storeManager */
$storeManager = $objectManager->get(StoreManagerInterface::class);
$storeManager->setCurrentStore(1);
/** @var ExperimentRepository $experimentRepository */
$experimentRepository = $objectManager->get(ExperimentRepository::class);
$acceptedExperimentUuid = null;

foreach ($experimentRepository->listRecent(100) as $experiment) {
    if ((string)$experiment['state'] === 'ACCEPTED' && (string)$experiment['eligibility'] === 'WINNER') {
        $acceptedExperimentUuid = (string)$experiment['experiment_uuid'];
        break;
    }
}

if ($acceptedExperimentUuid === null) {
    throw new RuntimeException('Activation fixture requires an accepted winning experiment.');
}

/** @var LiveActivationService $activationService */
$activationService = $objectManager->get(LiveActivationService::class);
$activationUuid = $activationService->activate(
    $acceptedExperimentUuid,
    1,
    '2026-08-28T18:00:00+00:00',
    'installed-live-activation'
);
/** @var LiveActivationRepository $activationRepository */
$activationRepository = $objectManager->get(LiveActivationRepository::class);
$active = $activationRepository->getCurrent(1);

if (
    $active === null
    || $active->getActivationUuid() !== $activationUuid
    || ($active->getTransformation()['type'] ?? null) !== 'FIELD_BOOST'
    || ($active->getTransformation()['boosts']['description'] ?? null) !== 20.0
) {
    throw new RuntimeException('Accepted candidate did not become the exact current live state.');
}

$duplicateRejected = false;

try {
    $activationService->activate(
        $acceptedExperimentUuid,
        1,
        '2026-08-28T18:00:30+00:00',
        'installed-duplicate-activation'
    );
} catch (UnexpectedValueException $exception) {
    $duplicateRejected = $exception->getMessage() === 'The exact candidate is already active for this store';
}

if (!$duplicateRejected) {
    throw new RuntimeException('Reapplying the exact live candidate was not rejected.');
}

$stockQuery = [
    'index' => 'magento2_product_1',
    'body' => [
        'query' => [
            'bool' => [
                'should' => [
                    ['multi_match' => ['query' => 'coat', 'fields' => ['name^3', 'description^1']]],
                    ['match' => ['description' => ['query' => 'coat', 'boost' => 1.0]]],
                ],
            ],
        ],
    ],
];
/** @var LiveQueryApplier $activeApplier */
$activeApplier = $objectManager->create(LiveQueryApplier::class);
$liveQuery = $activeApplier->apply($stockQuery);

if (
    $liveQuery['body']['query']['bool']['should'][0]['multi_match']['fields'] !== ['name^3', 'description^20']
    || $liveQuery['body']['query']['bool']['should'][1]['match']['description']['boost'] !== 20.0
) {
    throw new RuntimeException('Installed live query applier did not apply the accepted field boost.');
}

$rollbackUuid = $activationRepository->rollback(
    1,
    1,
    '2026-08-28T18:01:00+00:00',
    'installed-live-rollback'
);
$rolledBack = $activationRepository->getCurrent(1);

if (
    $rolledBack === null
    || $rolledBack->getActivationUuid() !== $rollbackUuid
    || $rolledBack->getAction() !== 'ROLLBACK'
    || $rolledBack->getTransformation() !== ['type' => 'STOCK']
) {
    throw new RuntimeException('Rollback did not restore the stock live state.');
}

/** @var LiveQueryApplier $rolledBackApplier */
$rolledBackApplier = $objectManager->create(LiveQueryApplier::class);

if ($rolledBackApplier->apply($stockQuery) !== $stockQuery) {
    throw new RuntimeException('Rolled-back storefront query did not return to the exact stock request.');
}

/** @var ResourceConnection $resourceConnection */
$resourceConnection = $objectManager->get(ResourceConnection::class);
$connection = $resourceConnection->getConnection();
$activationCount = (int)$connection->fetchOne(
    $connection->select()->from($resourceConnection->getTableName('osrw_live_activation'), ['COUNT(*)'])
);
$activationAuditCount = (int)$connection->fetchOne(
    $connection->select()
        ->from($resourceConnection->getTableName('osrw_audit_event'), ['COUNT(*)'])
        ->where('target_type = ?', 'LIVE_CONFIGURATION')
);

if ($activationCount !== 2 || $activationAuditCount !== 2) {
    throw new RuntimeException('Activation and rollback did not create exactly two append-only audit records.');
}

fwrite(
    STDOUT,
    json_encode(
        [
            'live_activation' => 'PASS',
            'source_experiment_uuid' => $acceptedExperimentUuid,
            'activation_uuid' => $activationUuid,
            'rollback_uuid' => $rollbackUuid,
            'active_boost' => 20.0,
            'duplicate_activation' => 'REJECTED',
            'restored_state' => 'STOCK',
            'activation_event_count' => $activationCount,
            'activation_audit_count' => $activationAuditCount,
            'graphql_scope' => 'UNCHANGED_BY_PLUGIN_CONTRACT',
        ],
        JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES
    ) . PHP_EOL
);
