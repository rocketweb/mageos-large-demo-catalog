<?php
declare(strict_types=1);

$args = getopt('', ['root:']);
try {
    $env = require $args['root'].'/app/etc/env.php';
    $db = $env['db']['connection']['default'];
    $pdo = new PDO('mysql:host='.$db['host'].';dbname='.$db['dbname'].';charset=utf8mb4', $db['username'], $db['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $pdo->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
    $pdo->exec('START TRANSACTION READ ONLY');
    $skus = ['WANDS-000056','WANDS-003897','WANDS-017842','WANDS-030335','WANDS-035295'];
    $query = $pdo->prepare('SELECT DISTINCT c.entity_id,c.path FROM catalog_category_entity c INNER JOIN catalog_category_product cp ON cp.category_id=c.entity_id INNER JOIN catalog_product_entity p ON p.entity_id=cp.product_id WHERE p.sku IN (?,?,?,?,?)');
    $query->execute($skus);
    $assigned = $query->fetchAll(PDO::FETCH_ASSOC);
    $ids = [];
    foreach ($assigned as $category) {
        foreach (explode('/', $category['path']) as $id) {
            if (!ctype_digit($id)) {
                throw new RuntimeException('Invalid category path');
            }
            $ids[(int)$id] = (int)$id;
        }
    }
    if (!$ids || count($ids) > 50) {
        throw new RuntimeException('Unexpected category ancestor scope');
    }
    sort($ids);
    $in = implode(',', $ids);
    $rows = ['catalog_category_entity' => $pdo->query('SELECT * FROM catalog_category_entity WHERE entity_id IN ('.$in.') ORDER BY entity_id')->fetchAll(PDO::FETCH_ASSOC)];
    $ddl = [];
    foreach (['varchar','int','text','decimal','datetime'] as $type) {
        $table = 'catalog_category_entity_'.$type;
        $ddl[$table] = $pdo->query('SHOW CREATE TABLE '.$table)->fetch(PDO::FETCH_NUM)[1];
        $rows[$table] = $pdo->query('SELECT * FROM '.$table.' WHERE entity_id IN ('.$in.') ORDER BY value_id')->fetchAll(PDO::FETCH_ASSOC);
    }
    $pdo->rollBack();
    echo json_encode(['captured_at' => gmdate('c'), 'host' => 'relevance.comtom.lab', 'consistent_read_only' => true,
        'collector_version' => 'wands-import-category-capture-v1', 'root_skus' => $skus, 'assigned_categories' => $assigned,
        'ancestor_ids' => $ids, 'ddl' => $ddl, 'rows' => $rows, 'live_writes' => false], JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR).PHP_EOL;
} catch (Throwable $error) {
    fwrite(STDERR, "Read-only category capture failed; no environment values emitted\n");
    exit(1);
}
