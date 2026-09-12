<?php

declare(strict_types=1);

use Magento\Framework\App\Bootstrap;
use Magento\Framework\App\ResourceConnection;

require '/var/www/html/app/bootstrap.php';
$data = $argv[1];
$output = $argv[2];
$expected = json_decode(file_get_contents($data . '/counts.json'), true, 512, JSON_THROW_ON_ERROR);
$objectManager = Bootstrap::create(BP, $_SERVER)->getObjectManager();
$resource = $objectManager->get(ResourceConnection::class);
$connection = $resource->getConnection();
$failures = [];
$checks = 0;
$check = static function (bool $valid, string $message) use (&$failures, &$checks): void {
    $checks++;
    if (!$valid && count($failures) < 100) {
        $failures[] = $message;
    }
};
$read = static function (string $file): array {
    $stream = fopen($file, 'r');
    $header = fgetcsv($stream, null, ',', '"', '');
    $rows = [];
    while (($row = fgetcsv($stream, null, ',', '"', '')) !== false) {
        $record = array_combine($header, $row);
        $rows[$record['sku']] = $record;
    }
    fclose($stream);
    return $rows;
};
$rows = [];
foreach (['1-simple.csv', '2-configurable.csv', '3-bundle.csv'] as $file) {
    $rows += $read($data . '/' . $file);
}
$entities = $connection->fetchAll($connection->select()->from($resource->getTableName('catalog_product_entity')));
$bySku = [];
$byId = [];
$types = [];
foreach ($entities as $entity) {
    $bySku[$entity['sku']] = $entity;
    $byId[(int)$entity['entity_id']] = $entity['sku'];
    $types[$entity['type_id']] = ($types[$entity['type_id']] ?? 0) + 1;
}
$check(count($entities) === $expected['products'], 'Product count mismatch');
foreach ($expected['product_types'] as $type => $count) {
    $check(($types[$type] ?? 0) === $count, 'Type count mismatch: ' . $type);
}
$attributes = $connection->fetchPairs('SELECT attribute_id, attribute_code FROM ' . $resource->getTableName('eav_attribute') . ' WHERE entity_type_id = 4');
$values = [];
foreach (['varchar', 'decimal', 'int', 'text'] as $type) {
    $table = $resource->getTableName('catalog_product_entity_' . $type);
    $ids = array_keys(array_filter($attributes, static fn(string $code): bool => in_array($code, ['name', 'price', 'special_price', 'status', 'image', 'small_image', 'thumbnail'], true)));
    foreach ($connection->fetchAll($connection->select()->from($table)->where('store_id = 0')->where('attribute_id IN (?)', $ids)) as $value) {
        $values[$byId[(int)$value['entity_id']]][$attributes[$value['attribute_id']]] = $value['value'];
    }
}
$stock = $connection->fetchAll($connection->select()->from($resource->getTableName('cataloginventory_stock_item')));
$stocks = [];
foreach ($stock as $item) {
    $stocks[$byId[(int)$item['product_id']]] = $item;
}
foreach ($rows as $sku => $row) {
    $check(isset($bySku[$sku]), 'Missing SKU: ' . $sku);
    $check(($bySku[$sku]['type_id'] ?? '') === $row['product_type'], 'Type mismatch: ' . $sku);
    $actual = $values[$sku] ?? [];
    $check(($actual['name'] ?? '') === $row['name'], 'Name mismatch: ' . $sku);
    $check((int)($actual['status'] ?? 0) === (int)$row['product_online'], 'Status mismatch: ' . $sku);
    if ($row['product_type'] !== 'bundle') {
        $check(abs((float)($actual['price'] ?? 0) - (float)$row['price']) < 0.005, 'Price mismatch: ' . $sku);
    }
    if (($row['special_price'] ?? '') === '') {
        $check(!isset($actual['special_price']), 'Unexpected special price: ' . $sku);
    } else {
        $check(abs((float)($actual['special_price'] ?? 0) - (float)$row['special_price']) < 0.005, 'Special price mismatch: ' . $sku);
    }
    $check(abs((float)($stocks[$sku]['qty'] ?? -999) - (float)$row['qty']) < 0.005, 'Stock quantity mismatch: ' . $sku);
    if ((int)$row['manage_stock'] === 0 && (int)$row['use_config_manage_stock'] === 0) {
        $check((int)($stocks[$sku]['manage_stock'] ?? -1) === 0 && (int)($stocks[$sku]['use_config_manage_stock'] ?? -1) === 0, 'Unmanaged stock configuration mismatch: ' . $sku);
    } else {
        $check((int)($stocks[$sku]['is_in_stock'] ?? -1) === (int)$row['is_in_stock'], 'Stock flag mismatch: ' . $sku);
    }
}
$actualLinks = [];
foreach ($connection->fetchAll($connection->select()->from($resource->getTableName('catalog_product_super_link'))) as $link) {
    $actualLinks[$byId[(int)$link['parent_id']] . '|' . $byId[(int)$link['product_id']]] = true;
}
$expectedLinks = [];
foreach ($rows as $sku => $row) {
    if ($row['product_type'] === 'configurable') {
        foreach (explode('|', $row['configurable_variations']) as $variation) {
            preg_match('/^sku=([^,]+)/', $variation, $match);
            $expectedLinks[$sku . '|' . $match[1]] = true;
        }
    }
}
$check(count($actualLinks) === $expected['configurable_links'] && array_keys(array_diff_key($actualLinks, $expectedLinks)) === [] && array_keys(array_diff_key($expectedLinks, $actualLinks)) === [], 'Configurable relationship mismatch');
$actualAxes = [];
foreach ($connection->fetchAll($connection->select()->from($resource->getTableName('catalog_product_super_attribute'))) as $axis) {
    $actualAxes[$byId[(int)$axis['product_id']] . '|' . $attributes[$axis['attribute_id']]] = true;
}
$expectedAxes = [];
$optionLabels = $connection->fetchPairs('SELECT option_id,value FROM ' . $resource->getTableName('eav_attribute_option_value') . ' WHERE store_id=0');
$variantValues = [];
$axisIds = [];
foreach ($actualAxes as $axis => $unused) {
    [, $code] = explode('|', $axis, 2);
    $axisIds[] = array_search($code, $attributes, true);
}
if ($axisIds !== []) {
    foreach ($connection->fetchAll($connection->select()->from($resource->getTableName('catalog_product_entity_int'))->where('store_id=0')->where('attribute_id IN (?)', array_unique($axisIds))) as $value) {
        $variantValues[$byId[(int)$value['entity_id']]][$attributes[$value['attribute_id']]] = $optionLabels[$value['value']] ?? null;
    }
}
foreach ($rows as $sku => $row) {
    if ($row['product_type'] !== 'configurable') {
        continue;
    }
    foreach (explode('|', $row['configurable_variations']) as $variation) {
        $fields = explode(',', $variation);
        $child = substr(array_shift($fields), 4);
        foreach ($fields as $field) {
            [$code, $label] = explode('=', $field, 2);
            $expectedAxes[$sku . '|' . $code] = true;
            $check(($variantValues[$child][$code] ?? null) === $label, 'Configurable option value mismatch: ' . $child . ':' . $code);
        }
    }
}
$check(array_diff_key($actualAxes, $expectedAxes) === [] && array_diff_key($expectedAxes, $actualAxes) === [], 'Configurable axis mismatch');
$bundleOptions = (int)$connection->fetchOne('SELECT COUNT(*) FROM ' . $resource->getTableName('catalog_product_bundle_option'));
$bundleSelections = (int)$connection->fetchOne('SELECT COUNT(*) FROM ' . $resource->getTableName('catalog_product_bundle_selection'));
$check($bundleOptions === $expected['bundle_options'], 'Bundle option count mismatch');
$check($bundleSelections === $expected['bundle_selections'], 'Bundle selection count mismatch');
$selectionRows = $connection->fetchAll(
    'SELECT s.*, o.required, o.type, v.title FROM ' . $resource->getTableName('catalog_product_bundle_selection') . ' s '
    . 'JOIN ' . $resource->getTableName('catalog_product_bundle_option') . ' o ON o.option_id=s.option_id '
    . 'JOIN ' . $resource->getTableName('catalog_product_bundle_option_value') . ' v ON v.option_id=o.option_id AND v.store_id=0'
);
$selectionMap = [];
foreach ($selectionRows as $selection) {
    $key = $byId[(int)$selection['parent_product_id']] . '|' . $selection['title'] . '|' . $byId[(int)$selection['product_id']];
    $selectionMap[$key] = $selection;
}
$expectedSelections = [];
foreach ($rows as $sku => $row) {
    if ($row['product_type'] !== 'bundle') {
        continue;
    }
    foreach (explode('|', $row['bundle_values']) as $group) {
        $parts = [];
        foreach (explode(',', $group) as $field) {
            [$key, $value] = explode('=', $field, 2);
            $parts[$key] = $value;
        }
        $key = $sku . '|' . $parts['name'] . '|' . $parts['sku'];
        $expectedSelections[$key] = true;
        $selection = $selectionMap[$key] ?? [];
        $check($selection !== [], 'Missing bundle selection: ' . $key);
        foreach (['required' => 'required', 'default' => 'is_default', 'default_qty' => 'selection_qty',
            'price' => 'selection_price_value', 'can_change_qty' => 'selection_can_change_qty'] as $source => $target) {
            $check(isset($selection[$target]) && abs((float)$selection[$target] - (float)$parts[$source]) < 0.005, 'Bundle selection field mismatch: ' . $key . ':' . $source);
        }
        $check(($selection['type'] ?? '') === ($parts['type'] === 'dropdown' ? 'select' : $parts['type']), 'Bundle option type mismatch: ' . $key);
        $check((int)($selection['selection_price_type'] ?? -1) === ($parts['price_type'] === 'fixed' ? 0 : 1), 'Bundle price type mismatch: ' . $key);
    }
}
$check(array_diff_key($selectionMap, $expectedSelections) === [], 'Unexpected bundle selection');
$media = $read($data . '/4-media.csv');
$lineage = json_decode(file_get_contents($data . '/media-lineage.json'), true, 512, JSON_THROW_ON_ERROR)['assignments'];
$hashes = [];
foreach ($media as $sku => $row) {
    foreach (['image', 'small_image', 'thumbnail'] as $role) {
        $file = $values[$sku][$role] ?? '';
        $path = BP . '/pub/media/catalog/product' . $file;
        if (!isset($hashes[$file])) {
            $hashes[$file] = is_file($path) ? hash_file('sha256', $path) : false;
        }
        $check($hashes[$file] === $lineage[$sku]['sha256'], 'Media mismatch: ' . $sku . ':' . $role);
    }
}
$report = ['status' => $failures === [] ? 'passed' : 'failed', 'checks' => $checks, 'product_types' => $types,
    'unmanaged_stock_flags_not_treated_as_availability' => true,
    'configurable_links' => count($actualLinks), 'bundle_options' => $bundleOptions, 'bundle_selections' => $bundleSelections,
    'configurable_axes' => count($actualAxes),
    'media_roles' => count($media) * 3, 'failures' => $failures];
file_put_contents($output, json_encode($report, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR));
exit($failures === [] ? 0 : 1);
