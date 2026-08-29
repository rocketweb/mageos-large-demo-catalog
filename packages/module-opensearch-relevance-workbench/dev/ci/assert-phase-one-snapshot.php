<?php

declare(strict_types=1);

use Magento\Framework\App\Bootstrap;
use Magento\Framework\App\ResourceConnection;
use Magento\Framework\App\State;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPreviewService;

if ($argc !== 2) {
    fwrite(STDERR, "Usage: php assert-phase-one-snapshot.php /path/to/mageos\n");
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
$searchQueryTable = $resourceConnection->getTableName('search_query');
$fixtureRows = [
    [
        'query_text' => 'winter boots',
        'num_results' => 4,
        'popularity' => 20,
        'redirect' => null,
        'store_id' => 1,
        'display_in_terms' => 1,
        'is_active' => 1,
        'is_processed' => 1,
        'updated_at' => '2026-08-26 12:00:00',
    ],
    [
        'query_text' => 'private@example.com',
        'num_results' => 2,
        'popularity' => 15,
        'redirect' => null,
        'store_id' => 1,
        'display_in_terms' => 1,
        'is_active' => 1,
        'is_processed' => 1,
        'updated_at' => '2026-08-26 12:01:00',
    ],
];

foreach ($fixtureRows as $fixtureRow) {
    $connection->insertOnDuplicate($searchQueryTable, $fixtureRow, array_keys($fixtureRow));
}

$parameters = [
    'store_id' => 1,
    'source_window_start' => '2026-08-26T00:00:00+00:00',
    'source_window_end' => '2026-08-26T23:59:59+00:00',
    'minimum_popularity' => 1,
    'positive_result_limit' => 10,
    'zero_result_limit' => 10,
    'total_limit' => 20,
    'include_redirects' => '0',
];
/** @var SnapshotPreviewService $previewService */
$previewService = $objectManager->get(SnapshotPreviewService::class);
$preview = $previewService->create($parameters);

if ($preview->getSourceCount() !== 2 || $preview->getSelectedCount() !== 1) {
    throw new RuntimeException('Unexpected source or selected snapshot counts.');
}

if ($preview->getExcludedCounts() !== ['EMAIL_ADDRESS' => 1]) {
    throw new RuntimeException('Privacy exclusion evidence did not match the fixture.');
}

$approved = $preview->approve(
    $preview->getSnapshotHash(),
    1,
    '2026-08-26T15:00:00+00:00'
);
/** @var QuerySnapshotRepository $repository */
$repository = $objectManager->get(QuerySnapshotRepository::class);
$snapshotUuid = $repository->saveApproved(
    $preview,
    $approved,
    'phase-one-fixture-correlation'
);
$idempotentUuid = $repository->saveApproved(
    $preview,
    $approved,
    'phase-one-fixture-correlation-repeat'
);

if ($snapshotUuid !== $idempotentUuid) {
    throw new RuntimeException('Identical snapshot approval did not resolve to the same local UUID.');
}

$snapshotTable = $resourceConnection->getTableName('osrw_query_snapshot');
$entryTable = $resourceConnection->getTableName('osrw_query_snapshot_entry');
$auditTable = $resourceConnection->getTableName('osrw_audit_event');
$snapshotCount = (int)$connection->fetchOne(
    $connection->select()->from($snapshotTable, ['count' => 'COUNT(*)'])
);
$entryCount = (int)$connection->fetchOne(
    $connection->select()->from($entryTable, ['count' => 'COUNT(*)'])
);
$auditCount = (int)$connection->fetchOne(
    $connection->select()->from($auditTable, ['count' => 'COUNT(*)'])
);
$privateEntryCount = (int)$connection->fetchOne(
    $connection->select()
        ->from($entryTable, ['count' => 'COUNT(*)'])
        ->where('query_text = ?', 'private@example.com')
);

if ($snapshotCount !== 1 || $entryCount !== 1 || $auditCount !== 1 || $privateEntryCount !== 0) {
    throw new RuntimeException('Persisted snapshot, entry, audit, or privacy counts did not match.');
}

fwrite(
    STDOUT,
    json_encode(
        [
            'phase_one_snapshot' => 'PASS',
            'snapshot_uuid' => $snapshotUuid,
            'snapshot_sha256' => $preview->getSnapshotHash(),
            'source_count' => $preview->getSourceCount(),
            'selected_count' => $preview->getSelectedCount(),
            'excluded_counts' => $preview->getExcludedCounts(),
            'idempotent_save' => true,
            'private_term_persisted_in_osrw' => false,
            'audit_event_count' => $auditCount,
        ],
        JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES
    ) . "\n"
);
