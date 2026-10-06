<?php
declare(strict_types=1);

namespace RocketWeb\LabCatalog\Test\Unit\Plugin;

use Magento\CatalogImportExport\Model\StockItemProcessorInterface;
use PHPUnit\Framework\TestCase;
use RocketWeb\LabCatalog\Model\Catalog\StockPreservation;
use RocketWeb\LabCatalog\Plugin\PreserveExistingStock;

require_once dirname(__DIR__, 3) . '/Model/Catalog/StockPreservation.php';
require_once dirname(__DIR__, 3) . '/Plugin/PreserveExistingStock.php';

class PreserveExistingStockTest extends TestCase
{
    public function testExistingStockNeverReachesLegacyOrMsiProcessor(): void
    {
        $context = new StockPreservation();
        $plugin = new PreserveExistingStock($context);
        $subject = $this->createStub(StockItemProcessorInterface::class);
        $seen = [];
        $next = static function (array $stock, array $data) use (&$seen): void {
            $seen[] = [$stock, $data];
        };
        $context->execute(['WANDS-OLD'], function () use ($plugin, $subject, $next): void {
            $plugin->aroundProcess($subject, $next,
                ['WANDS-OLD' => ['qty' => 0], 'WANDS-NEW' => ['qty' => 8]],
                ['WANDS-OLD' => ['sku' => 'WANDS-OLD'], 'WANDS-NEW' => ['sku' => 'WANDS-NEW']]
            );
            $plugin->aroundProcess($subject, $next, ['WANDS-OLD' => ['qty' => 0]], ['WANDS-OLD' => []]);
        });
        self::assertSame([[['WANDS-NEW' => ['qty' => 8]], ['WANDS-NEW' => ['sku' => 'WANDS-NEW']]]], $seen);
        $plugin->aroundProcess($subject, $next, ['WANDS-OLD' => ['qty' => 4]], ['WANDS-OLD' => []]);
        self::assertCount(2, $seen);
        self::assertSame(['WANDS-OLD' => ['qty' => 4]], $seen[1][0]);
    }

    public function testFailureCannotLeavePreservationActiveForLaterImports(): void
    {
        $context = new StockPreservation();
        try {
            $context->execute(['WANDS-OLD'], static function (): void {
                throw new \RuntimeException('Import failed');
            });
            self::fail('Expected failure');
        } catch (\RuntimeException $exception) {
            self::assertSame('Import failed', $exception->getMessage());
        }
        self::assertSame(['WANDS-OLD' => []], $context->filter(['WANDS-OLD' => []]));
    }

    public function testOtherCatalogCannotEnterPreservationScope(): void
    {
        $context = new StockPreservation();
        $this->expectException(\InvalidArgumentException::class);
        $context->execute(['KOTI-ONE'], static fn() => null);
    }

    public function testMagentoInterceptorPassesOnlyNewStockToDownstreamAfterPlugins(): void
    {
        $context = new StockPreservation();
        $guard = new PreserveExistingStock($context);
        $observer = new StockAfterObserver();
        $plugins = $this->createStub(\Magento\Framework\Interception\PluginListInterface::class);
        $plugins->method('getNext')->willReturnCallback(
            static fn($type, $method, $code = null) => $code === null
                ? [\Magento\Framework\Interception\DefinitionInterface::LISTENER_AROUND => 'guard']
                : [\Magento\Framework\Interception\DefinitionInterface::LISTENER_AFTER => ['observer']]
        );
        $plugins->method('getPlugin')->willReturnCallback(
            static fn($type, $code) => $code === 'guard' ? $guard : $observer
        );
        $importer = $this->createMock(\Magento\CatalogImportExport\Model\StockItemImporterInterface::class);
        $importer->expects(self::once())->method('import')->with(['WANDS-NEW' => ['qty' => 8]]);
        $processor = new StockProcessorInterceptor($importer);
        $processor->configurePlugins($plugins);
        $context->execute(['WANDS-OLD'], static function () use ($processor): void {
            $processor->process(['WANDS-OLD' => ['qty' => 0], 'WANDS-NEW' => ['qty' => 8]],
                ['WANDS-OLD' => [], 'WANDS-NEW' => ['sku' => 'WANDS-NEW']]);
            $processor->process(['WANDS-OLD' => ['qty' => 0]], ['WANDS-OLD' => []]);
        });
        self::assertSame([[['WANDS-NEW' => ['qty' => 8]], ['WANDS-NEW' => ['sku' => 'WANDS-NEW']]]], $observer->calls);
    }
}

class StockAfterObserver
{
    public array $calls = [];

    public function afterProcess(StockItemProcessorInterface $subject, mixed $result, array $stock, array $data): void
    {
        $this->calls[] = [$stock, $data];
    }
}

class StockProcessorInterceptor extends \Magento\CatalogImportExport\Model\StockItemProcessor
{
    use \Magento\Framework\Interception\Interceptor;

    public function configurePlugins(\Magento\Framework\Interception\PluginListInterface $plugins): void
    {
        $this->pluginList = $plugins;
        $this->subjectType = get_parent_class($this);
    }

    public function process(array $stockData, array $importedData): void
    {
        $this->___callPlugins('process', [$stockData, $importedData], $this->pluginList->getNext($this->subjectType, 'process'));
    }
}
