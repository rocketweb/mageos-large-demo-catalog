<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Model\Catalog;

use Magento\Catalog\Model\CategoryFactory;
use Magento\Framework\App\Cache\Type\Block;
use Magento\Framework\App\Cache\TypeListInterface;
use Magento\PageCache\Model\Cache\Type as PageCache;

class NavigationCurator
{
    public function __construct(
        private readonly \Magento\Catalog\Model\ResourceModel\Category\CollectionFactory $categoryCollectionFactory,
        private readonly \Magento\Catalog\Model\ResourceModel\Category $categoryResource,
        private readonly TypeListInterface $cacheTypeList,
        private readonly CategoryFactory $categoryFactory,
    ) {
    }

    public function execute(bool $dryRun = false): array
    {
        $roots = $this->categoryCollectionFactory->create();
        $roots->setStoreId(0);
        $root = $roots->addAttributeToFilter('url_key', 'wands-catalog')
            ->addFieldToFilter('parent_id', 1)->setPageSize(1)->getFirstItem();
        if (!$root->getId()) {
            throw new \RuntimeException('The WANDS root category does not exist.');
        }

        $collection = $this->categoryCollectionFactory->create();
        $collection->setStoreId(0);
        $collection->addAttributeToSelect(['name', 'include_in_menu']);
        $collection->addFieldToFilter('parent_id', (int)$root->getId());
        $categories = iterator_to_array($collection);
        $byName = [];
        foreach ($categories as $category) {
            $name = (string)$category->getName();
            $canonicalName = NavigationTaxonomy::RENAMES[$name] ?? $name;
            if (isset($byName[$canonicalName])) {
                throw new \RuntimeException('Conflicting WANDS departments for ' . $canonicalName . '.');
            }
            $byName[$canonicalName] = $category;
        }

        $createDecor = !isset($byName['Decor']) && (isset($byName['Lighting']) || isset($byName['Rugs']));
        $plan = [
            'root_category_id' => (int)$root->getId(), 'renames' => [], 'moves' => [], 'menu_changes' => [],
            'create_decor' => $createDecor, 'visible_departments' => $createDecor ? 1 : 0, 'hidden_departments' => 0,
        ];
        foreach ($categories as $category) {
            $name = (string)$category->getName();
            $canonicalName = NavigationTaxonomy::RENAMES[$name] ?? $name;
            if ($name !== $canonicalName) {
                $plan['renames'][] = ['category_id' => (int)$category->getId(), 'from' => $name, 'to' => $canonicalName];
            }
            $isChild = isset(NavigationTaxonomy::CHILD_DEPARTMENTS[$name]);
            $visible = $isChild || in_array($canonicalName, NavigationTaxonomy::DEPARTMENTS, true);
            if ($isChild) {
                $plan['moves'][] = ['category_id' => (int)$category->getId(), 'from' => $name, 'to' => 'Decor/' . $name];
            } elseif ($visible) {
                $plan['visible_departments']++;
            } else {
                $plan['hidden_departments']++;
            }
            if ((int)$category->getIncludeInMenu() !== (int)$visible) {
                $plan['menu_changes'][] = ['category_id' => (int)$category->getId(), 'include_in_menu' => (int)$visible];
            }
        }
        if ($dryRun) {
            return ['dry_run' => true] + $plan;
        }

        $changed = $createDecor || $plan['renames'] || $plan['moves'] || $plan['menu_changes'];
        if ($changed) {
            $connection = $this->categoryResource->getConnection();
            $connection->beginTransaction();
            try {
                if ($createDecor) {
                    $decor = $this->categoryFactory->create();
                    $decor->setStoreId(0)->setPath($root->getPath())->setParentId($root->getId())
                        ->setName('Decor')->setIsActive(true)->setIncludeInMenu(true)
                        ->setAttributeSetId($decor->getDefaultAttributeSetId());
                    $this->categoryResource->save($decor);
                    $byName['Decor'] = $decor;
                }
                foreach ($plan['renames'] as $rename) {
                    $category = $byName[$rename['to']];
                    $category->setStoreId(0)->setName($rename['to']);
                    $this->categoryResource->saveAttribute($category, 'name');
                }
                $afterId = null;
                foreach (NavigationTaxonomy::CHILD_DEPARTMENTS as $name => $parent) {
                    if (isset($byName[$name])) {
                        $byName[$name]->setStoreId(0)->move($byName[$parent]->getId(), $afterId);
                        $afterId = $byName[$name]->getId();
                    }
                }
                foreach ($categories as $category) {
                    $name = (string)$category->getName();
                    $visible = isset(NavigationTaxonomy::CHILD_DEPARTMENTS[$name])
                        || in_array($name, NavigationTaxonomy::DEPARTMENTS, true);
                    if ((int)$category->getIncludeInMenu() !== (int)$visible) {
                        $category->setStoreId(0)->setIncludeInMenu((int)$visible);
                        $this->categoryResource->saveAttribute($category, 'include_in_menu');
                    }
                }
                $connection->commit();
            } catch (\Throwable $exception) {
                $connection->rollBack();
                throw $exception;
            }
            $this->cacheTypeList->cleanType(Block::TYPE_IDENTIFIER);
            $this->cacheTypeList->cleanType(PageCache::TYPE_IDENTIFIER);
        }
        return [
            'visible_departments' => $plan['visible_departments'], 'hidden_departments' => $plan['hidden_departments'],
            'renamed_departments' => count($plan['renames']), 'moved_departments' => count($plan['moves']),
        ];
    }
}
