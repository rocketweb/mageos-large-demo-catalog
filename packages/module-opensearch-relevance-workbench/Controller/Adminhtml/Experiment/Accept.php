<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Experiment;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Backend\Model\Auth\Session;
use Magento\Framework\App\Action\HttpPostActionInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use Throwable;

class Accept extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::run_experiments';

    public function __construct(
        Context $context,
        private readonly ExperimentRepository $experimentRepository,
        private readonly Session $authSession
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $experimentUuid = (string)$this->getRequest()->getParam('experiment_uuid', '');
            $actorId = (int)($this->authSession->getUser()?->getId() ?? 0);
            $this->experimentRepository->accept(
                $experimentUuid,
                $actorId,
                gmdate(DATE_RFC3339),
                bin2hex(random_bytes(16))
            );
            $this->messageManager->addSuccessMessage(
                __('Accepted offline relevance evidence %1 for activation review and evidence export.', $experimentUuid)
            );
        } catch (Throwable) {
            $this->messageManager->addErrorMessage(__(
                'Evidence was not accepted. Only fresh, fully judged, validated, otherwise-winning evidence is eligible.'
            ));
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'compare',
        ]);
    }
}
