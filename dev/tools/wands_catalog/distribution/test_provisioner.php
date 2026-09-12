<?php

declare(strict_types=1);

namespace Magento\Config\Model\ResourceModel {
    class Config
    {
        public array $writes = [];

        public function saveConfig(string $path, string $value, string $scope, int $scopeId): void
        {
            $this->writes[$path] = [$value, $scope, $scopeId];
        }
    }
}

namespace {
    require __DIR__ . '/../../../../app/code/RocketWeb/LabCatalog/Model/Catalog/StoreProvisioner.php';

    $class = new ReflectionClass(\RocketWeb\LabCatalog\Model\Catalog\StoreProvisioner::class);
    $instance = $class->newInstanceWithoutConstructor();
    foreach (['', 'file:///tmp/catalog', 'https://user:secret@example.test/', 'https://example.test/?key=value'] as $url) {
        try {
            $instance->provision($url);
            throw new RuntimeException('Invalid URL accepted');
        } catch (InvalidArgumentException $exception) {
        }
    }
    $config = new \Magento\Config\Model\ResourceModel\Config();
    $class->getProperty('configResource')->setValue($instance, $config);
    $method = $class->getMethod('saveStoreConfiguration');
    $method->invoke($instance, 7, 'https://example.test/', null);
    if (isset($config->writes['design/theme/theme_id'])) {
        throw new RuntimeException('Inherited theme was overwritten');
    }
    $method->invoke($instance, 7, 'https://example.test/', 12);
    if ($config->writes['design/theme/theme_id'] !== ['12', 'stores', 7]) {
        throw new RuntimeException('Explicit theme was not scoped');
    }
    if ($class->hasMethod('saveCatalogConfiguration')) {
        throw new RuntimeException('Provisioning must not change global price scope');
    }
    echo "Provisioning contract tests passed\n";
}
