<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Model\Catalog;

use Magento\Catalog\Model\Category;
use Magento\Framework\App\Cache\Type\Config as ConfigCache;
use Magento\Framework\App\Cache\TypeListInterface;
use Magento\PageCache\Model\Cache\Type as PageCache;
use Magento\Store\Model\Group;
use Magento\Store\Model\Store;
use Magento\Store\Model\Website;

class StoreProvisioner
{
    public const WEBSITE_CODE = 'wands';
    public const STORE_GROUP_CODE = 'wands_catalog';
    public const STORE_GROUP_NAME = 'WANDS Catalog Store';
    public const STORE_CODE = 'wands';
    public const ROOT_CATEGORY_NAME = 'WANDS Catalog';
    public const THEME_PATH = 'frontend/Hyva/default';

    public function __construct(
        private readonly \Magento\Catalog\Model\CategoryFactory $categoryFactory,
        private readonly \Magento\Catalog\Model\ResourceModel\Category $categoryResource,
        private readonly \Magento\Catalog\Model\ResourceModel\Category\CollectionFactory $categoryCollectionFactory,
        private readonly \Magento\Store\Model\WebsiteFactory $websiteFactory,
        private readonly \Magento\Store\Model\ResourceModel\Website $websiteResource,
        private readonly \Magento\Store\Model\GroupFactory $groupFactory,
        private readonly \Magento\Store\Model\ResourceModel\Group $groupResource,
        private readonly \Magento\Store\Model\StoreFactory $storeFactory,
        private readonly \Magento\Store\Model\ResourceModel\Store $storeResource,
        private readonly \Magento\Theme\Model\ResourceModel\Theme\CollectionFactory $themeCollectionFactory,
        private readonly \Magento\Config\Model\ResourceModel\Config $configResource,
        private readonly \Magento\Framework\App\ResourceConnection $resourceConnection,
        private readonly \Magento\Store\Model\StoreManagerInterface $storeManager,
        private readonly TypeListInterface $cacheTypeList,
    ) {
    }

    public function provision(string $baseUrl): array
    {
        $baseUrl = rtrim($baseUrl, '/') . '/';
        $connection = $this->resourceConnection->getConnection();
        $connection->beginTransaction();

        try {
            $rootCategory = $this->getOrCreateRootCategory();
            $website = $this->getOrCreateWebsite();
            $group = $this->getOrCreateGroup($website, $rootCategory);
            $store = $this->getOrCreateStore($website, $group);
            $this->completeHierarchy($website, $group, $store);
            $themeId = $this->getHyvaThemeId();
            $this->saveCatalogConfiguration();
            $this->saveWebsiteConfiguration((int)$website->getId());
            $this->saveStoreConfiguration((int)$store->getId(), $baseUrl, $themeId);
            $connection->commit();
        } catch (\Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }

        $this->storeManager->reinitStores();
        $this->cacheTypeList->cleanType(ConfigCache::TYPE_IDENTIFIER);
        $this->cacheTypeList->cleanType(PageCache::TYPE_IDENTIFIER);

        return [
            'website_id' => (int)$website->getId(),
            'group_id' => (int)$group->getId(),
            'store_id' => (int)$store->getId(),
            'root_category_id' => (int)$rootCategory->getId(),
            'theme_id' => $themeId,
            'base_url' => $baseUrl,
        ];
    }

    private function getOrCreateRootCategory(): Category
    {
        $collection = $this->categoryCollectionFactory->create();
        $collection->addAttributeToSelect(['name', 'url_key']);
        $collection->addAttributeToFilter('url_key', 'wands-catalog');
        $collection->addFieldToFilter('parent_id', 1);
        $collection->setPageSize(1);
        $category = $collection->getFirstItem();

        if ($category->getId()) {
            return $category;
        }

        $category = $this->categoryFactory->create();
        $category->setName(self::ROOT_CATEGORY_NAME);
        $category->setUrlKey('wands-catalog');
        $category->setIsActive(1);
        $category->setIncludeInMenu(1);
        $category->setParentId(1);
        $category->setPath('1');
        $this->categoryResource->save($category);

        return $category;
    }

    private function getOrCreateWebsite(): Website
    {
        $website = $this->websiteFactory->create();
        $this->websiteResource->load($website, self::WEBSITE_CODE, 'code');

        if ($website->getId()) {
            return $website;
        }

        $website->setCode(self::WEBSITE_CODE);
        $website->setName('WANDS Relevance Lab');
        $website->setSortOrder(20);
        $website->setDefaultGroupId(0);
        $website->setIsDefault(0);
        $this->websiteResource->save($website);

        return $website;
    }

    private function getOrCreateGroup(Website $website, Category $rootCategory): Group
    {
        $group = $this->groupFactory->create();
        $collection = $group->getCollection();
        $collection->addFieldToFilter('website_id', (int)$website->getId());
        $collection->addFieldToFilter('name', self::STORE_GROUP_NAME);
        $collection->setPageSize(1);
        $existing = $collection->getFirstItem();

        if ($existing->getId()) {
            return $existing;
        }

        $group->setWebsiteId((int)$website->getId());
        $group->setCode(self::STORE_GROUP_CODE);
        $group->setName(self::STORE_GROUP_NAME);
        $group->setRootCategoryId((int)$rootCategory->getId());
        $group->setDefaultStoreId(0);
        $this->groupResource->save($group);

        return $group;
    }

    private function getOrCreateStore(Website $website, Group $group): Store
    {
        $store = $this->storeFactory->create();
        $this->storeResource->load($store, self::STORE_CODE, 'code');

        if ($store->getId()) {
            return $store;
        }

        $store->setCode(self::STORE_CODE);
        $store->setName('WANDS Store View');
        $store->setWebsiteId((int)$website->getId());
        $store->setGroupId((int)$group->getId());
        $store->setSortOrder(20);
        $store->setIsActive(1);
        $this->storeResource->save($store);

        return $store;
    }

    private function completeHierarchy(Website $website, Group $group, Store $store): void
    {
        if ((int)$website->getDefaultGroupId() !== (int)$group->getId()) {
            $website->setDefaultGroupId((int)$group->getId());
            $this->websiteResource->save($website);
        }

        if ((int)$group->getDefaultStoreId() !== (int)$store->getId()) {
            $group->setDefaultStoreId((int)$store->getId());
            $this->groupResource->save($group);
        }
    }

    private function getHyvaThemeId(): int
    {
        $theme = $this->themeCollectionFactory->create()->getThemeByFullPath(self::THEME_PATH);

        if (!$theme->getId()) {
            throw new \RuntimeException('The Hyva/default frontend theme is not registered.');
        }

        return (int)$theme->getId();
    }

    private function saveStoreConfiguration(int $storeId, string $baseUrl, int $themeId): void
    {
        $usesHttps = str_starts_with(strtolower($baseUrl), 'https://');
        $configuration = [
            'web/unsecure/base_url' => $baseUrl,
            'web/secure/base_url' => $baseUrl,
            'web/secure/use_in_frontend' => $usesHttps ? '1' : '0',
            'web/url/use_store' => '0',
            'design/theme/theme_id' => (string)$themeId,
            'design/head/default_title' => 'WANDS Product Relevance Lab',
            'general/store_information/name' => 'WANDS Product Relevance Lab',
        ];

        foreach ($configuration as $path => $value) {
            $this->configResource->saveConfig($path, $value, 'stores', $storeId);
        }
    }

    private function saveWebsiteConfiguration(int $websiteId): void
    {
        $configuration = [
            'currency/options/base' => 'USD',
            'currency/options/default' => 'USD',
            'currency/options/allow' => 'USD',
        ];

        foreach ($configuration as $path => $value) {
            $this->configResource->saveConfig($path, $value, 'websites', $websiteId);
        }
    }

    private function saveCatalogConfiguration(): void
    {
        $this->configResource->saveConfig('catalog/price/scope', '1', 'default', 0);
    }
}
