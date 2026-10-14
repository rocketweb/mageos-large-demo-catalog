<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Test\Unit\Observer;

use Magento\Framework\Event\Observer;
use Magento\Framework\View\Layout;
use Magento\Framework\View\Model\Layout\Merge;
use Magento\Store\Model\StoreManagerInterface;
use Magento\Store\Model\Website;
use PHPUnit\Framework\TestCase;
use RocketWeb\LabCatalog\Observer\AddNavigationLayout;

require_once dirname(__DIR__, 3) . '/Model/Catalog/StoreProvisioner.php';
require_once dirname(__DIR__, 3) . '/Observer/AddNavigationLayout.php';

class AddNavigationLayoutTest extends TestCase
{
    public function testWandsWebsiteGetsNavigationStyles(): void
    {
        $update = $this->createMock(Merge::class);
        $update->expects(self::once())->method('addHandle')->with('wands_catalog_navigation')->willReturnSelf();
        $this->execute('wands', $update);
    }

    public function testOtherWebsitesKeepTheirOwnNavigationStyles(): void
    {
        $update = $this->createMock(Merge::class);
        $update->expects(self::never())->method('addHandle');
        $this->execute('base', $update);
    }

    private function execute(string $websiteCode, Merge $update): void
    {
        $website = $this->createStub(Website::class);
        $website->method('getCode')->willReturn($websiteCode);
        $stores = $this->createStub(StoreManagerInterface::class);
        $stores->method('getWebsite')->willReturn($website);
        $layout = $this->createStub(Layout::class);
        $layout->method('getUpdate')->willReturn($update);
        (new AddNavigationLayout($stores))->execute(new Observer(['layout' => $layout]));
    }
}
