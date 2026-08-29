<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Schedule;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Backend\Model\Auth\Session;
use Magento\Framework\App\Action\HttpPostActionInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\SnapshotScheduleRepository;
use Throwable;

class Pause extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::manage_settings';

    public function __construct(
        Context $context,
        private readonly SnapshotScheduleRepository $scheduleRepository,
        private readonly Session $authSession
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $scheduleUuid = (string)$this->getRequest()->getParam('schedule_uuid', '');
            $actorId = (int)($this->authSession->getUser()?->getId() ?? 0);
            $this->scheduleRepository->pause(
                $scheduleUuid,
                $actorId,
                gmdate(DATE_RFC3339),
                bin2hex(random_bytes(16))
            );
            $this->messageManager->addSuccessMessage(__('Paused snapshot schedule %1.', $scheduleUuid));
        } catch (Throwable) {
            $this->messageManager->addErrorMessage(__('Snapshot schedule could not be paused.'));
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'snapshot',
        ]);
    }
}
