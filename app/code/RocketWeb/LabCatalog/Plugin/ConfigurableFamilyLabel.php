<?php
declare(strict_types=1);

namespace RocketWeb\LabCatalog\Plugin;

use Magento\ConfigurableProduct\Block\Product\View\Type\Configurable;
use Magento\ConfigurableProduct\Model\ResourceModel\Product\Type\Configurable\Attribute\Collection;

class ConfigurableFamilyLabel
{
    public function afterGetAllowAttributes(Configurable $subject, Collection $result): Collection
    {
        $product = $subject->getProduct();
        if ($product->getSku() !== 'WANDS-030335'
            || $product->getStore()->getWebsite()->getCode() !== 'wands'
        ) {
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
            }
            $displayAttributes->addItem($displayItem);
        }

        return $displayAttributes;
    }
}
