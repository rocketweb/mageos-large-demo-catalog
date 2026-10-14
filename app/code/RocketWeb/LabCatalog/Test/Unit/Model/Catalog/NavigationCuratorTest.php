<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Test\Unit\Model\Catalog;

use Magento\Catalog\Model\Category;
use Magento\Catalog\Model\ResourceModel\Category as CategoryResource;
use Magento\Catalog\Model\ResourceModel\Category\Collection;
use Magento\Catalog\Model\ResourceModel\Category\CollectionFactory;
use Magento\Framework\App\Cache\TypeListInterface;
use PHPUnit\Framework\TestCase;
use RocketWeb\LabCatalog\Model\Catalog\NavigationCurator;

require_once dirname(__DIR__, 4) . '/Model/Catalog/NavigationTaxonomy.php';

require_once dirname(__DIR__, 4) . '/Model/Catalog/NavigationCurator.php';

class NavigationCuratorTest extends TestCase
{
    public function testApprovedDepartmentOrderAndDiyUrlArePlannedWithoutWriting(): void
    {
        $names = ['Kitchen', 'Home Improvement', 'Decor', 'Furniture', 'Outdoor', 'Storage', 'Bed & Bath', 'Kids', 'Pets'];
        $categories = array_map(fn($name) => $this->category($name, 1), $names);
        foreach ($categories as $index => $category) {
            $category->setPosition($index + 20)->setUrlKey(strtolower(str_replace(' ', '-', $category->getName())));
        }
        $resource = $this->createMock(CategoryResource::class);
        $resource->expects(self::never())->method('save');
        $resource->expects(self::never())->method('saveAttribute');
        $resource->expects(self::never())->method('getConnection');
        $cache = $this->createMock(TypeListInterface::class);
        $cache->expects(self::never())->method('cleanType');
        $before = array_map(fn($category) => $category->getData(), $categories);
        $plan = $this->curator($categories, $resource, $cache)->execute(true);
        self::assertSame(['DIY', 'Furniture', 'Decor', 'Bed & Bath', 'Kitchen', 'Outdoor', 'Storage', 'Kids', 'Pets'], $plan['department_order']);
        self::assertCount(9, $plan['position_changes']);
        self::assertSame([1, 2, 3, 4, 5, 6, 7, 8, 9], array_column($plan['position_changes'], 'to'));
        self::assertSame('DIY', $plan['renames'][0]['to']);
        self::assertSame('diy', $plan['url_changes'][0]['to']);
        self::assertSame($before, array_map(fn($category) => $category->getData(), $categories));
    }

    public function testApprovedOrderAndDiyUrlAreAppliedOnce(): void
    {
        $names = ['Kitchen', 'Home Improvement', 'Decor', 'Furniture', 'Outdoor', 'Storage', 'Bed & Bath', 'Kids', 'Pets'];
        $categories = array_map(fn($name) => $this->category($name, 1), $names);
        foreach ($categories as $index => $category) {
            $category->setPosition($index + 20);
        }
        $resource = $this->createMock(CategoryResource::class);
        $resource->expects(self::once())->method('saveAttribute')->with($categories[1], 'name');
        $resource->expects(self::exactly(10))->method('save')->willReturnSelf();
        $cache = $this->createMock(TypeListInterface::class);
        $cache->expects(self::exactly(2))->method('cleanType');
        $result = $this->curator($categories, $resource, $cache)->execute();
        self::assertSame(9, $result['reordered_departments']);
        self::assertSame(1, $result['changed_department_urls']);
        self::assertSame('DIY', $categories[1]->getName());
        self::assertSame('diy', $categories[1]->getUrlKey());
        self::assertFalse($categories[1]->getData('save_rewrites_history'));
        usort($categories, fn($left, $right) => $left->getPosition() <=> $right->getPosition());
        self::assertSame(['DIY', 'Furniture', 'Decor', 'Bed & Bath', 'Kitchen', 'Outdoor', 'Storage', 'Kids', 'Pets'], array_map(fn($category) => $category->getName(), $categories));
        $resource = $this->createMock(CategoryResource::class);
        $resource->expects(self::never())->method('save');
        $resource->expects(self::never())->method('saveAttribute');
        $cache = $this->createMock(TypeListInterface::class);
        $cache->expects(self::never())->method('cleanType');
        $again = $this->curator($categories, $resource, $cache)->execute();
        self::assertSame(0, $again['renamed_departments']);
        self::assertSame(0, $again['reordered_departments']);
        self::assertSame(0, $again['changed_department_urls']);
    }

    public function testDiyMigrationUpdatesPersistedDescendantPathsWithoutChangingOtherBranches(): void
    {
        $department = $this->category('Home Improvement', 1)->setUrlPath('home-improvement');
        $child = $this->category('Hardware', 1)->setUrlPath('home-improvement/hardware');
        $other = $this->category('Outdoor', 1)->setUrlPath('outdoor/tools');
        $resource = $this->createMock(CategoryResource::class);
        $resource->expects(self::once())->method('save')->willReturnCallback(static function ($category) use ($resource) {
            $category->setUrlPath('diy');
            return $resource;
        });
        $saved = [];
        $resource->expects(self::exactly(2))->method('saveAttribute')->willReturnCallback(static function ($category, $attribute) use (&$saved, $resource) {
            $saved[] = [$category->getId(), $attribute];
            return $resource;
        });
        $cache = $this->createMock(TypeListInterface::class);
        $cache->expects(self::exactly(2))->method('cleanType');
        $this->curator([$department], $resource, $cache, [$child, $other])->execute();
        self::assertSame('diy/hardware', $child->getUrlPath());
        self::assertSame('outdoor/tools', $other->getUrlPath());
        self::assertSame([[$department->getId(), 'name'], [$child->getId(), 'url_path']], $saved);
    }

    public function testNineDepartmentsAreRenamedAndLightingAndRugsAreMovedWithoutLosingIds(): void
    {
        $names = [
            'Furniture', 'Bed & Bath', 'Kitchen & Tabletop', 'Décor & Pillows', 'Lighting',
            'Rugs', 'Outdoor', 'Storage & Organization', 'Home Improvement', 'Baby & Kids', 'Pet',
            'Room Bundles', 'QA Fixtures', 'Uncategorized',
        ];
        $categories = array_map(fn($name) => $this->category($name, 1), $names);
        $resource = $this->createMock(CategoryResource::class);
        $saved = [];
        $resource->expects(self::exactly(9))->method('saveAttribute')
            ->willReturnCallback(static function ($category, $attribute) use (&$saved, $resource) {
                $saved[] = [$attribute, $category->getName()];
                return $resource;
            });
        $cache = $this->createMock(TypeListInterface::class);
        $cleaned = [];
        $cache->expects(self::exactly(2))->method('cleanType')
            ->willReturnCallback(static function ($type) use (&$cleaned) { $cleaned[] = $type; });

        $result = $this->curator($categories, $resource, $cache)->execute();

        self::assertSame(9, $result['visible_departments']);
        self::assertSame(3, $result['hidden_departments']);
        self::assertSame(['Furniture','Bed & Bath','Kitchen','Decor','Lighting','Rugs','Outdoor','Storage','DIY','Kids','Pets','Room Bundles','QA Fixtures','Uncategorized'], array_map(fn($category) => $category->getName(), $categories));
        $decorId = $categories[3]->getId();
        self::assertSame($decorId, $categories[4]->getParentId());
        self::assertSame($decorId, $categories[5]->getParentId());
        self::assertSame(['Room Bundles', 'QA Fixtures', 'Uncategorized'], array_column(array_filter($saved, fn($entry) => $entry[0] === 'include_in_menu'), 1));
        self::assertSame(['block_html', 'full_page'], $cleaned);
    }

    public function testAlreadyCuratedMenuDoesNotWriteOrInvalidateCaches(): void
    {
        $categories = [$this->category('Furniture', 1), $this->category('QA Fixtures', 0)];
        $resource = $this->createMock(CategoryResource::class);
        $resource->expects(self::never())->method('saveAttribute');
        $cache = $this->createMock(TypeListInterface::class);
        $cache->expects(self::never())->method('cleanType');

        $result = $this->curator($categories, $resource, $cache)->execute();
        self::assertSame(1, $result['visible_departments']);
        self::assertSame(1, $result['hidden_departments']);
    }

    public function testDryRunListsTheRenameAndMoveWithoutWriting(): void
    {
        $categories = [$this->category('Décor & Pillows', 1), $this->category('Lighting', 1), $this->category('QA Fixtures', 1)];
        $before = array_map(fn($category) => $category->getData(), $categories);
        $resource = $this->createMock(CategoryResource::class);
        $resource->expects(self::never())->method('saveAttribute');
        $resource->expects(self::never())->method('getConnection');
        $cache = $this->createMock(TypeListInterface::class);
        $cache->expects(self::never())->method('cleanType');
        $plan = $this->curator($categories, $resource, $cache)->execute(true);
        self::assertTrue($plan['dry_run']);
        self::assertCount(1, $plan['renames']);
        self::assertCount(1, $plan['moves']);
        self::assertCount(1, $plan['menu_changes']);
        self::assertSame($before, array_map(fn($category) => $category->getData(), $categories));
    }

    private function category(string $name, int $visible): Category
    {
        $category = new NavigationCategory();
        static $id = 100;
        $category->setData(['entity_id' => $id++, 'parent_id' => 53, 'path' => '1/53/' . ($id - 1), 'name' => $name, 'include_in_menu' => $visible]);
        $canonicalName = \RocketWeb\LabCatalog\Model\Catalog\NavigationTaxonomy::RENAMES[$name] ?? $name;
        $order = ['DIY', 'Furniture', 'Decor', 'Bed & Bath', 'Kitchen', 'Outdoor', 'Storage', 'Kids', 'Pets'];
        $position = array_search($canonicalName, $order, true);
        $category->setPosition($position === false ? 50 : $position + 1)->setUrlKey(strtolower(str_replace(' ', '-', $name)));
        return $category;
    }

    private function curator(array $categories, CategoryResource $resource, TypeListInterface $cache, array $descendants = []): NavigationCurator
    {
        $root = $this->createStub(Category::class);
        $root->method('getId')->willReturn(53);
        $root->method('getPath')->willReturn('1/53');
        $rootCollection = $this->createStub(Collection::class);
        foreach (['addAttributeToFilter', 'addFieldToFilter', 'setPageSize'] as $method) {
            $rootCollection->method($method)->willReturnSelf();
        }
        $rootCollection->method('getFirstItem')->willReturn($root);
        $children = $this->createMock(Collection::class);
        $children->expects(self::once())->method('addFieldToFilter')->with('parent_id', 53)->willReturnSelf();
        $children->method('getIterator')->willReturn(new \ArrayIterator($categories));
        $factory = $this->createMock(CollectionFactory::class);
        $needsDescendants = count(array_filter($categories, static fn($category) => $category->getName() === 'Home Improvement' && $category->getUrlPath()));
        $descendantCollection = $this->createStub(Collection::class);
        $descendantCollection->method('addAttributeToSelect')->willReturnSelf();
        $descendantCollection->method('addFieldToFilter')->willReturnSelf();
        $descendantCollection->method('getIterator')->willReturn(new \ArrayIterator($descendants));
        $factory->expects(self::exactly(2 + $needsDescendants))->method('create')->willReturnOnConsecutiveCalls($rootCollection, $children, $descendantCollection);
        $resource->method('getConnection')->willReturn($this->createStub(\Magento\Framework\DB\Adapter\AdapterInterface::class));
        return new NavigationCurator($factory, $resource, $cache, $this->createStub(\Magento\Catalog\Model\CategoryFactory::class));
    }
}

class NavigationCategory extends Category
{
    public function __construct()
    {
        $this->_idFieldName = 'entity_id';
    }

    public function move($parentId, $afterCategoryId)
    {
        return $this->setData('parent_id', $parentId);
    }

    public function setStoreId($storeId)
    {
        return $this->setData('store_id', $storeId);
    }
}
