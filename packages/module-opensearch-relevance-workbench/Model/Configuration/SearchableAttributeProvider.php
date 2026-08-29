<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Configuration;

use Magento\Catalog\Model\ResourceModel\Product\Attribute\Collection;

class SearchableAttributeProvider
{
    public function __construct(private readonly Collection $attributeCollection)
    {
    }

    /**
     * @return list<string>
     */
    public function getAttributeCodes(): array
    {
        $this->attributeCollection->addIsSearchableFilter();
        $attributeCodes = [];

        foreach ($this->attributeCollection->getItems() as $attribute) {
            $attributeCode = $attribute->getData('attribute_code');

            if (is_string($attributeCode) && $attributeCode !== '') {
                $attributeCodes[] = $attributeCode;
            }
        }

        $attributeCodes[] = 'name';
        $attributeCodes[] = 'sku';
        $attributeCodes = array_values(array_unique($attributeCodes, SORT_STRING));
        sort($attributeCodes, SORT_STRING);

        return $attributeCodes;
    }
}
