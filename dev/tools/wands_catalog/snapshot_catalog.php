<?php

declare(strict_types=1);

function identifier(string $value): string
{
    if (!preg_match('/^[a-zA-Z0-9_]+$/', $value)) {
        throw new RuntimeException('Unsupported SQL identifier');
    }
    return '`' . $value . '`';
}

function exportRows(PDO $pdo, string $table, array $clauses, string $output): array
{
    $stream = fopen($output, 'x');
    if ($stream === false) {
        throw new RuntimeException('Snapshot output already exists or cannot be created');
    }
    $seen = [];
    $count = 0;
    foreach ($clauses as [$where, $parameters]) {
        $statement = $pdo->prepare('SELECT * FROM ' . $table . ' WHERE ' . $where);
        $statement->execute($parameters);
        while ($row = $statement->fetch(PDO::FETCH_ASSOC)) {
            $encoded = json_encode($row, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
            $hash = hash('sha256', $encoded);
            if (isset($seen[$hash])) {
                continue;
            }
            $seen[$hash] = true;
            fwrite($stream, $encoded . PHP_EOL);
            $count++;
        }
    }
    fflush($stream);
    fsync($stream);
    fclose($stream);
    return ['rows' => $count, 'sha256' => hash_file('sha256', $output)];
}

function conditions(array $values, array $columns): array
{
    $clauses = [];
    foreach (array_chunk($values, 400) as $chunk) {
        $parts = [];
        $parameters = [];
        foreach ($columns as $column) {
            $parts[] = identifier($column) . ' IN (' . implode(',', array_fill(0, count($chunk), '?')) . ')';
            array_push($parameters, ...$chunk);
        }
        $clauses[] = [implode(' OR ', $parts), $parameters];
    }
    return $clauses;
}

function readJsonLines(string $file): array
{
    $rows = [];
    $stream = fopen($file, 'r');
    while (($line = fgets($stream)) !== false) {
        $rows[] = json_decode($line, true, 512, JSON_THROW_ON_ERROR);
    }
    fclose($stream);
    return $rows;
}

function snapshot(array $options): void
{
    $request = json_decode(file_get_contents($options['request']), true, 512, JSON_THROW_ON_ERROR);
    if (($request['version'] ?? null) !== 1 || ($request['expected_host'] ?? '') !== 'relevance.comtom.lab') {
        throw new RuntimeException('Unsupported snapshot request or destination');
    }
    $skus = $request['skus'];
    if (!$skus || count($skus) !== count(array_unique($skus)) || count($skus) > 60000) {
        throw new RuntimeException('Invalid exact SKU scope');
    }
    foreach ($skus as $sku) {
        if (!preg_match('/^WANDS-[A-Z0-9-]+$/', $sku)) {
            throw new RuntimeException('Snapshot scope contains a non-WANDS SKU');
        }
    }
    $root = realpath($options['root']);
    if ($root === false || !is_file($root . '/app/etc/env.php')) {
        throw new RuntimeException('Mage-OS root not found');
    }
    $environment = require $root . '/app/etc/env.php';
    $connection = $environment['db']['connection']['default'];
    $database = (string)$connection['dbname'];
    $prefix = (string)($environment['db']['table_prefix'] ?? '');
    $dsn = 'mysql:host=' . $connection['host'] . ';dbname=' . $database . ';charset=utf8mb4';
    if (!empty($connection['port'])) {
        $dsn .= ';port=' . (int)$connection['port'];
    }
    $pdo = new PDO($dsn, $connection['username'], $connection['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    if ($pdo->query('SELECT DATABASE()')->fetchColumn() !== $database) {
        throw new RuntimeException('Database context mismatch');
    }
    $table = static fn(string $name): string => identifier($database) . '.' . identifier($prefix . $name);
    $output = $options['output-dir'];
    if (file_exists($output) || !mkdir($output, 0700, true)) {
        throw new RuntimeException('Choose a fresh snapshot directory');
    }
    $pdo->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
    $pdo->exec('SET TRANSACTION READ ONLY');
    $pdo->beginTransaction();
    try {
        $configPaths = ['web/unsecure/base_url', 'web/secure/base_url', 'cataloginventory/item_options/manage_stock',
            'cataloginventory/item_options/backorders', 'catalog/price/scope', 'currency/options/base',
            'currency/options/default', 'tax/display/type', 'catalog/seo/product_url_suffix'];
        $configStatement = $pdo->prepare('SELECT scope, scope_id, path, value FROM ' . $table('core_config_data')
            . ' WHERE path IN (' . implode(',', array_fill(0, count($configPaths), '?')) . ')');
        $configStatement->execute($configPaths);
        $config = $configStatement->fetchAll(PDO::FETCH_ASSOC);
        $hosts = [];
        foreach ($config as $row) {
            if (in_array($row['path'], ['web/unsecure/base_url', 'web/secure/base_url'], true)) {
                $hosts[] = parse_url((string)$row['value'], PHP_URL_HOST);
            }
        }
        if (!in_array($request['expected_host'], $hosts, true)) {
            throw new RuntimeException('Configured base URL does not match requested store');
        }
        $manifest = ['version' => 1, 'consistent_read_only' => true, 'captured_at' => gmdate('c'),
            'host' => $request['expected_host'], 'database' => $database, 'prefix' => $prefix,
            'request_sha256' => hash_file('sha256', $options['request']), 'packet_sha256' => $request['packet_sha256'],
            'config' => $config, 'tables' => []];
        $manifest['tables']['catalog_product_entity'] = exportRows($pdo, $table('catalog_product_entity'),
            conditions($skus, ['sku']), $output . '/catalog_product_entity.jsonl');
        $entities = readJsonLines($output . '/catalog_product_entity.jsonl');
        $ids = array_column($entities, 'entity_id');
        $found = array_column($entities, 'sku');
        $manifest['missing_skus'] = array_values(array_diff($skus, $found));
        $bundleIds = [];
        foreach ($entities as $entity) {
            if (in_array($entity['sku'], $request['bundle_skus'], true)) {
                $bundleIds[] = $entity['entity_id'];
            }
        }
        $specs = [
            'eav_attribute' => [['entity_type_id IN (SELECT entity_type_id FROM ' . $table('eav_entity_type') . ' WHERE entity_type_code=?)', ['catalog_product']]],
            'eav_entity_attribute' => conditions(array_unique(array_column($entities, 'attribute_set_id')), ['attribute_set_id']),
            'catalog_eav_attribute' => [['attribute_id IN (SELECT attribute_id FROM ' . $table('eav_attribute') . ' WHERE entity_type_id IN (SELECT entity_type_id FROM ' . $table('eav_entity_type') . ' WHERE entity_type_code=?))', ['catalog_product']]],
            'cataloginventory_stock_item' => conditions($ids, ['product_id']),
            'catalog_product_super_link' => conditions($ids, ['parent_id', 'product_id']),
            'catalog_product_super_attribute' => conditions($ids, ['product_id']),
            'catalog_product_relation' => conditions($ids, ['parent_id', 'child_id']),
            'catalog_product_bundle_option' => conditions($bundleIds, ['parent_id']),
            'catalog_product_bundle_option_value' => conditions($bundleIds, ['parent_product_id']),
            'catalog_product_bundle_selection' => conditions($bundleIds, ['parent_product_id']),
            'catalog_product_bundle_selection_price' => conditions($bundleIds, ['parent_product_id']),
            'catalog_product_website' => conditions($ids, ['product_id']),
            'catalog_category_product' => conditions($ids, ['product_id']),
            'catalog_product_entity_media_gallery_value_to_entity' => conditions($ids, ['entity_id']),
            'catalog_product_entity_media_gallery_value' => conditions($ids, ['entity_id']),
            'inventory_source_item' => conditions($skus, ['sku']),
            'store' => [['1=1', []]],
            'store_website' => [['1=1', []]],
        ];
        foreach (['varchar', 'text', 'decimal', 'int', 'datetime'] as $type) {
            $specs['catalog_product_entity_' . $type] = conditions($ids, ['entity_id']);
        }
        foreach ($specs as $name => $clauses) {
            $check = $pdo->prepare('SELECT ENGINE FROM information_schema.tables WHERE table_schema=? AND table_name=?');
            $check->execute([$database, $prefix . $name]);
            $engine = $check->fetchColumn();
            if ($engine === false && $name === 'inventory_source_item') {
                $manifest['inventory_source_item_absent'] = true;
                continue;
            }
            if (strtolower((string)$engine) !== 'innodb') {
                throw new RuntimeException('Missing or nontransactional snapshot table: ' . $name);
            }
            $manifest['tables'][$name] = exportRows($pdo, $table($name), $clauses, $output . '/' . $name . '.jsonl');
        }
        $attributeIds = [];
        foreach (readJsonLines($output . '/eav_attribute.jsonl') as $attribute) {
            if (in_array($attribute['attribute_code'], $request['attributes'], true)) {
                $attributeIds[] = $attribute['attribute_id'];
            }
        }
        $manifest['tables']['eav_attribute_option'] = exportRows($pdo, $table('eav_attribute_option'), conditions($attributeIds, ['attribute_id']), $output . '/eav_attribute_option.jsonl');
        $optionIds = array_column(readJsonLines($output . '/eav_attribute_option.jsonl'), 'option_id');
        $manifest['tables']['eav_attribute_option_value'] = exportRows($pdo, $table('eav_attribute_option_value'), conditions($optionIds, ['option_id']), $output . '/eav_attribute_option_value.jsonl');
        $mediaIds = array_unique(array_column(readJsonLines($output . '/catalog_product_entity_media_gallery_value_to_entity.jsonl'), 'value_id'));
        $manifest['tables']['catalog_product_entity_media_gallery'] = exportRows($pdo, $table('catalog_product_entity_media_gallery'), conditions($mediaIds, ['value_id']), $output . '/catalog_product_entity_media_gallery.jsonl');
        $pdo->rollBack();
        file_put_contents($output . '/manifest.json', json_encode($manifest, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . PHP_EOL);
    } catch (Throwable $exception) {
        if ($pdo->inTransaction()) {
            $pdo->rollBack();
        }
        throw $exception;
    }
}

$options = getopt('', ['root:', 'request:', 'output-dir:']);
if (!isset($options['root'], $options['request'], $options['output-dir'])) {
    fwrite(STDERR, "Required: --root --request --output-dir\n");
    exit(2);
}
$log = $options['output-dir'] . '.log';
try {
    snapshot($options);
    file_put_contents($log, gmdate('c') . " Read-only snapshot completed\n", FILE_APPEND);
    exit(0);
} catch (Throwable $exception) {
    file_put_contents($log, gmdate('c') . ' Snapshot failed: ' . get_class($exception) . "; no catalog writes performed. Incomplete output is not usable.\n", FILE_APPEND);
    exit(1);
}
