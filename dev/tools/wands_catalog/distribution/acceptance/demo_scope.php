<?php
declare(strict_types=1);

// Read-only, target-bound planning and verification for the existing demo.
require '/var/www/html/app/bootstrap.php';
$om = Magento\Framework\App\Bootstrap::create(BP, $_SERVER)->getObjectManager();
$resource = $om->get(Magento\Framework\App\ResourceConnection::class);
$db = $resource->getConnection();
$config = $om->get(Magento\Framework\App\Config\ScopeConfigInterface::class);
if ($db->fetchOne('SELECT DATABASE()') !== 'magento'
    || parse_url((string)$config->getValue('web/secure/base_url'), PHP_URL_HOST) !== 'relevance.comtom.lab') {
    throw new RuntimeException('Wrong demo destination');
}
$mode = $argv[1] ?? '';
$root = BP . '/var/catalog-enriched-20260913-v2';
if (!in_array($mode, ['plan', 'verify'], true)) {
    throw new RuntimeException('Choose plan or verify');
}
$read = static function (string $path): array {
    $stream = fopen($path, 'r');
    $header = fgetcsv($stream, null, ',', '"', '');
    $rows = [];
    while (($values = fgetcsv($stream, null, ',', '"', '')) !== false) {
        $row = array_combine($header, $values);
        if (isset($rows[$row['sku']])) { throw new RuntimeException('Duplicate SKU'); }
        $rows[$row['sku']] = $row;
    }
    fclose($stream);
    return $rows;
};
$rows = [];
foreach (['1-simple', '2-configurable', '3-bundle'] as $name) {
    $rows += $read($root . '/data/' . $name . '.csv');
}
if (count($rows) !== 53844) { throw new RuntimeException('Unexpected source scope'); }
$entities = $db->fetchAll('SELECT entity_id, sku, type_id FROM catalog_product_entity ORDER BY entity_id');
$ids = array_column($entities, 'entity_id', 'sku');
$skus = array_column($entities, 'sku', 'entity_id');
if (count($entities) !== 55044 || array_diff_key($rows, $ids)) {
    throw new RuntimeException('Live product population changed or source SKUs missing');
}
$targetCodes = array_values(array_filter(array_keys(reset($rows)), static fn($code) =>
    str_starts_with($code, 'lab_spec_') || in_array($code, ['description', 'short_description'], true)));
$attributes = $db->fetchAll("SELECT a.*,c.is_visible_on_front,c.is_comparable FROM eav_attribute a
    JOIN catalog_eav_attribute c USING(attribute_id)");
$metadata = array_column($attributes, null, 'attribute_code');
$targetIds = [];
foreach ($targetCodes as $code) {
    if (isset($metadata[$code])) { $targetIds[] = $metadata[$code]['attribute_id']; }
}
$labels = [];
foreach ($db->fetchAll('SELECT o.attribute_id,o.option_id,v.value FROM eav_attribute_option o
    JOIN eav_attribute_option_value v USING(option_id) WHERE v.store_id=0') as $option) {
    $labels[$option['attribute_id']][$option['option_id']] = $option['value'];
}
$values = [];
$protected = [];
$hash = static function (array $records): string {
    $context = hash_init('sha256');
    foreach ($records as $record) { hash_update($context, json_encode($record, JSON_THROW_ON_ERROR) . "\n"); }
    return hash_final($context);
};
$byAttribute = array_column($attributes, 'attribute_code', 'attribute_id');
foreach (['varchar', 'int', 'text', 'decimal', 'datetime'] as $type) {
    $table = 'catalog_product_entity_' . $type;
    $untouched = [];
    foreach ($db->fetchAll('SELECT * FROM ' . $table . ' ORDER BY value_id') as $row) {
        $sku = $skus[$row['entity_id']];
        if (isset($rows[$sku]) && (int)$row['store_id'] === 0 && in_array($row['attribute_id'], $targetIds)) {
            $code = $byAttribute[$row['attribute_id']];
            $value = $row['value'];
            if ($metadata[$code]['frontend_input'] === 'select') {
                $value = $labels[$row['attribute_id']][$value] ?? '__INVALID_OPTION__';
            }
            $values[$sku][$code] = $value;
        } else {
            $untouched[] = $row;
        }
    }
    $protected[$table] = ['rows' => count($untouched), 'sha256' => $hash($untouched)];
}
// Index tables may change. Canonical prices, stock, identity, images, relationships
// and configuration must not. updated_at is the native import bookkeeping field.
foreach (['catalog_product_entity', 'cataloginventory_stock_item', 'inventory_source_item',
    'inventory_reservation', 'catalog_product_super_link', 'catalog_product_super_attribute',
    'catalog_product_relation', 'catalog_product_bundle_option', 'catalog_product_bundle_selection',
    'catalog_product_entity_tier_price', 'catalog_product_entity_media_gallery',
    'catalog_product_entity_media_gallery_value', 'catalog_product_entity_media_gallery_value_to_entity',
    'core_config_data'] as $table) {
    $records = $db->fetchAll('SELECT * FROM ' . $table . ' ORDER BY 1');
    if ($table === 'catalog_product_entity') {
        foreach ($records as &$record) { unset($record['updated_at']); }
        unset($record);
    }
    $protected[$table] = ['rows' => count($records), 'sha256' => $hash($records)];
}
$changes = [];
$csv = [];
foreach ($rows as $sku => $row) {
    $update = ['sku' => $sku];
    foreach ($targetCodes as $code) {
        $desired = $row[$code] ?? '';
        $actual = $values[$sku][$code] ?? '';
        $same = (string)$actual === (string)$desired;
        if (($metadata[$code]['backend_type'] ?? '') === 'decimal' && is_numeric($actual) && is_numeric($desired)) {
            $same = abs((float)$actual - (float)$desired) < 0.00005;
        }
        if (!$same) {
            $changes[$code] = ($changes[$code] ?? 0) + 1;
            $update[$code] = $desired === '' ? '__EMPTY__VALUE__' : $desired;
        }
    }
    if (count($update) > 1) { $csv[$sku] = $update; }
}
$expectedLinks = [];
foreach ($read($root . '/data/5-merchandising.csv') as $sku => $row) {
    foreach (['related_skus' => 1, 'crosssell_skus' => 5] as $code => $type) {
        foreach (array_filter(explode(',', $row[$code] ?? '')) as $target) {
            if (!isset($ids[$target])) { throw new RuntimeException('Missing linked product'); }
            $expectedLinks[] = $sku . ':' . $type . ':' . $target;
        }
    }
}
$actualLinks = [];
foreach ($db->fetchAll('SELECT * FROM catalog_product_link') as $link) {
    $actualLinks[] = $skus[$link['product_id']] . ':' . $link['link_type_id'] . ':' . $skus[$link['linked_product_id']];
}
sort($expectedLinks); sort($actualLinks);
$report = ['products' => count($entities), 'source_products' => count($rows), 'extra_products_preserved' => 1200,
    'changed_products' => count($csv), 'attribute_changes' => $changes,
    'attribute_change_count' => array_sum($changes), 'desired_links' => count($expectedLinks),
    'existing_links' => count($actualLinks), 'missing_attributes' => array_values(array_diff($targetCodes, array_keys($metadata))),
    'protected' => $protected, 'search_engine' => $config->getValue('catalog/search/engine')];
if ($mode === 'plan') {
    if ($actualLinks !== []) { throw new RuntimeException('Expected link-free original demo'); }
    $stream = fopen($root . '/attributes.csv', 'x');
    if (!$stream) { throw new RuntimeException('Plan already exists'); }
    $columns = ['sku', ...$targetCodes];
    fputcsv($stream, $columns, ',', '"', '');
    foreach ($csv as $row) {
        fputcsv($stream, array_map(static fn($code) => $row[$code] ?? '', $columns), ',', '"', '');
    }
    fclose($stream);
    $report['csv_sha256'] = hash_file('sha256', $root . '/attributes.csv');
} else {
    $before = json_decode(file_get_contents($root . '/plan.json'), true, 512, JSON_THROW_ON_ERROR);
    $report['protected_unchanged'] = $before['protected'] === $protected;
    $report['links_exact'] = $expectedLinks === $actualLinks;
    $report['status'] = $csv === [] && $report['missing_attributes'] === []
        && $report['protected_unchanged'] && $report['links_exact']
        && $report['search_engine'] === $before['search_engine'] ? 'passed' : 'failed';
}
$output = fopen($root . '/' . $mode . '.json', 'x');
if (!$output) { throw new RuntimeException('Receipt already exists'); }
fwrite($output, json_encode($report, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR)); fclose($output);
echo json_encode(array_diff_key($report, ['protected' => true]), JSON_PRETTY_PRINT) . "\n";
exit(($report['status'] ?? 'passed') === 'passed' ? 0 : 1);
