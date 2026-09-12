<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Test\Unit\Model\Catalog;

use Magento\Framework\Filesystem;
use Magento\Framework\Filesystem\Directory\ReadInterface;
use Magento\Framework\Filesystem\Driver\File;
use Magento\Framework\App\ResourceConnection;
use PHPUnit\Framework\TestCase;
use RocketWeb\LabCatalog\Model\Catalog\BundleAssortmentReconciler;

require_once dirname(__DIR__, 4) . '/Model/Catalog/BundleAssortmentReconciler.php';

class BundleAssortmentReconcilerTest extends TestCase
{
    private string $temporaryFile;

    protected function tearDown(): void
    {
        if (isset($this->temporaryFile) && is_file($this->temporaryFile)) {
            unlink($this->temporaryFile);
        }
    }

    public function testBundleScopeRejectsNonBundleRows(): void
    {
        $reconciler = $this->reconciler("sku,product_type\nWANDS-000001,simple\n");

        $method = new \ReflectionMethod($reconciler, 'bundleSkus');

        $this->expectException(\RuntimeException::class);
        $this->expectExceptionMessage('only bounded WANDS bundle rows');
        $method->invoke($reconciler, $this->temporaryFile);
    }

    public function testBundleScopeReturnsExactUniqueSkus(): void
    {
        $reconciler = $this->reconciler(
            "sku,product_type\nWANDS-BUNDLE-001,bundle\nWANDS-BUNDLE-050,bundle\n"
        );

        $method = new \ReflectionMethod($reconciler, 'bundleSkus');

        self::assertSame(
            ['WANDS-BUNDLE-001', 'WANDS-BUNDLE-050'],
            $method->invoke($reconciler, $this->temporaryFile)
        );
    }

    private function reconciler(string $contents): BundleAssortmentReconciler
    {
        $this->temporaryFile = tempnam(sys_get_temp_dir(), 'wands-bundles-');
        file_put_contents($this->temporaryFile, $contents);
        $directory = $this->createStub(ReadInterface::class);
        $directory->method('getAbsolutePath')->willReturn(dirname($this->temporaryFile) . DIRECTORY_SEPARATOR);
        $filesystem = $this->createStub(Filesystem::class);
        $filesystem->method('getDirectoryRead')->willReturn($directory);
        $driver = $this->createStub(File::class);
        $driver->method('getRealPath')->willReturn($this->temporaryFile);
        $driver->method('isFile')->willReturn(true);

        return new BundleAssortmentReconciler(
            $this->createStub(ResourceConnection::class),
            $filesystem,
            $driver
        );
    }
}
