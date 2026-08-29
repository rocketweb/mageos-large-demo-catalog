<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Judgment;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Framework\App\Action\HttpPostActionInterface;
use Magento\Framework\App\Request\DataPersistorInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\HumanRatingQueueService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\CandidateConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use Throwable;

class PrepareQueue extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::curate_ratings';

    public function __construct(
        Context $context,
        private readonly BaselineConfigurationRepository $baselineRepository,
        private readonly CandidateConfigurationRepository $candidateRepository,
        private readonly QuerySnapshotRepository $snapshotRepository,
        private readonly HumanRatingQueueService $queueService,
        private readonly DataPersistorInterface $dataPersistor
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $candidate = $this->candidateRepository->get(
                (string)$this->getRequest()->getParam('candidate_uuid', '')
            );
            $baseline = $this->baselineRepository->get($candidate->getParentBaselineUuid());
            $snapshotUuid = (string)$this->getRequest()->getParam('snapshot_uuid', '');
            $snapshot = $this->snapshotRepository->getApproved($snapshotUuid);
            $items = $this->queueService->build($baseline, $candidate, $snapshot);
            $this->dataPersistor->set('osrw_rating_queue', [
                'candidate_uuid' => $candidate->getConfigurationUuid(),
                'baseline_uuid' => $baseline->getConfigurationUuid(),
                'snapshot_uuid' => $snapshotUuid,
                'items' => $items,
            ]);
            $this->messageManager->addSuccessMessage(
                __('Prepared %1 frozen query-product pairs for human review.', count($items))
            );
        } catch (Throwable) {
            $this->messageManager->addErrorMessage(
                __('Human rating queue preparation failed. The index may be stale or the selected inputs incompatible.')
            );
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'judge',
        ]);
    }
}
