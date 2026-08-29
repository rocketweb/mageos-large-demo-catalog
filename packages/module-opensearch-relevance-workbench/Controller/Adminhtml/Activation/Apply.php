<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Activation;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Backend\Model\Auth\Session;
use Magento\Framework\App\Action\HttpPostActionInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Activation\LiveActivationService;
use Psr\Log\LoggerInterface;
use Throwable;

class Apply extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::apply_live_configuration';

    public function __construct(
        Context $context,
        private readonly LiveActivationService $activationService,
        private readonly Session $authSession,
        private readonly LoggerInterface $logger
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $experimentUuid = (string)$this->getRequest()->getParam('experiment_uuid', '');
            $actorId = (int)($this->authSession->getUser()?->getId() ?? 0);
            $activationUuid = $this->activationService->activate(
                $experimentUuid,
                $actorId,
                gmdate(DATE_RFC3339),
                bin2hex(random_bytes(16))
            );
            $this->messageManager->addSuccessMessage(__(
                'Candidate activated. Live activation %1 is now serving storefront search.',
                $activationUuid
            ));
        } catch (Throwable $exception) {
            $this->logger->error('OpenSearch Relevance Workbench live activation failed', [
                'exception' => $exception,
            ]);
            $this->messageManager->addErrorMessage(__(
                'Activation failed. The candidate must be an accepted winner and its exact index evidence must still be current.'
            ));
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'activate',
        ]);
    }
}
