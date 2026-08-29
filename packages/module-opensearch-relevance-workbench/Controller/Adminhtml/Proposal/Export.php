<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Proposal;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Backend\Model\Auth\Session;
use Magento\Framework\App\Action\HttpPostActionInterface;
use Magento\Framework\Controller\Result\Raw;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ProposalRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Proposal\ProposalCreationService;
use Psr\Log\LoggerInterface;
use Throwable;

class Export extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::export_proposals';

    public function __construct(
        Context $context,
        private readonly ProposalCreationService $proposalCreationService,
        private readonly ProposalRepository $proposalRepository,
        private readonly Session $authSession,
        private readonly Raw $rawResult,
        private readonly LoggerInterface $logger
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $experimentUuid = (string)$this->getRequest()->getParam('experiment_uuid', '');
            $actorId = (int)($this->authSession->getUser()?->getId() ?? 0);
            $proposalUuid = $this->proposalCreationService->create(
                $experimentUuid,
                $actorId,
                gmdate(DATE_RFC3339),
                bin2hex(random_bytes(16))
            );
            $artifact = $this->proposalRepository->getArtifact($proposalUuid);
            $result = $this->rawResult;
            $result->setHeader('Content-Type', 'application/json', true);
            $result->setHeader(
                'Content-Disposition',
                'attachment; filename="' . $artifact->getFilename() . '"',
                true
            );
            $result->setHeader('X-Content-Type-Options', 'nosniff', true);
            $result->setContents($artifact->getCanonicalJson());

            return $result;
        } catch (Throwable $exception) {
            $this->logger->error(
                'Relevance evidence package export failed',
                ['exception' => $exception]
            );
            $this->messageManager->addErrorMessage(__(
                'Proposal export failed. The experiment must be an explicitly accepted winner with matching local evidence.'
            ));

            return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
                '_fragment' => 'compare',
            ]);
        }
    }
}
