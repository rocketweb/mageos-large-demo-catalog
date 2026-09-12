<?php
declare(strict_types=1);

namespace RocketWeb\LabCatalog\Plugin;

use Magento\ConfigurableProduct\Block\Product\View\Type\Configurable;
use Magento\ConfigurableProduct\Model\ResourceModel\Product\Type\Configurable\Attribute\Collection;

class ConfigurableFamilyLabel
{
    public function afterGetAllowAttributes(Configurable $subject, Collection $result): Collection
    {
        if (!$this->isOutdoorFamily($subject)) {
            return $result;
        }

        $items = $result->getItems();
        $displayAttributes = clone $result;
        $displayAttributes->removeAllItems();
        foreach ($items as $item) {
            $displayItem = clone $item;
            $attribute = $item->getProductAttribute();
            if ($attribute->getAttributeCode() === 'wands_piece_count') {
                $displayAttribute = clone $attribute;
                $displayAttribute->setStoreLabel($item->getLabel());
                $displayItem->setProductAttribute($displayAttribute);
                $displayItem->setOptions($this->sortOptions($item->getOptions(), 'store_label'));
            }
            $displayAttributes->addItem($displayItem);
        }

        return $displayAttributes;
    }

    public function afterGetJsonConfig(Configurable $subject, string $result): string
    {
        if (!$this->isOutdoorFamily($subject)) {
            return $result;
        }

        $config = json_decode($result, true, 512, JSON_THROW_ON_ERROR);
        foreach ($subject->getAllowAttributes() as $attribute) {
            $id = $attribute->getAttributeId();
            if (($config['attributes'][$id]['code'] ?? null) !== 'wands_piece_count') {
                continue;
            }
            $config['attributes'][$id]['label'] = $attribute->getLabel();
            $config['attributes'][$id]['options'] = $this->sortOptions($config['attributes'][$id]['options'], 'label');
        }

        return json_encode($config, JSON_HEX_TAG | JSON_HEX_APOS | JSON_HEX_AMP | JSON_HEX_QUOT | JSON_THROW_ON_ERROR);
    }

    private function isOutdoorFamily(Configurable $subject): bool
    {
        $product = $subject->getProduct();
        return $product->getSku() === 'WANDS-030335'
            && $product->getStore()->getWebsite()->getCode() === 'wands';
    }

    private function sortOptions(array $options, string $labelKey): array
    {
        usort($options, static fn(array $left, array $right): int => strnatcasecmp($left[$labelKey], $right[$labelKey]));
        return $options;
    }
}
