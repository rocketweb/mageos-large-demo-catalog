<?php
declare(strict_types=1);
require __DIR__.'/bulk_structure.php';

$args = getopt('', ['root:', 'structure:', 'csv:', 'output:']);
try {
    if (file_exists($args['output'])) {
        throw new RuntimeException('Choose a fresh axis receipt');
    }
    $structure = json_decode(file_get_contents($args['structure']), true, 512, JSON_THROW_ON_ERROR);
    if (count($structure['parent_axes']) !== 98 || count($structure['all_skus']) !== 667) {
        throw new RuntimeException('Wrong bulk scope');
    }
    $csv = fopen($args['csv'], 'r');
    $columns = fgetcsv($csv, 0, ',', '"', '');
    $labels = [];
    while (($values = fgetcsv($csv, 0, ',', '"', '')) !== false) {
        $row = array_combine($columns, $values);
        foreach (explode(',', $row['configurable_variation_labels']) as $pair) {
            [$code, $label] = explode('=', $pair, 2);
            $labels[$row['sku']][$code] = $label;
        }
    }
    fclose($csv);
    $environment = require $args['root'].'/app/etc/env.php';
    $db = $environment['db']['connection']['default'];
    $pdo = new PDO('mysql:host='.$db['host'].';dbname='.$db['dbname'].';charset=utf8mb4', $db['username'], $db['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $urls = $pdo->query("SELECT value FROM core_config_data WHERE path='web/secure/base_url'")->fetchAll(PDO::FETCH_COLUMN);
    if (!in_array('https://relevance.comtom.lab/', $urls, true) || !empty($environment['db']['table_prefix'])) {
        throw new RuntimeException('Wrong destination');
    }
    $pdo->beginTransaction();
    $journal = (new BulkCatalogStructure($pdo))->reconcileAxes($structure, $labels);
    $stream = fopen($args['output'], 'x');
    if ($stream === false) {
        throw new RuntimeException('Receipt create failed');
    }
    chmod($args['output'], 0600);
    $data = json_encode(['host' => 'relevance.comtom.lab', 'structure_sha256' => hash_file('sha256', $args['structure']), 'journal' => $journal], JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR).PHP_EOL;
    if (fwrite($stream, $data) !== strlen($data) || !fflush($stream) || !fsync($stream)) {
        throw new RuntimeException('Receipt write failed');
    }
    fclose($stream);
    $pdo->commit();
    file_put_contents($args['output'].'.committed', hash_file('sha256', $args['output']));
    file_put_contents($args['output'].'.log', 'Updated '.count($journal)." axis rows while preserving existing IDs\n");
} catch (Throwable $error) {
    if (isset($pdo) && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    file_put_contents($args['output'].'.log', 'Failed: '.$error->getMessage().PHP_EOL, FILE_APPEND);
    exit(1);
}
