<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Setup\Patch\Data;

use Magento\Catalog\Model\Product;
use Magento\Eav\Model\Entity\Attribute\ScopedAttributeInterface;
use Magento\Eav\Model\Entity\Attribute\Source\Boolean;
use Magento\Eav\Setup\EavSetup;
use Magento\Framework\Setup\Patch\DataPatchInterface;

class AddProductAttributes implements DataPatchInterface
{
    private const ATTRIBUTE_GROUP = 'WANDS Lab';

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
            $this->addAttributes($eavSetup);
        } finally {
            $this->moduleDataSetup->getConnection()->endSetup();
        }
    }

    private function addAttributes(EavSetup $eavSetup): void
    {
        $attributes = [
            'wands_product_id' => $this->textAttribute('WANDS Product ID', true),
            'wands_product_class' => $this->textAttribute('WANDS Product Class', true),
            'wands_average_rating' => $this->numericAttribute('WANDS Average Rating', 'decimal'),
            'wands_review_count' => $this->numericAttribute('WANDS Review Count', 'int'),
            'lab_price_method' => $this->textAttribute('Lab Price Method'),
            'lab_price_version' => $this->textAttribute('Lab Price Version'),
            'lab_price_synthetic' => [
                'type' => 'int',
                'label' => 'Synthetic Lab Price',
                'input' => 'boolean',
                'source' => Boolean::class,
                'required' => false,
                'user_defined' => true,
                'global' => ScopedAttributeInterface::SCOPE_GLOBAL,
                'visible' => true,
                'default' => 1,
                'group' => self::ATTRIBUTE_GROUP,
            ],
        ];

        foreach ($attributes as $code => $configuration) {
            $eavSetup->addAttribute(Product::ENTITY, $code, $configuration);
        }
    }

    private function textAttribute(string $label, bool $searchable = false): array
    {
        return [
            'type' => 'varchar',
            'label' => $label,
            'input' => 'text',
            'required' => false,
            'user_defined' => true,
            'global' => ScopedAttributeInterface::SCOPE_GLOBAL,
            'visible' => true,
            'searchable' => $searchable,
            'filterable' => false,
            'comparable' => false,
            'visible_on_front' => false,
            'used_in_product_listing' => false,
            'group' => self::ATTRIBUTE_GROUP,
        ];
    }

    private function numericAttribute(string $label, string $type): array
    {
        return [
            'type' => $type,
            'label' => $label,
            'input' => 'text',
            'required' => false,
            'user_defined' => true,
            'global' => ScopedAttributeInterface::SCOPE_GLOBAL,
            'visible' => true,
            'searchable' => false,
            'filterable' => false,
            'comparable' => false,
            'visible_on_front' => false,
            'used_in_product_listing' => false,
            'group' => self::ATTRIBUTE_GROUP,
        ];
    }

    public static function getDependencies(): array
    {
        return [];
    }

    public function getAliases(): array
    {
        return [];
    }
}
