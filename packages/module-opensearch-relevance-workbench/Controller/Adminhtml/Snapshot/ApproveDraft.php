<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Snapshot;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Backend\Model\Auth\Session;
use Magento\Framework\App\Action\HttpPostActionInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use Throwable;

class ApproveDraft extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::approve_snapshots';

    public function __construct(
        Context $context,
        private readonly QuerySnapshotRepository $snapshotRepository,
        private readonly Session $authSession
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $snapshotUuid = (string)$this->getRequest()->getParam('snapshot_uuid', '');
            $expectedHash = (string)$this->getRequest()->getParam('snapshot_hash', '');
            $actorId = (int)($this->authSession->getUser()?->getId() ?? 0);
            $this->snapshotRepository->approveDraft(
                $snapshotUuid,
                $expectedHash,
                $actorId,
                gmdate(DATE_RFC3339),
                bin2hex(random_bytes(16))
            );
            $this->messageManager->addSuccessMessage(
                __('Approved exact scheduled snapshot draft %1.', $snapshotUuid)
            );
        } catch (Throwable) {
            $this->messageManager->addErrorMessage(__(
                'Scheduled draft approval failed. Review the current exact hash before approving.'
            ));
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'snapshot',
        ]);
    }
}
