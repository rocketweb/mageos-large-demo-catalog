<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Test\Unit\Setup\Patch\Data;

use Magento\Eav\Setup\EavSetup;
use Magento\Eav\Setup\EavSetupFactory;
use Magento\Framework\DB\Adapter\AdapterInterface;
use Magento\Framework\Filesystem\Driver\File;
use Magento\Framework\Setup\ModuleDataSetupInterface;
use PHPUnit\Framework\TestCase;
use RocketWeb\LabCatalog\Setup\Patch\Data\AddDepthAttributes;
use RuntimeException;

$patchPath = dirname(__DIR__, 5) . '/Setup/Patch/Data/AddDepthAttributes.php';
if (is_file($patchPath)) {
    require_once $patchPath;
}

class AddDepthAttributesTest extends TestCase
{
    public function testCreatesSchemaWithControlledFacetsAndDisplayOnlyMeasurements(): void
    {
        $setup = $this->createMock(EavSetup::class);
        $setup->method('getAttribute')->willReturn(false);
        $created = [];
        $setup->expects(self::exactly(21))->method('addAttribute')->willReturnCallback(
            function ($entity, $code, $config) use (&$created, $setup): EavSetup {
                $created[$code] = $config;
                return $setup;
            }
        );
        $this->patch($setup)->apply();
        self::assertSame('decimal', $created['lab_spec_width_cm']['type']);
        self::assertSame(false, $created['lab_spec_width_cm']['filterable']);
        self::assertSame('select', $created['lab_spec_style']['input']);
        self::assertSame(1, $created['lab_spec_style']['filterable']);
        self::assertContains('Modern', $created['lab_spec_style']['option']['values']);
        self::assertSame(false, $created['lab_spec_style']['searchable']);
        self::assertSame(true, $created['lab_spec_style']['used_in_product_listing']);
    }

    public function testExistingCompatibleAttributesAreNotOverwritten(): void
    {
        $setup = $this->createMock(EavSetup::class);
        $schema = json_decode(file_get_contents(dirname(__DIR__, 5) . '/etc/depth_attributes.json'), true);
        $setup->method('getAttribute')->willReturnCallback(static function ($entity, $code) use ($schema): array {
            $kind = $schema['attributes'][$code]['kind'];
            $backend = $kind === 'length' ? 'decimal' : ($kind === 'select' ? 'int' : 'text');
            return ['attribute_id' => 42, 'backend_type' => $backend,
                'frontend_input' => $kind === 'select' ? 'select' : ($kind === 'text' ? 'textarea' : 'text')];
        });
        $setup->expects(self::never())->method('addAttribute');
        $this->patch($setup)->apply();
    }

    public function testTypeConflictStopsBeforeAnyAttributeWrite(): void
    {
        $setup = $this->createMock(EavSetup::class);
        $setup->method('getAttribute')->willReturn(
            ['attribute_id' => 42, 'backend_type' => 'varchar', 'frontend_input' => 'text']
        );
        $setup->expects(self::never())->method('addAttribute');
        $this->expectException(RuntimeException::class);
        $this->patch($setup, false)->apply();
    }

    private function patch(EavSetup $setup, bool $starts = true): AddDepthAttributes
    {
        $connection = $this->createMock(AdapterInterface::class);
        $connection->expects($starts ? self::once() : self::never())->method('startSetup');
        $connection->expects($starts ? self::once() : self::never())->method('endSetup');
        $module = $this->createStub(ModuleDataSetupInterface::class);
        $module->method('getConnection')->willReturn($connection);
        $factory = $this->createStub(EavSetupFactory::class);
        $factory->method('create')->willReturn($setup);
        $driver = $this->createStub(File::class);
        $driver->method('fileGetContents')->willReturn(
            file_get_contents(dirname(__DIR__, 5) . '/etc/depth_attributes.json')
        );
        return new AddDepthAttributes($module, $factory, $driver);
    }
}
