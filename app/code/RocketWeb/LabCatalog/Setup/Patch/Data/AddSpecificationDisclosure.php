<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Setup\Patch\Data;

use Magento\Catalog\Model\Product;
use Magento\Eav\Model\Entity\Attribute\ScopedAttributeInterface;
use Magento\Framework\Setup\Patch\DataPatchInterface;
use RuntimeException;

class AddSpecificationDisclosure implements DataPatchInterface
{
    public function __construct(
        private readonly \Magento\Framework\Setup\ModuleDataSetupInterface $moduleDataSetup,
        private readonly \Magento\Eav\Setup\EavSetupFactory $eavSetupFactory,
    ) {
    }

    public function apply(): self
    {
        $setup = $this->eavSetupFactory->create(['setup' => $this->moduleDataSetup]);
        $existing = $setup->getAttribute(Product::ENTITY, 'lab_spec_disclosure');
        if ($existing && !empty($existing['attribute_id'])) {
            if ($existing['backend_type'] !== 'text' || $existing['frontend_input'] !== 'textarea') {
                throw new RuntimeException('Existing specification disclosure has incompatible storage');
            }
            return $this;
        }
        $connection = $this->moduleDataSetup->getConnection();
        $connection->startSetup();
        try {
            $setup->addAttribute(Product::ENTITY, 'lab_spec_disclosure', [
                'type' => 'text',
                'input' => 'textarea',
                'label' => 'Test-data specification notice',
                'required' => false,
                'user_defined' => true,
                'global' => ScopedAttributeInterface::SCOPE_GLOBAL,
                'visible' => true,
                'visible_on_front' => true,
                'comparable' => true,
                'searchable' => false,
                'filterable' => false,
                'used_in_product_listing' => true,
                'group' => 'WANDS Specifications',
                'sort_order' => 0,
            ]);
        } finally {
            $connection->endSetup();
        }
        return $this;
    }

    public static function getDependencies(): array
    {
        return [AddDepthAttributes::class];
    }

    public function getAliases(): array
    {
        return [];
    }
}
