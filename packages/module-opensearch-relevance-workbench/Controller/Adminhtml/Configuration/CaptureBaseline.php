<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Configuration;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Backend\Model\Auth\Session;
use Magento\Framework\App\Action\HttpPostActionInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\StockBaselineCaptureService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use Throwable;

class CaptureBaseline extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::manage_configurations';

    public function __construct(
        Context $context,
        private readonly QuerySnapshotRepository $snapshotRepository,
        private readonly StockBaselineCaptureService $captureService,
        private readonly BaselineConfigurationRepository $configurationRepository,
        private readonly Session $authSession
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $snapshotUuid = (string)$this->getRequest()->getParam('snapshot_uuid', '');
            $snapshot = $this->snapshotRepository->getApproved($snapshotUuid);
            $capture = $this->captureService->capture($snapshot);
            $userId = (int)($this->authSession->getUser()?->getId() ?? 0);
            $configurationUuid = $this->configurationRepository->save(
                $capture,
                $snapshot->getStoreId(),
                $userId,
                gmdate(DATE_RFC3339),
                bin2hex(random_bytes(16))
            );
            $this->messageManager->addSuccessMessage(
                __('Captured and locally verified stock baseline %1.', $configurationUuid)
            );
        } catch (Throwable) {
            $this->messageManager->addErrorMessage(
                __('Baseline capture failed. Use an approved snapshot with at least five distinct queries.')
            );
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'tune',
        ]);
    }
}
