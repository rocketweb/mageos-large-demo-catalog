<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Workbench;

use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Framework\View\Result\PageFactory;

class Index extends Action
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::view';

    public function __construct(
        Context $context,
        private readonly PageFactory $pageFactory
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        $page = $this->pageFactory->create();
        $page->getConfig()->getTitle()->prepend((string)__('OpenSearch Relevance Workbench'));

        return $page;
    }
}
