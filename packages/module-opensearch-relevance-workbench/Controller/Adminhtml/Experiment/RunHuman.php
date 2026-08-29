<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Experiment;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Backend\Model\Auth\Session;
use Magento\Framework\App\Action\HttpPostActionInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\HumanExperimentRunService;
use Psr\Log\LoggerInterface;
use Throwable;

class RunHuman extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::run_experiments';

    public function __construct(
        Context $context,
        private readonly HumanExperimentRunService $runService,
        private readonly Session $authSession,
        private readonly LoggerInterface $logger
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $actorId = (int)($this->authSession->getUser()?->getId() ?? 0);
            $experiment = $this->runService->run(
                (string)$this->getRequest()->getParam('snapshot_uuid', ''),
                (string)$this->getRequest()->getParam('baseline_uuid', ''),
                (string)$this->getRequest()->getParam('candidate_uuid', ''),
                (string)$this->getRequest()->getParam('judgment_uuid', ''),
                $actorId,
                gmdate(DATE_RFC3339),
                bin2hex(random_bytes(16))
            );
            $evidence = $experiment->getEvidence();
            $this->messageManager->addSuccessMessage(__(
                'Completed and validated three offline experiments. Local evidence %1 is %2 with NDCG delta %3.',
                $experiment->getExperimentUuid(),
                $evidence->getEligibility(),
                number_format($evidence->getMetricDelta(), 4)
            ));
        } catch (Throwable $exception) {
            $this->logger->error(
                'Human relevance experiment run failed',
                ['exception' => $exception]
            );
            $this->messageManager->addErrorMessage(__(
                'Human experiment run did not complete. Inputs, remote identities, validation, and index freshness must all match.'
            ));
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'compare',
        ]);
    }
}
