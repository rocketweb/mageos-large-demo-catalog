<?php

declare(strict_types=1);

namespace Magento\Framework\Setup\Patch {
    interface DataPatchInterface
    {
    }
}

namespace {
    require __DIR__ . '/../../../../app/code/RocketWeb/LabCatalog/Setup/Patch/Data/AddMerchandisingAttributes.php';
    $class = new ReflectionClass(\RocketWeb\LabCatalog\Setup\Patch\Data\AddMerchandisingAttributes::class);
    $options = $class->getConstant('ATTRIBUTE_OPTIONS');
    $packet = json_decode(file_get_contents($argv[1]), true, 512, JSON_THROW_ON_ERROR);
    $expected = $packet['attribute_options'] ?? $packet;
    foreach ($expected as $code => $values) {
        $missing = array_diff($values, $options[$code] ?? []);
        if ($missing !== []) {
            throw new RuntimeException('Missing setup options for ' . $code . ': ' . implode(', ', $missing));
        }
    }
    echo "All configurable options are provisioned\n";
}
