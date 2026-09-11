<?php
declare(strict_types=1);

// Read-only companion to snapshot_catalog.php. No Magento bootstrap or customer data.
$options = getopt('', ['root:', 'request:', 'output:']);
try {
    $request = json_decode(file_get_contents($options['request']), true, 512, JSON_THROW_ON_ERROR);
    if ($request['expected_host'] !== 'relevance.comtom.lab' || count($request['skus']) !== 17) {
        throw new RuntimeException('Wrong pilot scope');
    }
    foreach ($request['skus'] as $sku) {
        if (!preg_match('/^WANDS-[A-Z0-9-]+$/', $sku)) {
            throw new RuntimeException('Invalid SKU');
        }
    }
    $environment = require $options['root'] . '/app/etc/env.php';
    $c = $environment['db']['connection']['default'];
    $prefix = (string)($environment['db']['table_prefix'] ?? '');
    $quote = static function (string $name): string {
        if (!preg_match('/^[a-zA-Z0-9_]+$/', $name)) {
            throw new RuntimeException('Invalid identifier');
        }
        return '`' . $name . '`';
    };
    $table = static fn(string $name): string => $quote($c['dbname']) . '.' . $quote($prefix . $name);
    $dsn = 'mysql:host=' . $c['host'] . ';dbname=' . $c['dbname'] . ';charset=utf8mb4';
    if (!empty($c['port'])) {
        $dsn .= ';port=' . (int)$c['port'];
    }
    $pdo = new PDO($dsn, $c['username'], $c['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    if ($pdo->query('SELECT DATABASE()')->fetchColumn() !== $c['dbname']) {
        throw new RuntimeException('Wrong database');
    }
    $select = static function (string $sql, array $params = []) use ($pdo): array {
        $s = $pdo->prepare($sql);
        $s->execute($params);
        return $s->fetchAll(PDO::FETCH_ASSOC);
    };
    $pdo->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
    $pdo->exec('SET TRANSACTION READ ONLY');
    $pdo->beginTransaction();
    $hosts = $select('SELECT value FROM ' . $table('core_config_data') . ' WHERE path IN (?,?)', ['web/secure/base_url', 'web/unsecure/base_url']);
    if (!in_array('relevance.comtom.lab', array_map(static fn(array $r) => parse_url($r['value'], PHP_URL_HOST), $hosts), true)) {
        throw new RuntimeException('Wrong base URL');
    }
    $slots = implode(',', array_fill(0, count($request['skus']), '?'));
    $entities = $select('SELECT entity_id,sku,type_id FROM ' . $table('catalog_product_entity') . ' WHERE sku IN (' . $slots . ')', $request['skus']);
    if (count($entities) !== 17) {
        throw new RuntimeException('Incomplete pilot entities');
    }
    $ids = array_column($entities, 'entity_id');
    $result = ['version' => 1, 'consistent_read_only' => true, 'host' => 'relevance.comtom.lab',
        'captured_at' => gmdate('c'), 'request_sha256' => hash_file('sha256', $options['request']), 'entities' => $entities];
    $result['relations'] = $select('SELECT r.*,p.sku AS parent_sku,c.sku AS child_sku FROM ' . $table('catalog_product_relation') . ' r JOIN '
        . $table('catalog_product_entity') . ' p ON p.entity_id=r.parent_id JOIN ' . $table('catalog_product_entity')
        . ' c ON c.entity_id=r.child_id WHERE r.parent_id IN (' . $slots . ') OR r.child_id IN (' . $slots . ')', [...$ids, ...$ids]);
    $result['bundle_selections'] = $select('SELECT s.*,p.sku AS parent_sku,c.sku AS child_sku FROM ' . $table('catalog_product_bundle_selection') . ' s JOIN '
        . $table('catalog_product_entity') . ' p ON p.entity_id=s.parent_product_id JOIN ' . $table('catalog_product_entity')
        . ' c ON c.entity_id=s.product_id WHERE s.parent_product_id IN (' . $slots . ') OR s.product_id IN (' . $slots . ')', [...$ids, ...$ids]);
    $result['product_links'] = $select('SELECT l.*,p.sku AS source_sku,c.sku AS target_sku FROM ' . $table('catalog_product_link') . ' l JOIN '
        . $table('catalog_product_entity') . ' p ON p.entity_id=l.product_id JOIN ' . $table('catalog_product_entity')
        . ' c ON c.entity_id=l.linked_product_id WHERE l.product_id IN (' . $slots . ') OR l.linked_product_id IN (' . $slots . ')', [...$ids, ...$ids]);
    $result['axis_labels'] = $select('SELECT v.*,a.product_id,a.attribute_id FROM ' . $table('catalog_product_super_attribute_label') . ' v JOIN '
        . $table('catalog_product_super_attribute') . ' a ON a.product_super_attribute_id=v.product_super_attribute_id WHERE a.product_id IN (' . $slots . ')', $ids);
    $pricingExists = $select('SELECT TABLE_NAME FROM information_schema.tables WHERE TABLE_SCHEMA=? AND TABLE_NAME=?', [$c['dbname'], $prefix . 'catalog_product_super_attribute_pricing']);
    $result['axis_pricing_table_present'] = (bool)$pricingExists;
    $result['axis_prices'] = $pricingExists ? $select('SELECT v.* FROM ' . $table('catalog_product_super_attribute_pricing') . ' v JOIN '
        . $table('catalog_product_super_attribute') . ' a ON a.product_super_attribute_id=v.product_super_attribute_id WHERE a.product_id IN (' . $slots . ')', $ids) : [];
    $result['url_rewrites'] = $select('SELECT * FROM ' . $table('url_rewrite') . ' WHERE entity_type=? AND entity_id IN (' . $slots . ')', ['product', ...$ids]);
    $result['piece_option_consumers'] = $select('SELECT v.value AS option_id,v.store_id,COUNT(*) AS rows_count,COUNT(DISTINCT v.entity_id) AS product_count FROM '
        . $table('catalog_product_entity_int') . ' v JOIN ' . $table('eav_attribute') . ' a ON a.attribute_id=v.attribute_id JOIN '
        . $table('eav_entity_type') . ' t ON t.entity_type_id=a.entity_type_id WHERE t.entity_type_code=? AND a.attribute_code=? GROUP BY v.value,v.store_id', ['catalog_product', 'wands_piece_count']);
    $exists = $select('SELECT TABLE_NAME FROM information_schema.tables WHERE TABLE_SCHEMA=? AND TABLE_NAME=?', [$c['dbname'], $prefix . 'inventory_reservation']);
    $result['inventory_reservation_table_present'] = (bool)$exists;
    $result['reservation_totals'] = $exists ? $select('SELECT sku,stock_id,COUNT(*) AS row_count,SUM(quantity) AS quantity FROM ' . $table('inventory_reservation') . ' WHERE sku IN (' . $slots . ') GROUP BY sku,stock_id', $request['skus']) : [];
    $pdo->rollBack();
    $stream = fopen($options['output'], 'x');
    if ($stream === false) {
        throw new RuntimeException('Choose a fresh output');
    }
    chmod($options['output'], 0600);
    fwrite($stream, json_encode($result, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . PHP_EOL);
    fclose($stream);
    file_put_contents($options['output'] . '.log', gmdate('c') . " Read-only dependency snapshot completed\n");
} catch (Throwable $error) {
    if (isset($pdo) && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    // Never put exception messages or connection details in logs.
    file_put_contents(($options['output'] ?? sys_get_temp_dir() . '/wands-dependency-snapshot') . '.log', gmdate('c') . ' Failed: ' . get_class($error) . "; no catalog writes\n", FILE_APPEND);
    exit(1);
}
