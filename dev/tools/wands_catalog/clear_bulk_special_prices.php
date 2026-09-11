<?php
declare(strict_types=1);

// Native import can cast its empty-value marker to 0 for decimal attributes.
// Clear only explicitly empty special prices from this exact correction packet.
$args = getopt('', ['root:', 'imports:', 'output:', 'apply']);
try {
    if (file_exists($args['output'])) {
        throw new RuntimeException('Choose a fresh receipt');
    }
    $skus = [];
    foreach (['simple-updates.csv', 'parent-content-only.csv'] as $name) {
        $stream = fopen($args['imports'].'/'.$name, 'r');
        $columns = fgetcsv($stream, 0, ',', '"', '');
        while (($values = fgetcsv($stream, 0, ',', '"', '')) !== false) {
            $row = array_combine($columns, $values);
            if (($row['special_price'] ?? '') === '__EMPTY__VALUE__') {
                if (!preg_match('/^WANDS-[A-Z0-9-]+$/', $row['sku'])) {
                    throw new RuntimeException('Unexpected SKU');
                }
                $skus[] = $row['sku'];
            }
        }
        fclose($stream);
    }
    if (!$skus || count($skus) > 603) {
        throw new RuntimeException('Wrong empty-price scope');
    }
    $env = require $args['root'].'/app/etc/env.php';
    $db = $env['db']['connection']['default'];
    $pdo = new PDO('mysql:host='.$db['host'].';dbname='.$db['dbname'].';charset=utf8mb4', $db['username'], $db['password'], [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
    $urls = $pdo->query("SELECT value FROM core_config_data WHERE path='web/secure/base_url'")->fetchAll(PDO::FETCH_COLUMN);
    if (!in_array('https://relevance.comtom.lab/', $urls, true) || !empty($env['db']['table_prefix'])) {
        throw new RuntimeException('Wrong destination');
    }
    $pdo->beginTransaction();
    $statement = $pdo->prepare("SELECT d.* FROM catalog_product_entity_decimal d JOIN catalog_product_entity p ON p.entity_id=d.entity_id JOIN eav_attribute a ON a.attribute_id=d.attribute_id WHERE a.attribute_code='special_price' AND d.store_id=0 AND p.sku IN (".implode(',',array_fill(0,count($skus),'?')).') FOR UPDATE');
    $statement->execute($skus);
    $rows = $statement->fetchAll(PDO::FETCH_ASSOC);
    foreach ($rows as $row) {
        if ($row['value'] !== null && (float)$row['value'] !== 0.0) {
            throw new RuntimeException('Special price differs from failed empty-marker conversion');
        }
    }
    $receipt = ['scope_skus'=>count($skus), 'affected_rows'=>count($rows), 'apply'=>isset($args['apply']), 'before'=>$rows, 'after'=>'absent default-scope special-price values'];
    $stream = fopen($args['output'], 'x');
    chmod($args['output'], 0600);
    $data = json_encode($receipt, JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR).PHP_EOL;
    if (fwrite($stream,$data)!==strlen($data) || !fflush($stream) || !fsync($stream)) {
        throw new RuntimeException('Receipt write failed');
    }
    fclose($stream);
    if (isset($args['apply'])) {
        $delete = $pdo->prepare('DELETE FROM catalog_product_entity_decimal WHERE value_id=? AND store_id=0 AND (value=0 OR value IS NULL)');
        foreach ($rows as $row) {
            $delete->execute([$row['value_id']]);
            if ($delete->rowCount() !== 1) {
                throw new RuntimeException('Price row drift');
            }
        }
        $pdo->commit();
        file_put_contents($args['output'].'.committed',hash_file('sha256',$args['output']));
    } else {
        $pdo->rollBack();
    }
    file_put_contents($args['output'].'.log',json_encode(['affected_rows'=>count($rows),'applied'=>isset($args['apply'])]).PHP_EOL);
} catch (Throwable $error) {
    if (isset($pdo) && $pdo->inTransaction()) { $pdo->rollBack(); }
    file_put_contents($args['output'].'.log',$error->getMessage().PHP_EOL);
    exit(1);
}
