<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Observer;

use Magento\Framework\Event\Observer;
use Magento\Framework\Event\ObserverInterface;
use Magento\Store\Model\StoreManagerInterface;
use RocketWeb\LabCatalog\Model\Catalog\StoreProvisioner;

class AddNavigationLayout implements ObserverInterface
{
    public function __construct(private readonly StoreManagerInterface $storeManager)
    {
    }

    public function execute(Observer $observer): void
    {
        if ($this->storeManager->getWebsite()->getCode() === StoreProvisioner::WEBSITE_CODE) {
            $observer->getLayout()->getUpdate()->addHandle('wands_catalog_navigation');
        }
    }
}
