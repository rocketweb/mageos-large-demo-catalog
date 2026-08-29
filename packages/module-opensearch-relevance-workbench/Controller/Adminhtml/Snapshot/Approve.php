<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Snapshot;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Backend\Model\Auth\Session;
use Magento\Framework\App\Action\HttpPostActionInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPreviewService;
use Throwable;

class Approve extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::approve_snapshots';

    public function __construct(
        Context $context,
        private readonly SnapshotPreviewService $previewService,
        private readonly QuerySnapshotRepository $snapshotRepository,
        private readonly Session $authSession
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $parameters = $this->getRequest()->getParams();
            $preview = $this->previewService->create($parameters);
            $userId = (int)($this->authSession->getUser()?->getId() ?? 0);
            $approved = $preview->approve(
                (string)($parameters['snapshot_hash'] ?? ''),
                $userId,
                gmdate(DATE_RFC3339)
            );
            $snapshotUuid = $this->snapshotRepository->saveApproved(
                $preview,
                $approved,
                bin2hex(random_bytes(16))
            );
            $this->messageManager->addSuccessMessage(
                __('Approved immutable query snapshot %1.', $snapshotUuid)
            );
        } catch (Throwable) {
            $this->messageManager->addErrorMessage(
                __('Snapshot approval failed. Re-run the preview and approve its current exact hash.')
            );
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'snapshot',
        ]);
    }
}
