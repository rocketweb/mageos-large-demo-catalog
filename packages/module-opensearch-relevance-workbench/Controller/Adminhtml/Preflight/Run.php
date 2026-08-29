<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Preflight;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Framework\App\Action\HttpPostActionInterface;
use Magento\Framework\App\Request\DataPersistorInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Admin\PreflightService;
use Throwable;

class Run extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::view';

    public function __construct(
        Context $context,
        private readonly PreflightService $preflightService,
        private readonly DataPersistorInterface $dataPersistor
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $result = $this->preflightService->run();
            $this->dataPersistor->set('osrw_preflight_result', $result);
            $this->messageManager->addSuccessMessage(__('Preflight completed.'));
        } catch (Throwable) {
            $this->dataPersistor->set('osrw_preflight_result', [
                'human_workflow_ready' => false,
                'llm_workflow_ready' => false,
                'reason_codes' => ['PREFLIGHT_UNAVAILABLE'],
            ]);
            $this->messageManager->addErrorMessage(
                __('Preflight could not reach the configured stock OpenSearch service.')
            );
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'readiness',
        ]);
    }
}
