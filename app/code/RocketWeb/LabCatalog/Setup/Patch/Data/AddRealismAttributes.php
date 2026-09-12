<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Setup\Patch\Data;

use Magento\Catalog\Model\Product;
use Magento\Eav\Model\Entity\Attribute\ScopedAttributeInterface;
use Magento\Framework\Setup\Patch\DataPatchInterface;

class AddRealismAttributes implements DataPatchInterface
{
    public function __construct(
        private readonly \Magento\Framework\Setup\ModuleDataSetupInterface $moduleDataSetup,
        private readonly \Magento\Eav\Setup\EavSetupFactory $eavSetupFactory,
    ) {
    }

    public function apply(): void
    {
        $this->moduleDataSetup->getConnection()->startSetup();
        try {
            $setup = $this->eavSetupFactory->create(['setup' => $this->moduleDataSetup]);
            $attributes = [
                'lab_brand' => 'Lab Collection',
                'lab_stock_scenario' => 'Synthetic Stock Scenario',
                'lab_sale_unit' => 'Lab Sale Unit',
            ];
            foreach ($attributes as $code => $label) {
                if ($setup->getAttributeId(Product::ENTITY, $code)) {
                    continue;
                }
                $setup->addAttribute(Product::ENTITY, $code, [
                    'type' => 'varchar',
                    'label' => $label,
                    'input' => 'text',
                    'required' => false,
                    'user_defined' => true,
                    'global' => ScopedAttributeInterface::SCOPE_GLOBAL,
                    'visible' => true,
                    'searchable' => $code === 'lab_brand',
                    'filterable' => false,
                    'comparable' => false,
                    'visible_on_front' => $code === 'lab_brand',
                    'used_in_product_listing' => $code === 'lab_brand',
                    'group' => 'WANDS Lab',
                ]);
            }
        } finally {
            $this->moduleDataSetup->getConnection()->endSetup();
        }
    }

    public static function getDependencies(): array
    {
        return [AddProductAttributes::class];
    }

    public function getAliases(): array
    {
        return [];
    }
}
