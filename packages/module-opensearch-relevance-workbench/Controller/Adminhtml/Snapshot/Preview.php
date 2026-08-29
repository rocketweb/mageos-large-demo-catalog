<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Snapshot;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Framework\App\Action\HttpPostActionInterface;
use Magento\Framework\App\Request\DataPersistorInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\QuerySnapshotEntry;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPreviewService;
use Throwable;

class Preview extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::preview_queries';

    public function __construct(
        Context $context,
        private readonly SnapshotPreviewService $previewService,
        private readonly DataPersistorInterface $dataPersistor
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        $parameters = $this->getRequest()->getParams();

        try {
            $preview = $this->previewService->create($parameters);
            $this->dataPersistor->set('osrw_snapshot_preview', [
                'parameters' => $this->approvedParameters($parameters),
                'snapshot_hash' => $preview->getSnapshotHash(),
                'source_count' => $preview->getSourceCount(),
                'selected_count' => $preview->getSelectedCount(),
                'excluded_counts' => $preview->getExcludedCounts(),
                'entries' => array_map(
                    static fn (QuerySnapshotEntry $entry): array => [
                        'query_text' => $entry->getQueryText(),
                        'query_hash' => $entry->getQueryHash(),
                        'popularity' => $entry->getPopularity(),
                        'result_count' => $entry->getResultCount(),
                        'custom_fields' => $entry->getCustomFields(),
                    ],
                    $preview->getEntries()
                ),
            ]);
            $this->messageManager->addSuccessMessage(
                __('Preview prepared. Approval is bound to the displayed SHA-256 hash.')
            );
        } catch (Throwable) {
            $this->messageManager->addErrorMessage(
                __('The query preview could not be prepared from the selected store and policy.')
            );
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'snapshot',
        ]);
    }

    /**
     * @param array<string, mixed> $parameters
     * @return array<string, int|string>
     */
    private function approvedParameters(array $parameters): array
    {
        return [
            'store_id' => (int)($parameters['store_id'] ?? 0),
            'source_window_start' => (string)($parameters['source_window_start'] ?? ''),
            'source_window_end' => (string)($parameters['source_window_end'] ?? ''),
            'minimum_popularity' => (int)($parameters['minimum_popularity'] ?? 0),
            'positive_result_limit' => (int)($parameters['positive_result_limit'] ?? 0),
            'zero_result_limit' => (int)($parameters['zero_result_limit'] ?? 0),
            'total_limit' => (int)($parameters['total_limit'] ?? 0),
            'include_redirects' => ($parameters['include_redirects'] ?? null) === '1' ? '1' : '0',
        ];
    }
}
