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
        $resource->expects(self::exactly(8))->method('saveAttribute')
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
        self::assertSame(['Furniture','Bed & Bath','Kitchen','Decor','Lighting','Rugs','Outdoor','Storage','Home Improvement','Kids','Pets','Room Bundles','QA Fixtures','Uncategorized'], array_map(fn($category) => $category->getName(), $categories));
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
        return $category;
    }

    private function curator(array $categories, CategoryResource $resource, TypeListInterface $cache): NavigationCurator
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
        $factory->expects(self::exactly(2))->method('create')->willReturnOnConsecutiveCalls($rootCollection, $children);
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
