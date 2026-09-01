<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Setup\Patch\Data;

use Magento\Catalog\Model\Product;
use Magento\Eav\Model\Entity\Attribute\ScopedAttributeInterface;
use Magento\Eav\Setup\EavSetup;
use Magento\Framework\Setup\Patch\DataPatchInterface;

class AddMerchandisingAttributes implements DataPatchInterface
{
    private const ATTRIBUTE_GROUP = 'WANDS Merchandising';

    private const ATTRIBUTE_OPTIONS = [
        'color' => [
            'Beige',
            'Black',
            'Blue',
            'Brown',
            'Cream',
            'Gray',
            'Green',
            'Ivory',
            'Navy',
            'Natural',
            'Red',
            'Terracotta',
            'White',
        ],
        'wands_size' => [
            'Small',
            'Medium',
            'Large',
            'Extra Large',
            'Twin',
            'Full',
            'Queen',
            'King',
            '2 ft x 3 ft',
            '5 ft x 7 ft',
            '8 ft x 10 ft',
            '9 ft x 12 ft',
            '16 in x 16 in',
            '18 in x 18 in',
            '20 in x 20 in',
            '22 in x 22 in',
            '12 in x 12 in',
            '24 in x 24 in',
            '18 in x 30 in',
            '24 in x 36 in',
            '30 in x 48 in',
            '36 in x 60 in',
            'Toddler',
            '6 in x 6 in',
            'Twin over Twin',
            'Twin over Full',
            'Full over Full',
            'Twin XL over Queen',
        ],
        'wands_finish' => [
            'Natural',
            'Walnut',
            'Oak',
            'Espresso',
            'Black',
            'White',
            'Brass',
            'Chrome',
            'Brushed Nickel',
            'Matte Black',
            'Bronze',
            'Cream',
        ],
        'wands_material' => [
            'Cotton',
            'Engineered Wood',
            'Faux Leather',
            'Leather',
            'Linen Blend',
            'Metal',
            'Polyester',
            'Solid Wood',
            'Velvet',
            'Wool',
        ],
        'wands_length' => [
            '24 in',
            '30 in',
            '36 in',
            '42 in',
            '48 in',
            '60 in',
            '63 in',
            '72 in',
            '84 in',
            '95 in',
            '108 in',
        ],
        'wands_seat_height' => ['18 in', '24 in', '26 in', '30 in', '32 in'],
        'wands_seating_capacity' => ['Seats 2', 'Seats 4', 'Seats 6', 'Seats 8'],
        'wands_piece_count' => ['2 Pieces', '3 Pieces', '4 Pieces', '5 Pieces', '7 Pieces'],
        'wands_pack_size' => ['Pack of 4', 'Pack of 6', 'Pack of 8', 'Pack of 10', 'Pack of 12'],
        'wands_light_count' => ['1 Light', '3 Lights', '4 Lights', '6 Lights', '8 Lights'],
    ];

    private const ATTRIBUTE_LABELS = [
        'wands_size' => 'Size',
        'wands_finish' => 'Finish',
        'wands_material' => 'Material',
        'wands_length' => 'Length / Width',
        'wands_seat_height' => 'Seat Height',
        'wands_seating_capacity' => 'Seating Capacity',
        'wands_piece_count' => 'Piece Count',
        'wands_pack_size' => 'Pack Size',
        'wands_light_count' => 'Light Count',
    ];

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
            $this->assertReusableColorAttribute($eavSetup);

            foreach (self::ATTRIBUTE_LABELS as $code => $label) {
                if ($eavSetup->getAttributeId(Product::ENTITY, $code) === false) {
                    $eavSetup->addAttribute(Product::ENTITY, $code, $this->selectAttribute($label));
                }
            }

            foreach (self::ATTRIBUTE_OPTIONS as $code => $labels) {
                $this->addMissingOptions($eavSetup, $code, $labels);
            }
        } finally {
            $this->moduleDataSetup->getConnection()->endSetup();
        }
    }

    private function assertReusableColorAttribute(EavSetup $eavSetup): void
    {
        $attribute = $eavSetup->getAttribute(Product::ENTITY, 'color');

        if (!is_array($attribute)
            || ($attribute['frontend_input'] ?? null) !== 'select'
            || (int)($attribute['is_global'] ?? 0) !== ScopedAttributeInterface::SCOPE_GLOBAL
        ) {
            throw new \RuntimeException('The core color attribute must exist as a global select attribute.');
        }
    }

    private function selectAttribute(string $label): array
    {
        return [
            'type' => 'int',
            'label' => $label,
            'input' => 'select',
            'required' => false,
            'user_defined' => true,
            'global' => ScopedAttributeInterface::SCOPE_GLOBAL,
            'visible' => true,
            'searchable' => true,
            'filterable' => true,
            'filterable_in_search' => true,
            'comparable' => true,
            'visible_on_front' => true,
            'used_in_product_listing' => true,
            'group' => self::ATTRIBUTE_GROUP,
        ];
    }

    private function addMissingOptions(EavSetup $eavSetup, string $code, array $labels): void
    {
        $attributeId = $eavSetup->getAttributeId(Product::ENTITY, $code);

        if ($attributeId === false) {
            throw new \RuntimeException(sprintf('Product attribute %s was not created.', $code));
        }

        $connection = $this->moduleDataSetup->getConnection();
        $select = $connection->select()
            ->from(['option' => $this->moduleDataSetup->getTable('eav_attribute_option')], [])
            ->join(
                ['value' => $this->moduleDataSetup->getTable('eav_attribute_option_value')],
                'value.option_id = option.option_id',
                ['value']
            )
            ->where('option.attribute_id = ?', (int)$attributeId)
            ->where('value.store_id = 0');
        $existing = array_map('strtolower', $connection->fetchCol($select));
        $missing = array_filter(
            $labels,
            static fn(string $label): bool => !in_array(strtolower($label), $existing, true)
        );
        $missing = array_values($missing);

        if ($missing === []) {
            return;
        }

        $values = [];
        foreach ($missing as $position => $label) {
            $values[1000 + $position] = $label;
        }
        $eavSetup->addAttributeOption([
            'attribute_id' => (int)$attributeId,
            'values' => $values,
        ]);
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
