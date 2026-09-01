<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Setup\Patch\Data;

use Magento\Catalog\Model\Product;
use Magento\Framework\Setup\Patch\DataPatchInterface;

class AttachColorToDefaultAttributeSet implements DataPatchInterface
{
    private const ATTRIBUTE_GROUP = 'WANDS Merchandising';

    public function __construct(
        private readonly \Magento\Framework\Setup\ModuleDataSetupInterface $moduleDataSetup,
        private readonly \Magento\Eav\Setup\EavSetupFactory $eavSetupFactory,
    ) {
    }

    public function apply(): void
    {
        $this->moduleDataSetup->getConnection()->startSetup();

        try {
            $eavSetup = $this->eavSetupFactory->create(['setup' => $this->moduleDataSetup]);
            $attributeSetId = (int)$eavSetup->getDefaultAttributeSetId(Product::ENTITY);

            if ($attributeSetId <= 0) {
                throw new \RuntimeException('The default product attribute set does not exist.');
            }

            $eavSetup->addAttributeToSet(
                Product::ENTITY,
                $attributeSetId,
                self::ATTRIBUTE_GROUP,
                'color'
            );
        } finally {
            $this->moduleDataSetup->getConnection()->endSetup();
        }
    }

    public static function getDependencies(): array
    {
        return [AddMerchandisingAttributes::class];
    }

    public function getAliases(): array
    {
        return [];
    }
}
