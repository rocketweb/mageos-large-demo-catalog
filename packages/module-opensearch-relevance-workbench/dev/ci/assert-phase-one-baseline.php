<?php

declare(strict_types=1);

use Magento\Framework\App\Bootstrap;
use Magento\Framework\App\ResourceConnection;
use Magento\Framework\App\State;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\StockBaselineCaptureService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\CandidateValidationService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\HumanExperimentRunService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\HumanJudgmentSetFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\HumanRatingQueueService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\CandidateConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\HumanJudgmentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ProposalRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\ConfiguredOpenSearchClientProvider;
use MageOS\OpenSearchRelevanceWorkbench\Model\Proposal\ProposalCreationService;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPreviewService;

if ($argc !== 2) {
    fwrite(STDERR, "Usage: php assert-phase-one-baseline.php /path/to/mageos\n");
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
$queryTexts = ['boots', 'red dress', 'MUG-001', 'café table', 'winter coat'];

foreach ($queryTexts as $ordinal => $queryText) {
    $fixtureRow = [
        'query_text' => $queryText,
        'num_results' => 3 + $ordinal,
        'popularity' => 30 - $ordinal,
        'redirect' => null,
        'store_id' => 1,
        'display_in_terms' => 1,
        'is_active' => 1,
        'is_processed' => 1,
        'updated_at' => sprintf('2026-08-26 13:%02d:00', $ordinal),
    ];
    $connection->insertOnDuplicate($searchQueryTable, $fixtureRow, array_keys($fixtureRow));
}

$parameters = [
    'store_id' => 1,
    'source_window_start' => '2026-08-26T00:00:00+00:00',
    'source_window_end' => '2026-08-26T23:59:59+00:00',
    'minimum_popularity' => 1,
    'positive_result_limit' => 20,
    'zero_result_limit' => 10,
    'total_limit' => 30,
    'include_redirects' => '0',
];
/** @var SnapshotPreviewService $previewService */
$previewService = $objectManager->get(SnapshotPreviewService::class);
$preview = $previewService->create($parameters);
$approved = $preview->approve(
    $preview->getSnapshotHash(),
    1,
    '2026-08-26T16:00:00+00:00'
);

if (count($approved->getEntries()) < 5) {
    throw new RuntimeException('The approved fixture snapshot did not contain five safe validation queries.');
}

/** @var QuerySnapshotRepository $repository */
$repository = $objectManager->get(QuerySnapshotRepository::class);
$snapshotUuid = $repository->saveApproved(
    $preview,
    $approved,
    'phase-one-baseline-fixture'
);
$persistedSnapshot = $repository->getApproved($snapshotUuid);

if ($persistedSnapshot->getSnapshotHash() !== $approved->getSnapshotHash()) {
    throw new RuntimeException('The approved snapshot did not reconstruct from immutable local records.');
}

/** @var ConfiguredOpenSearchClientProvider $clientProvider */
$clientProvider = $objectManager->get(ConfiguredOpenSearchClientProvider::class);
$openSearchClient = $clientProvider->get();
$aliasResponse = $openSearchClient->indices()->getAlias(['name' => 'magento2_product_1']);
$physicalIndices = array_keys($aliasResponse);

if (count($physicalIndices) !== 1) {
    throw new RuntimeException('Fixture catalog alias did not resolve to exactly one physical index.');
}

$fixturePhysicalIndex = $physicalIndices[0];
$fixtureProducts = [
    '910001' => ['name' => 'Trail footwear', 'sku' => 'BOOT-HIKE', 'description' => 'boots for winter trails'],
    '910002' => ['name' => 'Boots decoration', 'sku' => 'DECOR-BOOT', 'description' => 'home ornament'],
    '910003' => ['name' => 'Evening garment', 'sku' => 'DRESS-RED', 'description' => 'red dress for formal events'],
    '910004' => ['name' => 'Red dress poster', 'sku' => 'POSTER-DRESS', 'description' => 'wall art'],
    '910005' => ['name' => 'Ceramic mug', 'sku' => 'MUG-001', 'description' => 'mug for a café table'],
    '910006' => ['name' => 'Café table sign', 'sku' => 'SIGN-CAFE', 'description' => 'wall art'],
    '910007' => ['name' => 'Insulated outerwear', 'sku' => 'COAT-WINTER', 'description' => 'winter coat'],
    '910008' => ['name' => 'Winter coat poster', 'sku' => 'POSTER-COAT', 'description' => 'wall art'],
];

foreach ($fixtureProducts as $documentId => $document) {
    $openSearchClient->index([
        'index' => $fixturePhysicalIndex,
        'id' => $documentId,
        'body' => $document + [
            'short_description' => $document['description'],
            'manufacturer_value' => 'Fixture',
            'color_value' => 'red',
            'status_value' => 'Enabled',
            'url_key' => strtolower(str_replace(' ', '-', $document['name'])),
            'tax_class_id_value' => 'Taxable Goods',
            'price_0_1' => 10.0,
            'category_ids' => [2],
        ],
    ]);
}
$openSearchClient->indices()->refresh(['index' => $fixturePhysicalIndex]);
/** @var StockBaselineCaptureService $captureService */
$captureService = $objectManager->get(StockBaselineCaptureService::class);
$capture = $captureService->capture($persistedSnapshot);
$template = $capture->getCaptureResult()->getTemplate();
$templateArray = $template->getTemplate();
$targetIndex = $templateArray['index'] ?? null;
$indexEvidence = $capture->getIndexEvidence();
$remoteConfiguration = $capture->getRemoteConfiguration();
$fieldCapabilities = $capture->getFieldCapabilities();
$configurationHash = $capture->getConfigurationHash();

if (!is_string($targetIndex) || $targetIndex === '') {
    throw new RuntimeException('The stock request did not expose its exact target index.');
}

if ($indexEvidence->getAlias() !== $targetIndex) {
    throw new RuntimeException('Index evidence did not preserve the captured target alias.');
}

if ($remoteConfiguration['index'] !== $indexEvidence->getPhysicalIndex()) {
    throw new RuntimeException('Remote configuration did not use the evidence-resolved physical index.');
}

if (!str_contains($remoteConfiguration['query'], '{{queryText}}')) {
    throw new RuntimeException('Remote baseline query did not preserve its query-text variable.');
}

if (count($capture->getCaptureResult()->getValidationEvidence()) !== 5) {
    throw new RuntimeException('Baseline round-trip did not preserve five validation samples.');
}

if (
    !isset($fieldCapabilities['name'], $fieldCapabilities['sku'])
    || !$fieldCapabilities['name']['searchable']
    || !$fieldCapabilities['sku']['searchable']
) {
    throw new RuntimeException('Mapped field capabilities did not include searchable name and SKU fields.');
}

if (preg_match('/\A[0-9a-f]{64}\z/', $configurationHash) !== 1) {
    throw new RuntimeException('Baseline configuration identity is not a canonical SHA-256 digest.');
}

/** @var BaselineConfigurationRepository $configurationRepository */
$configurationRepository = $objectManager->get(BaselineConfigurationRepository::class);
$configurationUuid = $configurationRepository->save(
    $capture,
    $persistedSnapshot->getStoreId(),
    1,
    '2026-08-26T16:01:00+00:00',
    'phase-one-baseline-persistence'
);
$idempotentConfigurationUuid = $configurationRepository->save(
    $capture,
    $persistedSnapshot->getStoreId(),
    1,
    '2026-08-26T16:02:00+00:00',
    'phase-one-baseline-repeat'
);

if ($configurationUuid !== $idempotentConfigurationUuid) {
    throw new RuntimeException('Identical stock baseline capture did not resolve to one local configuration.');
}

$persistedBaseline = $configurationRepository->get($configurationUuid);
/** @var CandidateValidationService $candidateValidationService */
$candidateValidationService = $objectManager->get(CandidateValidationService::class);
$validatedCandidate = $candidateValidationService->build(
    $persistedBaseline,
    $persistedSnapshot,
    ['description' => 20.0]
);

if (count($validatedCandidate->getValidationEvidence()) !== 5) {
    throw new RuntimeException('Candidate did not execute five bounded validation searches.');
}

/** @var CandidateConfigurationRepository $candidateRepository */
$candidateRepository = $objectManager->get(CandidateConfigurationRepository::class);
$candidateUuid = $candidateRepository->save(
    $validatedCandidate,
    1,
    '2026-08-26T16:03:00+00:00',
    'phase-one-candidate-persistence'
);
$idempotentCandidateUuid = $candidateRepository->save(
    $validatedCandidate,
    1,
    '2026-08-26T16:04:00+00:00',
    'phase-one-candidate-repeat'
);

if ($candidateUuid !== $idempotentCandidateUuid) {
    throw new RuntimeException('Identical candidate did not resolve to one local configuration.');
}

$persistedCandidate = $candidateRepository->get($candidateUuid);
/** @var HumanRatingQueueService $ratingQueueService */
$ratingQueueService = $objectManager->get(HumanRatingQueueService::class);
$ratingQueue = $ratingQueueService->build(
    $persistedBaseline,
    $persistedCandidate,
    $persistedSnapshot
);
$relevantDocuments = [
    'boots' => '910001',
    'red dress' => '910003',
    'MUG-001' => '910005',
    'café table' => '910005',
    'winter coat' => '910007',
];
$ratings = [];

foreach ($ratingQueue as $item) {
    $relevantDocumentId = $relevantDocuments[$item['query_text']] ?? null;

    if ($relevantDocumentId === null) {
        throw new RuntimeException('Fixture rating queue contained an unexpected approved query.');
    }

    $ratings[] = [
        'query_hash' => $item['query_hash'],
        'document_id' => $item['document_id'],
        'rating' => $item['document_id'] === $relevantDocumentId ? 1.0 : 0.0,
    ];
}
/** @var HumanJudgmentSetFactory $humanJudgmentSetFactory */
$humanJudgmentSetFactory = $objectManager->get(HumanJudgmentSetFactory::class);
$humanJudgmentSet = $humanJudgmentSetFactory->create(
    $persistedSnapshot,
    $persistedBaseline->getIndexEvidenceHash(),
    $ratings,
    1,
    '2026-08-26T16:05:00+00:00'
);
/** @var HumanJudgmentRepository $humanJudgmentRepository */
$humanJudgmentRepository = $objectManager->get(HumanJudgmentRepository::class);
$humanJudgmentUuid = $humanJudgmentRepository->save(
    $humanJudgmentSet,
    $snapshotUuid,
    $persistedBaseline->getIndexEvidenceUuid(),
    'phase-one-human-judgment'
);
$idempotentHumanJudgmentUuid = $humanJudgmentRepository->save(
    $humanJudgmentSet,
    $snapshotUuid,
    $persistedBaseline->getIndexEvidenceUuid(),
    'phase-one-human-repeat'
);

if ($humanJudgmentUuid !== $idempotentHumanJudgmentUuid) {
    throw new RuntimeException('Identical human ratings did not resolve to one local judgment set.');
}

/** @var HumanExperimentRunService $experimentRunService */
$experimentRunService = $objectManager->get(HumanExperimentRunService::class);
$experiment = $experimentRunService->run(
    $snapshotUuid,
    $configurationUuid,
    $candidateUuid,
    $humanJudgmentUuid,
    1,
    '2026-08-26T16:06:00+00:00',
    'phase-one-human-experiment'
);

if (
    $experiment->getEvidence()->getEligibility() !== 'EXPLORATORY'
    || $experiment->getEvidence()->getMetricDelta() < 0.01
    || $experiment->getEvidence()->getJudgedCoverage() !== 1.0
) {
    throw new RuntimeException('Fixture candidate did not produce fully judged, otherwise-winning evidence.');
}

$remoteExperimentIds = $experiment->getRemoteExperimentIds();

if (count($remoteExperimentIds) !== 3) {
    throw new RuntimeException('Phase 1 did not persist the exact three remote experiments.');
}

$resumedExperiment = $experimentRunService->run(
    $snapshotUuid,
    $configurationUuid,
    $candidateUuid,
    $humanJudgmentUuid,
    1,
    '2026-08-26T16:07:00+00:00',
    'phase-one-human-resume'
);

if (
    $resumedExperiment->getExperimentUuid() !== $experiment->getExperimentUuid()
    || $resumedExperiment->getRemoteExperimentIds() !== $remoteExperimentIds
) {
    throw new RuntimeException('Identical experiment inputs did not reuse all owned remote resources.');
}

/** @var ExperimentRepository $experimentRepository */
$experimentRepository = $objectManager->get(ExperimentRepository::class);
$experimentRepository->accept(
    $experiment->getExperimentUuid(),
    1,
    '2026-08-26T16:08:00+00:00',
    'phase-one-fixture-acceptance'
);
$acceptedExperiment = $experimentRepository->getCompleted($experiment->getExperimentUuid());

if (
    $acceptedExperiment->getState() !== 'ACCEPTED'
    || $acceptedExperiment->getEvidence()->getEligibility() !== 'WINNER'
) {
    throw new RuntimeException('Explicit fixture acceptance did not produce winner evidence.');
}

/** @var ProposalCreationService $proposalCreationService */
$proposalCreationService = $objectManager->get(ProposalCreationService::class);
$proposalUuid = $proposalCreationService->create(
    $experiment->getExperimentUuid(),
    1,
    '2026-08-26T16:09:00+00:00',
    'phase-one-proposal-export'
);
/** @var ProposalRepository $proposalRepository */
$proposalRepository = $objectManager->get(ProposalRepository::class);
$proposal = $proposalRepository->getArtifact($proposalUuid);
$proposalValue = json_decode($proposal->getCanonicalJson(), true, 512, JSON_THROW_ON_ERROR);

if (
    ($proposalValue['target_type'] ?? null) !== 'review_only'
    || ($proposalValue['application']['supported'] ?? null) !== false
    || hash('sha256', $proposal->getCanonicalJson()) !== $proposal->getArtifactHash()
) {
    throw new RuntimeException('Review-only proposal artifact did not preserve its safety contract.');
}

foreach (array_keys($relevantDocuments) as $queryText) {
    if (str_contains($proposal->getCanonicalJson(), $queryText)) {
        throw new RuntimeException('Review-only proposal leaked approved query text.');
    }
}

$acceptedRerun = $experimentRunService->run(
    $snapshotUuid,
    $configurationUuid,
    $candidateUuid,
    $humanJudgmentUuid,
    1,
    '2026-08-26T16:10:00+00:00',
    'phase-one-accepted-resume'
);
$idempotentProposalUuid = $proposalCreationService->create(
    $experiment->getExperimentUuid(),
    1,
    '2026-08-26T16:11:00+00:00',
    'phase-one-proposal-repeat'
);

if (
    $acceptedRerun->getState() !== 'ACCEPTED'
    || $acceptedRerun->getEvidence()->getEligibility() !== 'WINNER'
    || $idempotentProposalUuid !== $proposalUuid
) {
    throw new RuntimeException('Accepted evidence or proposal identity changed during an identical rerun.');
}

fwrite(
    STDOUT,
    json_encode(
        [
            'phase_one_baseline' => 'PASS',
            'snapshot_uuid' => $snapshotUuid,
            'captured_target' => $targetIndex,
            'physical_index' => $indexEvidence->getPhysicalIndex(),
            'index_evidence_sha256' => $indexEvidence->getEvidenceHash(),
            'template_sha256' => $template->getTemplateHash(),
            'configuration_sha256' => $configurationHash,
            'configuration_uuid' => $configurationUuid,
            'idempotent_save' => true,
            'candidate_uuid' => $candidateUuid,
            'candidate_sha256' => $validatedCandidate->getCandidate()->getConfigurationHash(),
            'candidate_validation_sample_count' => count($validatedCandidate->getValidationEvidence()),
            'candidate_idempotent_save' => true,
            'rating_queue_pair_count' => count($ratingQueue),
            'human_judgment_uuid' => $humanJudgmentUuid,
            'human_judgment_sha256' => $humanJudgmentSet->getJudgmentHash(),
            'human_judgment_idempotent_save' => true,
            'experiment_uuid' => $experiment->getExperimentUuid(),
            'remote_experiment_ids' => $remoteExperimentIds,
            'experiment_resumable' => true,
            'baseline_ndcg_at_10' => $experiment->getEvidence()->getBaselineMetric(),
            'candidate_ndcg_at_10' => $experiment->getEvidence()->getCandidateMetric(),
            'ndcg_delta' => $experiment->getEvidence()->getMetricDelta(),
            'judged_coverage' => $experiment->getEvidence()->getJudgedCoverage(),
            'accepted_fixture_evidence' => true,
            'proposal_uuid' => $proposalUuid,
            'proposal_sha256' => $proposal->getArtifactHash(),
            'proposal_idempotent_save' => true,
            'validation_sample_count' => count($capture->getCaptureResult()->getValidationEvidence()),
            'searchable_fields' => array_keys(array_filter(
                $fieldCapabilities,
                static fn (array $capability): bool => $capability['searchable']
            )),
            'owned_evaluation_resource_mutation' => true,
            'live_search_mutation' => false,
        ],
        JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES
    ) . "\n"
);
