<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Test\Unit\Plugin;

use Magento\CatalogImportExport\Model\Import\Product\CategoryProcessor;
use PHPUnit\Framework\TestCase;
use RocketWeb\LabCatalog\Plugin\PreserveCategoryCommas;

require_once dirname(__DIR__, 3) . '/Model/Catalog/NavigationTaxonomy.php';

require_once dirname(__DIR__, 3) . '/Plugin/PreserveCategoryCommas.php';

class PreserveCategoryCommasTest extends TestCase
{
    public function testNativeProcessorKeepsCommasInCategoryNamesAndCreatesNoStrayRoots(): void
    {
        $processor = new RecordingCategoryProcessor();
        $plugin = new PreserveCategoryCommas();
        $arguments = $plugin->beforeUpsertCategories(
            $processor,
            'WANDS Catalog/Kitchen & Tabletop/Vases, Urns, Jars & Bottles',
            ','
        );

        $ids = $processor->upsertCategories(...$arguments);

        self::assertCount(1, $ids);
        self::assertSame([
            ['name' => 'Kitchen', 'parent_id' => 2],
            ['name' => 'Vases, Urns, Jars & Bottles', 'parent_id' => 4],
        ], $processor->created);
    }

    public function testMultipleRootedWandsPathsStillAssignBothCategories(): void
    {
        $processor = new RecordingCategoryProcessor();
        $plugin = new PreserveCategoryCommas();
        $arguments = $plugin->beforeUpsertCategories(
            $processor,
            'WANDS Catalog/Slicers, Peelers And Graters,WANDS Catalog/Kitchen & Tabletop/Tools',
            ','
        );

        self::assertCount(2, $processor->upsertCategories(...$arguments));
        self::assertSame('Slicers, Peelers And Graters', $processor->created[0]['name']);
        self::assertSame(2, $processor->created[0]['parent_id']);
        self::assertCount(3, $processor->created);
    }

    public function testOtherCatalogsRetainNativeParsing(): void
    {
        $processor = new RecordingCategoryProcessor();
        $plugin = new PreserveCategoryCommas();
        foreach ([
            [null, ','],
            ['Default Category/Gear,Default Category/Training', ','],
        ] as $arguments) {
            self::assertSame($arguments, $plugin->beforeUpsertCategories($processor, ...$arguments));
        }
    }
    public function testImportsUseTheNineDepartmentsAndPutLightingAndRugsUnderDecor(): void
    {
        $processor = new RecordingCategoryProcessor();
        $plugin = new PreserveCategoryCommas();
        $paths = 'WANDS Catalog/Lighting/Lamps,WANDS Catalog/Rugs/Area Rugs,WANDS Catalog/Baby & Kids/Toys,WANDS Catalog/Pet/Crates';
        $arguments = $plugin->beforeUpsertCategories($processor, $paths, ',');
        self::assertCount(4, $processor->upsertCategories(...$arguments));
        self::assertSame(['Decor', 'Lighting', 'Lamps', 'Rugs', 'Area Rugs', 'Kids', 'Toys', 'Pets', 'Crates'], array_column($processor->created, 'name'));
    }

    public function testExplicitAssignmentSeparatorsAlsoNormalizeDepartmentNames(): void
    {
        $processor = new RecordingCategoryProcessor();
        $plugin = new PreserveCategoryCommas();
        self::assertSame(
            ['WANDS Catalog/Slicers, Peelers And Graters;WANDS Catalog/Pets', ';'],
            $plugin->beforeUpsertCategories($processor, 'WANDS Catalog/Slicers, Peelers And Graters;WANDS Catalog/Pet', ';')
        );
    }

}

class RecordingCategoryProcessor extends CategoryProcessor
{
    public array $created = [];
    private int $nextId = 4;

    public function __construct()
    {
        $this->categories = ['wands catalog' => 2, 'default category' => 3];
    }

    protected function createCategory($name, $parentId)
    {
        $this->created[] = ['name' => $name, 'parent_id' => $parentId];
        return $this->nextId++;
    }
}
