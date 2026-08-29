<?php

declare(strict_types=1);

use Magento\Framework\App\Bootstrap;
use Magento\Framework\App\ResourceConnection;
use Magento\Framework\App\State;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\ExperimentEvidenceService;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\ConfiguredOpenSearchClientProvider;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ProposalRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\SnapshotScheduleRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Proposal\ProposalCreationService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Schedule\ScheduledDraftPreparer;
use MageOS\OpenSearchRelevanceWorkbench\Model\Schedule\SnapshotSchedulePolicyFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\OwnedResourceCleanupPreviewService;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPreviewService;

if ($argc !== 2) {
    fwrite(STDERR, "Usage: php assert-phase-three.php /path/to/mageos\n");
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
/** @var ExperimentRepository $experimentRepository */
$experimentRepository = $objectManager->get(ExperimentRepository::class);
$experimentUuid = null;

foreach ($experimentRepository->listRecent() as $row) {
    if (($row['state'] ?? null) === 'ACCEPTED') {
        $experimentUuid = (string)$row['experiment_uuid'];
        break;
    }
}

if ($experimentUuid === null) {
    throw new RuntimeException('Phase 3 fixture requires the accepted Phase 1 experiment.');
}

/** @var ExperimentEvidenceService $evidenceService */
$evidenceService = $objectManager->get(ExperimentEvidenceService::class);
$freshEvidence = $evidenceService->build($experimentUuid);

if (
    ($freshEvidence['index_state'] ?? null) !== 'FRESH'
    || ($freshEvidence['product_context_state'] ?? null) !== 'AVAILABLE'
    || !is_array($freshEvidence['queries'] ?? null)
    || $freshEvidence['queries'] === []
) {
    throw new RuntimeException('Phase 3 did not reconstruct fresh before-and-after product evidence.');
}

$removedDocumentId = null;

foreach ($freshEvidence['queries'] as $query) {
    foreach (is_array($query['products'] ?? null) ? $query['products'] : [] as $product) {
        if (($product['available'] ?? false) === true && is_string($product['document_id'] ?? null)) {
            $removedDocumentId = $product['document_id'];
            break 2;
        }
    }
}

if ($removedDocumentId === null) {
    throw new RuntimeException('Phase 3 evidence did not include a product identity for stale-context testing.');
}

$experiment = $experimentRepository->getCompleted($experimentUuid);
$baselineUuid = $experiment->getInputIdentities()['baseline_configuration_uuid'] ?? null;

if (!is_string($baselineUuid) || $baselineUuid === '') {
    throw new RuntimeException('Accepted experiment did not preserve its baseline identity.');
}

/** @var BaselineConfigurationRepository $baselineRepository */
$baselineRepository = $objectManager->get(BaselineConfigurationRepository::class);
$baseline = $baselineRepository->get($baselineUuid);
/** @var ConfiguredOpenSearchClientProvider $clientProvider */
$clientProvider = $objectManager->get(ConfiguredOpenSearchClientProvider::class);
$openSearchClient = $clientProvider->get();
$openSearchClient->delete([
    'index' => $baseline->getPhysicalIndex(),
    'id' => $removedDocumentId,
]);
$openSearchClient->indices()->refresh(['index' => $baseline->getPhysicalIndex()]);
$staleEvidence = $evidenceService->build($experimentUuid);
$unavailableDocumentFound = false;

foreach ($staleEvidence['queries'] as $query) {
    foreach (is_array($query['products'] ?? null) ? $query['products'] : [] as $product) {
        if (
            ($product['document_id'] ?? null) === $removedDocumentId
            && ($product['available'] ?? true) === false
            && ($product['name'] ?? null) === 'Product unavailable'
        ) {
            $unavailableDocumentFound = true;
            break 2;
        }
    }
}

if (
    ($staleEvidence['index_state'] ?? null) !== 'STALE'
    || ($staleEvidence['product_context_state'] ?? null) !== 'PARTIAL'
    || !$unavailableDocumentFound
) {
    throw new RuntimeException('Stale evidence did not preserve deleted products as unavailable context.');
}

/** @var ProposalCreationService $proposalCreationService */
$proposalCreationService = $objectManager->get(ProposalCreationService::class);
$staleProposalBlocked = false;

try {
    $proposalCreationService->create(
        $experimentUuid,
        1,
        '2026-08-27T00:00:00+00:00',
        'phase-three-stale-proposal'
    );
} catch (RuntimeException $exception) {
    $staleProposalBlocked = str_contains($exception->getMessage(), 'index evidence is stale');
}

if (!$staleProposalBlocked) {
    throw new RuntimeException('Existing proposal export bypassed stale index evidence.');
}

/** @var OwnedResourceCleanupPreviewService $cleanupPreviewService */
$cleanupPreviewService = $objectManager->get(OwnedResourceCleanupPreviewService::class);
$cleanupPreview = $cleanupPreviewService->preview();

if (count($cleanupPreview) !== 7) {
    throw new RuntimeException('Phase 3 cleanup preview did not enumerate all seven bound resources.');
}

foreach ($cleanupPreview as $resource) {
    if ($resource['eligible'] !== true || $resource['reason_codes'] !== []) {
        throw new RuntimeException('An exact bound resource failed the cleanup preview identity gate.');
    }
}

/** @var SnapshotPreviewService $metadataPreviewService */
$metadataPreviewService = $objectManager->get(SnapshotPreviewService::class);
$metadataQueryHash = hash('sha256', 'boots');
$metadataPreview = $metadataPreviewService->create([
    'store_id' => 1,
    'source_window_start' => '2026-08-26T00:00:00+00:00',
    'source_window_end' => '2026-08-26T23:59:59+00:00',
    'minimum_popularity' => 1,
    'positive_result_limit' => 20,
    'zero_result_limit' => 10,
    'total_limit' => 30,
    'include_redirects' => '0',
    'metadata' => [
        $metadataQueryHash => ['category_id' => '42', 'brand_value' => 'Northwind'],
    ],
]);
$metadataApproved = $metadataPreview->approve(
    $metadataPreview->getSnapshotHash(),
    1,
    '2026-08-27T00:01:00+00:00'
);
/** @var QuerySnapshotRepository $snapshotRepository */
$snapshotRepository = $objectManager->get(QuerySnapshotRepository::class);
$metadataSnapshotUuid = $snapshotRepository->saveApproved(
    $metadataPreview,
    $metadataApproved,
    'phase-three-curated-metadata'
);
$persistedMetadataSnapshot = $snapshotRepository->getApproved($metadataSnapshotUuid);
$metadataRemoteEntry = null;
$persistedMetadataFields = null;

foreach ($persistedMetadataSnapshot->getRemoteQuerySetEntries() as $entry) {
    if (($entry['queryText'] ?? null) === 'boots') {
        $metadataRemoteEntry = $entry;
        break;
    }
}

foreach ($persistedMetadataSnapshot->getEntries() as $entry) {
    if ($entry->getQueryText() === 'boots') {
        $persistedMetadataFields = $entry->getCustomFields();
        break;
    }
}

if (
    !is_array($metadataRemoteEntry)
    || ($metadataRemoteEntry['customFields'] ?? null) !== [
        'brand_value' => 'Northwind',
        'category_id' => '42',
    ]
    || $persistedMetadataFields !== [
        'brand_value' => ['value' => 'Northwind', 'provenance' => 'MERCHANT_CURATED'],
        'category_id' => ['value' => '42', 'provenance' => 'MERCHANT_CURATED'],
    ]
) {
    throw new RuntimeException('Curated scalar metadata did not preserve its exact provenance and remote fields.');
}

$remoteBindingCounts = static function () use ($connection, $resourceConnection): array {
    return [
        'query_sets' => (int)$connection->fetchOne(
            $connection->select()
                ->from($resourceConnection->getTableName('osrw_query_snapshot'), ['COUNT(*)'])
                ->where('remote_query_set_id IS NOT NULL')
        ),
        'search_configurations' => (int)$connection->fetchOne(
            $connection->select()
                ->from($resourceConnection->getTableName('osrw_search_configuration'), ['COUNT(*)'])
                ->where('remote_configuration_id IS NOT NULL')
        ),
        'judgments' => (int)$connection->fetchOne(
            $connection->select()
                ->from($resourceConnection->getTableName('osrw_judgment_run'), ['COUNT(*)'])
                ->where('remote_judgment_id IS NOT NULL')
        ),
        'experiments' => (int)$connection->fetchOne(
            $connection->select()->from(
                $resourceConnection->getTableName('osrw_experiment'),
                ['COUNT(*)']
            )
        ),
        'proposals' => (int)$connection->fetchOne(
            $connection->select()->from(
                $resourceConnection->getTableName('osrw_proposal'),
                ['COUNT(*)']
            )
        ),
    ];
};
$beforeBindings = $remoteBindingCounts();
/** @var SnapshotSchedulePolicyFactory $policyFactory */
$policyFactory = $objectManager->get(SnapshotSchedulePolicyFactory::class);
$policy = $policyFactory->create([
    'store_id' => '1',
    'source_window_days' => '2',
    'minimum_popularity' => '1',
    'positive_result_limit' => '20',
    'zero_result_limit' => '10',
    'total_limit' => '30',
    'include_redirects' => '0',
    'interval_days' => '7',
    'retention_days' => '30',
    'first_run_at' => '2026-08-27T00:00:00+00:00',
]);
/** @var SnapshotScheduleRepository $scheduleRepository */
$scheduleRepository = $objectManager->get(SnapshotScheduleRepository::class);
$scheduleUuid = $scheduleRepository->approve(
    $policy,
    1,
    '2026-08-26T23:59:00+00:00',
    'phase-three-schedule-approval'
);
/** @var ScheduledDraftPreparer $draftPreparer */
$draftPreparer = $objectManager->get(ScheduledDraftPreparer::class);
$draftPreparer->prepare('2026-08-27T00:00:00+00:00');
$afterBindings = $remoteBindingCounts();

if ($afterBindings !== $beforeBindings) {
    throw new RuntimeException('Scheduled draft preparation changed remote evaluation bindings.');
}

$draft = null;

foreach ($snapshotRepository->listRecent() as $row) {
    if (($row['schedule_uuid'] ?? null) === $scheduleUuid && ($row['status'] ?? null) === 'DRAFT') {
        $draft = $row;
        break;
    }
}

if (!is_array($draft)) {
    throw new RuntimeException('The approved schedule did not prepare a reviewable draft.');
}

$draftUuid = (string)$draft['snapshot_uuid'];
$draftRow = $connection->fetchRow(
    $connection->select()
        ->from($resourceConnection->getTableName('osrw_query_snapshot'))
        ->where('snapshot_uuid = ?', $draftUuid)
        ->limit(1)
);
$draftReviewEntries = $snapshotRepository->getDraftReviewEntries($draftUuid);

if (
    !is_array($draftRow)
    || $draftRow['approved_by'] !== null
    || $draftRow['approved_at'] !== null
    || $draftRow['remote_query_set_id'] !== null
    || count($draftReviewEntries) < 5
    || $scheduleRepository->listDue('2026-08-27T00:00:00+00:00') !== []
) {
    throw new RuntimeException('Scheduled snapshot did not remain an unapproved, local-only draft.');
}

fwrite(
    STDOUT,
    json_encode(
        [
            'phase_three' => 'PASS',
            'experiment_uuid' => $experimentUuid,
            'fresh_index_evidence' => true,
            'movement_query_count' => count($freshEvidence['queries']),
            'regression_count' => count($freshEvidence['regressions']),
            'stale_index_evidence' => true,
            'unavailable_document_id' => $removedDocumentId,
            'stale_existing_proposal_blocked' => true,
            'cleanup_preview_resource_count' => count($cleanupPreview),
            'cleanup_delete_action_exposed' => false,
            'curated_metadata_snapshot_uuid' => $metadataSnapshotUuid,
            'curated_metadata_provenance' => 'MERCHANT_CURATED',
            'schedule_uuid' => $scheduleUuid,
            'schedule_policy_sha256' => $policy->getPolicyHash(),
            'draft_snapshot_uuid' => $draftUuid,
            'draft_review_query_count' => count($draftReviewEntries),
            'draft_only' => true,
            'remote_binding_mutation' => false,
        ],
        JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES
    ) . "\n"
);
