<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Model\Catalog;

class NavigationCurator
{
    private const VISIBLE_DEPARTMENTS = [
        'Furniture',
        'Bed & Bath',
        'Kitchen & Tabletop',
        'Décor & Pillows',
        'Lighting',
        'Rugs',
        'Outdoor',
        'Storage & Organization',
        'Home Improvement',
        'Baby & Kids',
    ];

    public function __construct(
        private readonly \Magento\Catalog\Model\ResourceModel\Category\CollectionFactory $categoryCollectionFactory,
        private readonly \Magento\Catalog\Model\ResourceModel\Category $categoryResource,
    ) {
    }

    public function execute(): array
    {
        $rootCategories = $this->categoryCollectionFactory->create();
        $rootCategories->setStoreId(0);
        $rootCategory = $rootCategories->addAttributeToFilter('url_key', 'wands-catalog')
            ->addFieldToFilter('parent_id', 1)
            ->setPageSize(1)
            ->getFirstItem();

        if (!$rootCategory->getId()) {
            throw new \RuntimeException('The WANDS root category does not exist.');
        }

        $categories = $this->categoryCollectionFactory->create();
        $categories->setStoreId(0);
        $categories->addAttributeToSelect(['name', 'include_in_menu']);
        $categories->addFieldToFilter('parent_id', (int)$rootCategory->getId());
        $visible = 0;
        $hidden = 0;

        foreach ($categories as $category) {
            $includeInMenu = in_array((string)$category->getName(), self::VISIBLE_DEPARTMENTS, true);
            $category->setStoreId(0);
            $category->setIncludeInMenu($includeInMenu ? 1 : 0);
            $this->categoryResource->saveAttribute($category, 'include_in_menu');
            if ($includeInMenu) {
                $visible++;
            } else {
                $hidden++;
            }
        }

        return ['visible_departments' => $visible, 'hidden_departments' => $hidden];
    }
}
