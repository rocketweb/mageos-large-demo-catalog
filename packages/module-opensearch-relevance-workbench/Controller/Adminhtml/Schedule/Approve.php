<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Schedule;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Backend\Model\Auth\Session;
use Magento\Framework\App\Action\HttpPostActionInterface;
use Magento\Store\Api\StoreRepositoryInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\SnapshotScheduleRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Schedule\SnapshotSchedulePolicyFactory;
use Throwable;

class Approve extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::manage_settings';

    public function __construct(
        Context $context,
        private readonly SnapshotSchedulePolicyFactory $policyFactory,
        private readonly SnapshotScheduleRepository $scheduleRepository,
        private readonly StoreRepositoryInterface $storeRepository,
        private readonly Session $authSession
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $policy = $this->policyFactory->create($this->getRequest()->getParams());
            $this->storeRepository->getActiveStoreById($policy->getStoreId());
            $actorId = (int)($this->authSession->getUser()?->getId() ?? 0);
            $scheduleUuid = $this->scheduleRepository->approve(
                $policy,
                $actorId,
                gmdate(DATE_RFC3339),
                bin2hex(random_bytes(16))
            );
            $this->messageManager->addSuccessMessage(__(
                'Approved snapshot schedule %1. Cron may prepare drafts only.',
                $scheduleUuid
            ));
        } catch (Throwable) {
            $this->messageManager->addErrorMessage(__(
                'Snapshot schedule approval failed. Review every source, size, timing, and retention bound.'
            ));
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'snapshot',
        ]);
    }
}
