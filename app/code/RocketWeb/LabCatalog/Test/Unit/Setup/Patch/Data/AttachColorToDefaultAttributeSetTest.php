<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Test\Unit\Setup\Patch\Data;

use Magento\Catalog\Model\Product;
use Magento\Eav\Setup\EavSetup;
use Magento\Eav\Setup\EavSetupFactory;
use Magento\Framework\DB\Adapter\AdapterInterface;
use Magento\Framework\Setup\ModuleDataSetupInterface;
use PHPUnit\Framework\TestCase;
use RocketWeb\LabCatalog\Setup\Patch\Data\AttachColorToDefaultAttributeSet;

require_once dirname(__DIR__, 5) . '/Setup/Patch/Data/AttachColorToDefaultAttributeSet.php';

class AttachColorToDefaultAttributeSetTest extends TestCase
{
    public function testApplyAssignsColorToDefaultProductAttributeSet(): void
    {
        $connection = $this->createMock(AdapterInterface::class);
        $connection->expects(self::once())->method('startSetup');
        $connection->expects(self::once())->method('endSetup');

        $moduleDataSetup = $this->createMock(ModuleDataSetupInterface::class);
        $moduleDataSetup->expects(self::exactly(2))
            ->method('getConnection')
            ->willReturn($connection);

        $eavSetup = $this->createMock(EavSetup::class);
        $eavSetup->expects(self::once())
            ->method('getDefaultAttributeSetId')
            ->with(Product::ENTITY)
            ->willReturn(4);
        $eavSetup->expects(self::once())
            ->method('addAttributeToSet')
            ->with(Product::ENTITY, 4, 'WANDS Merchandising', 'color');

        $eavSetupFactory = $this->createMock(EavSetupFactory::class);
        $eavSetupFactory->expects(self::once())
            ->method('create')
            ->with(['setup' => $moduleDataSetup])
            ->willReturn($eavSetup);

        $patch = new AttachColorToDefaultAttributeSet($moduleDataSetup, $eavSetupFactory);

        $patch->apply();
    }
}
