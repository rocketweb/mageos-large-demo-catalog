<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Setup\Patch\Data;

use Magento\Catalog\Model\Product;
use Magento\Eav\Model\Entity\Attribute\ScopedAttributeInterface;
use Magento\Framework\Setup\Patch\DataPatchInterface;
use RuntimeException;

class AddDepthAttributes implements DataPatchInterface
{
    /**
     * Keep runtime attribute definitions aligned with the offline pilot builder.
     */
    public function __construct(
        private readonly \Magento\Framework\Setup\ModuleDataSetupInterface $moduleDataSetup,
        private readonly \Magento\Eav\Setup\EavSetupFactory $eavSetupFactory,
        private readonly \Magento\Framework\Filesystem\Driver\File $fileDriver,
    ) {
    }

    /**
     * Add missing attributes without overwriting incompatible existing storage.
     *
     * @return self
     */
    public function apply(): self
    {
        $path = __DIR__ . '/../../../etc/depth_attributes.json';
        $schema = json_decode($this->fileDriver->fileGetContents($path), true, 512, JSON_THROW_ON_ERROR);
        $setup = $this->eavSetupFactory->create(['setup' => $this->moduleDataSetup]);
        $missing = [];
        foreach ($schema['attributes'] as $code => $definition) {
            if (!preg_match('/^lab_spec_[a-z_]+$/', $code)) {
                throw new RuntimeException('Unexpected depth attribute code: ' . $code);
            }
            $configuration = $this->configuration($definition);
            $existing = $setup->getAttribute(Product::ENTITY, $code);
            if ($existing && !empty($existing['attribute_id'])) {
                if ($existing['backend_type'] !== $configuration['type']
                    || $existing['frontend_input'] !== $configuration['input']) {
                    throw new RuntimeException('Existing depth attribute has incompatible storage: ' . $code);
                }
                continue;
            }
            $missing[$code] = $configuration;
        }
        $connection = $this->moduleDataSetup->getConnection();
        $connection->startSetup();
        try {
            foreach ($missing as $code => $configuration) {
                $setup->addAttribute(Product::ENTITY, $code, $configuration);
            }
        } finally {
            $connection->endSetup();
        }
        return $this;
    }

    /**
     * Build display attributes and controlled facets without adding search boosts.
     *
     * @param array $definition
     * @return array
     */
    private function configuration(array $definition): array
    {
        $kind = $definition['kind'];
        $type = match ($kind) {
            'length' => 'decimal',
            'select' => 'int',
            'text' => 'text',
            default => throw new RuntimeException('Unsupported depth attribute type'),
        };
        $input = match ($kind) {
            'select' => 'select',
            'text' => 'textarea',
            default => 'text',
        };
        $configuration = [
            'type' => $type,
            'label' => $definition['label'],
            'input' => $input,
            'required' => false,
            'user_defined' => true,
            'global' => ScopedAttributeInterface::SCOPE_GLOBAL,
            'visible' => true,
            'searchable' => false,
            'filterable' => $kind === 'select' ? 1 : false,
            'filterable_in_search' => $kind === 'select',
            'comparable' => true,
            'visible_on_front' => true,
            'used_in_product_listing' => true,
            'group' => 'WANDS Specifications',
        ];
        if ($kind === 'select') {
            $configuration['option'] = ['values' => $definition['options']];
        }
        return $configuration;
    }

    /**
     * @inheritdoc
     */
    public static function getDependencies(): array
    {
        return [AddRealismAttributes::class];
    }

    /**
     * @inheritdoc
     */
    public function getAliases(): array
    {
        return [];
    }
}
