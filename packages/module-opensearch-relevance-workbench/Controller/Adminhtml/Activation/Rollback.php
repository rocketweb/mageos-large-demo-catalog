<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Activation;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Backend\Model\Auth\Session;
use Magento\Framework\App\Action\HttpPostActionInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\LiveActivationRepository;
use Psr\Log\LoggerInterface;
use Throwable;

class Rollback extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::apply_live_configuration';

    public function __construct(
        Context $context,
        private readonly LiveActivationRepository $activationRepository,
        private readonly Session $authSession,
        private readonly LoggerInterface $logger
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $storeId = (int)$this->getRequest()->getParam('store_id', 0);
            $actorId = (int)($this->authSession->getUser()?->getId() ?? 0);
            $activationUuid = $this->activationRepository->rollback(
                $storeId,
                $actorId,
                gmdate(DATE_RFC3339),
                bin2hex(random_bytes(16))
            );
            $this->messageManager->addSuccessMessage(__(
                'Previous storefront search state restored as activation %1.',
                $activationUuid
            ));
        } catch (Throwable $exception) {
            $this->logger->error('OpenSearch Relevance Workbench rollback failed', [
                'exception' => $exception,
            ]);
            $this->messageManager->addErrorMessage(__(
                'Rollback failed. No prior live state was available for this store.'
            ));
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'activate',
        ]);
    }
}
