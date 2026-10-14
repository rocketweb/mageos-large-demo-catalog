<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Test\Unit\Model\Import;

use Magento\Catalog\Model\Category;
use Magento\Catalog\Model\CategoryFactory;
use Magento\Catalog\Model\ResourceModel\Category\Collection;
use Magento\Catalog\Model\ResourceModel\Category\CollectionFactory;
use PHPUnit\Framework\TestCase;
use RocketWeb\LabCatalog\Model\Import\CategoryProcessor;

require_once dirname(__DIR__, 4) . '/Model/Catalog/NavigationTaxonomy.php';
require_once dirname(__DIR__, 4) . '/Model/Import/CategoryProcessor.php';

class CategoryProcessorTest extends TestCase
{
    public function testCanonicalPathsReuseTheExistingLegacyCategoryIds(): void
    {
        $processor = $this->processor();
        self::assertSame([3, 4, 7, 6], $processor->upsertCategories(
            'WANDS Catalog/Kitchen;WANDS Catalog/Decor;WANDS Catalog/Decor/Lighting/Lamps;WANDS Catalog/Decor/Rugs',
            ';'
        ));
        self::assertSame([], $processor->created);
    }

    public function testNewLeavesUseTheExistingLightingCategoryAsTheirParent(): void
    {
        $processor = $this->processor();
        self::assertSame([10], $processor->upsertCategories('WANDS Catalog/Decor/Lighting/New Lamps', ','));
        self::assertSame([['name' => 'New Lamps', 'parent_id' => 5]], $processor->created);
    }

    public function testConflictingOldAndCanonicalBranchesAreRejectedBeforeWriting(): void
    {
        $this->expectException(\RuntimeException::class);
        $this->expectExceptionMessage('Conflicting WANDS category paths');
        $this->processor(true);
    }

    private function processor(bool $conflict = false): RecordingCategoryProcessor
    {
        $rows = [
            [2, 'WANDS Catalog', '1/2'], [3, 'Kitchen & Tabletop', '1/2/3'],
            [4, 'Décor & Pillows', '1/2/4'], [5, 'Lighting', '1/2/5'],
            [6, 'Rugs', '1/2/6'], [7, 'Lamps', '1/2/5/7'],
        ];
        if ($conflict) {
            $rows[] = [8, 'Kitchen', '1/2/8'];
        }
        $categories = [];
        foreach ($rows as [$id, $name, $path]) {
            $category = $this->createStub(Category::class);
            $category->method('getId')->willReturn($id);
            $category->method('getName')->willReturn($name);
            $category->method('getPath')->willReturn($path);
            $categories[$id] = $category;
        }
        $collection = $this->createStub(Collection::class);
        $collection->method('addAttributeToSelect')->willReturnSelf();
        $collection->method('getIterator')->willReturn(new \ArrayIterator($categories));
        $collection->method('getItemById')->willReturnCallback(static fn($id) => $categories[$id]);
        $factory = $this->createStub(CollectionFactory::class);
        $factory->method('create')->willReturn($collection);
        return new RecordingCategoryProcessor($factory, $this->createStub(CategoryFactory::class));
    }
}

class RecordingCategoryProcessor extends CategoryProcessor
{
    public array $created = [];

    protected function createCategory($name, $parentId)
    {
        $this->created[] = ['name' => $name, 'parent_id' => $parentId];
        return 10;
    }
}
