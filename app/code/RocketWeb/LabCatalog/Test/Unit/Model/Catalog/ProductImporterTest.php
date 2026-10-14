<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Test\Unit\Model\Catalog;

use Magento\Framework\App\State;
use Magento\Framework\Filesystem;
use Magento\Framework\Filesystem\Directory\ReadInterface;
use Magento\ImportExport\Model\Import;
use Magento\ImportExport\Model\ImportFactory;
use Magento\ImportExport\Model\Import\ErrorProcessing\ProcessingErrorAggregatorInterface;
use Magento\ImportExport\Model\Import\Source\Csv;
use Magento\ImportExport\Model\Import\Source\CsvFactory;
use PHPUnit\Framework\TestCase;
use RocketWeb\LabCatalog\Model\Catalog\BundleAssortmentReconciler;
use RocketWeb\LabCatalog\Model\Catalog\NavigationCurator;
use RocketWeb\LabCatalog\Model\Catalog\ProductImporter;
use RocketWeb\LabCatalog\Model\Catalog\StockPreservation;

foreach (['BundleAssortmentReconciler', 'NavigationCurator', 'StockPreservation', 'ProductImporter'] as $class) {
    require_once dirname(__DIR__, 4) . '/Model/Catalog/' . $class . '.php';
}

class ProductImporterTest extends TestCase
{
    private string $csv;

    protected function setUp(): void
    {
        $this->csv = tempnam(sys_get_temp_dir(), 'wands-import-');
        file_put_contents($this->csv, "sku,name\nWANDS-TEST,Test\n");
    }

    protected function tearDown(): void
    {
        unlink($this->csv);
    }

    public function testSuccessfulImportAutomaticallyCuratesNavigation(): void
    {
        $navigation = $this->createMock(NavigationCurator::class);
        $navigation->expects(self::once())->method('execute')->willReturn([
            'visible_departments' => 9, 'hidden_departments' => 47,
        ]);
        $import = $this->import(true);
        $import->expects(self::once())->method('importSource')->willReturn(true);

        $result = $this->importer($import, $navigation)->execute($this->csv);

        self::assertArrayHasKey('navigation', $result);
        self::assertSame(9, $result['navigation']['visible_departments']);
        self::assertFalse($result['validated_only']);
    }

    public function testValidationOnlyDoesNotChangeNavigation(): void
    {
        $navigation = $this->createMock(NavigationCurator::class);
        $navigation->expects(self::never())->method('execute');
        $import = $this->import(true);
        $import->expects(self::never())->method('importSource');

        $result = $this->importer($import, $navigation)->execute($this->csv, true);

        self::assertTrue($result['validated_only']);
        self::assertArrayNotHasKey('navigation', $result);
    }

    public function testFailedImportDoesNotCurateNavigation(): void
    {
        $navigation = $this->createMock(NavigationCurator::class);
        $navigation->expects(self::never())->method('execute');
        $import = $this->import(true);
        $import->expects(self::once())->method('importSource')->willReturn(false);

        $this->expectException(\RuntimeException::class);
        $this->expectExceptionMessage('Product import failed');
        $this->importer($import, $navigation)->execute($this->csv);
    }

    private function import(bool $valid): Import
    {
        $import = $this->createMock(Import::class);
        $errors = $this->createStub(ProcessingErrorAggregatorInterface::class);
        $errors->method('getErrorsCount')->willReturn(0);
        $errors->method('getInvalidRowsCount')->willReturn(0);
        $errors->method('getAllErrors')->willReturn([]);
        $import->method('validateSource')->willReturn($valid);
        $import->method('getErrorAggregator')->willReturn($errors);
        return $import;
    }

    private function importer(Import $import, NavigationCurator $navigation): ProductImporter
    {
        $factory = $this->createStub(ImportFactory::class);
        $factory->method('create')->willReturn($import);
        $csvFactory = $this->createStub(CsvFactory::class);
        $csvFactory->method('create')->willReturn($this->createStub(Csv::class));
        $directory = $this->createStub(ReadInterface::class);
        $directory->method('getAbsolutePath')->willReturn(dirname($this->csv));
        $filesystem = $this->createStub(Filesystem::class);
        $filesystem->method('getDirectoryRead')->willReturn($directory);
        $state = $this->createStub(State::class);
        $state->method('emulateAreaCode')->willReturnCallback(static fn($area, $callback) => $callback());

        return new ProductImporter(
            $factory,
            $csvFactory,
            $filesystem,
            $state,
            $this->createStub(\Magento\Framework\App\ResourceConnection::class),
            $this->createStub(BundleAssortmentReconciler::class),
            new StockPreservation(),
            $navigation,
        );
    }
}
