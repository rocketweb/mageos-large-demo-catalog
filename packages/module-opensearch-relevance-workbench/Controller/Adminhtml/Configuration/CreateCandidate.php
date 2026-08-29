<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Configuration;

use InvalidArgumentException;
use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Backend\Model\Auth\Session;
use Magento\Framework\App\Action\HttpPostActionInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\CandidateValidationService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\CandidateConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use Throwable;

class CreateCandidate extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::manage_configurations';

    public function __construct(
        Context $context,
        private readonly BaselineConfigurationRepository $baselineRepository,
        private readonly QuerySnapshotRepository $snapshotRepository,
        private readonly CandidateValidationService $validationService,
        private readonly CandidateConfigurationRepository $candidateRepository,
        private readonly Session $authSession
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $field = (string)$this->getRequest()->getParam('field', '');
            $boostValue = $this->getRequest()->getParam('boost');

            if ($field === '' || !is_numeric($boostValue)) {
                throw new InvalidArgumentException('Candidate field and boost are required');
            }

            $baseline = $this->baselineRepository->get(
                (string)$this->getRequest()->getParam('baseline_uuid', '')
            );
            $snapshot = $this->snapshotRepository->getApproved(
                (string)$this->getRequest()->getParam('snapshot_uuid', '')
            );
            $validatedCandidate = $this->validationService->build(
                $baseline,
                $snapshot,
                [$field => (float)$boostValue]
            );
            $userId = (int)($this->authSession->getUser()?->getId() ?? 0);
            $candidateUuid = $this->candidateRepository->save(
                $validatedCandidate,
                $userId,
                gmdate(DATE_RFC3339),
                bin2hex(random_bytes(16))
            );
            $this->messageManager->addSuccessMessage(
                __('Compiled and locally validated candidate %1.', $candidateUuid)
            );
        } catch (Throwable) {
            $this->messageManager->addErrorMessage(
                __('Candidate creation failed. Use an offered field and a same-store snapshot with at least five queries.')
            );
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'tune',
        ]);
    }
}
