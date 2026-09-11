<?php
declare(strict_types=1);
require __DIR__.'/bulk_structure.php';

$args = getopt('', ['root:', 'batch:', 'action:', 'output:', 'preflight:', 'snapshot:']);
ini_set('display_errors', '0');
ini_set('log_errors', '1');
ini_set('error_log', ($args['output'] ?? sys_get_temp_dir().'/wands-bulk-structure').'.php.log');
try {
    $action = $args['action'] ?? 'inspect';
    if (!in_array($action, ['inspect', 'apply', 'rollback'], true) || file_exists($args['output'])) {
        throw new RuntimeException('Choose a supported action and fresh receipt');
    }
    $structurePath = $args['batch'].'/structure.json';
    $structure = json_decode(file_get_contents($structurePath), true, 512, JSON_THROW_ON_ERROR);
    if (count($structure['all_skus']) !== 667 || count(array_unique($structure['all_skus'])) !== 667 || count($structure['conversions']) !== 5 || count($structure['retired_skus']) !== 64) {
        throw new RuntimeException('Wrong bulk catalog scope');
    }
    $environment = require $args['root'].'/app/etc/env.php';
    $db = $environment['db']['connection']['default'];
    if (!empty($environment['db']['table_prefix'])) {
        throw new RuntimeException('This demo adapter expects unprefixed tables');
    }
    $pdo = new PDO('mysql:host='.$db['host'].';dbname='.$db['dbname'].';charset=utf8mb4', $db['username'], $db['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $urls = $pdo->query("SELECT value FROM core_config_data WHERE path='web/secure/base_url'")->fetchAll(PDO::FETCH_COLUMN);
    if (!in_array('https://relevance.comtom.lab/', $urls, true)) {
        throw new RuntimeException('Wrong demo database');
    }
    $manager = new BulkCatalogStructure($pdo);
    $pdo->exec('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE');
    if ($action === 'inspect') {
        $pdo->exec('SET TRANSACTION READ ONLY');
    }
    $pdo->beginTransaction();
    $result = ['action' => $action, 'host' => 'relevance.comtom.lab', 'database' => $db['dbname'],
        'created_at' => gmdate('c'), 'structure_sha256' => hash_file('sha256', $structurePath),
        'adapter_sha256' => hash_file('sha256', __DIR__.'/bulk_structure.php')];
    if ($action === 'inspect') {
        $result['preflight'] = $manager->inspect($structure);
        $pdo->rollBack();
    } else {
        $previous = json_decode(file_get_contents($args['preflight']), true, 512, JSON_THROW_ON_ERROR);
        if ($previous['structure_sha256'] !== $result['structure_sha256'] || $previous['adapter_sha256'] !== $result['adapter_sha256'] || $previous['database'] !== $db['dbname']) {
            throw new RuntimeException('Wrong preflight or adapter');
        }
        if ($action === 'apply') {
            $snapshot = json_decode(file_get_contents($args['snapshot'].'/manifest.json'), true, 512, JSON_THROW_ON_ERROR);
            if ($previous['action'] !== 'inspect' || time()-strtotime($previous['created_at']) > 86400 || $snapshot['host'] !== $result['host'] || $snapshot['tables']['catalog_product_entity']['rows'] !== 667 || $snapshot['missing_skus']) {
                throw new RuntimeException('Fresh exact preflight and backup required');
            }
            foreach ($snapshot['tables'] as $table => $metadata) {
                if (hash_file('sha256', $args['snapshot'].'/'.$table.'.jsonl') !== $metadata['sha256']) {
                    throw new RuntimeException('Backup changed');
                }
            }
            $result['journal'] = $manager->apply($structure, $previous['preflight']);
        } else {
            $marker = json_decode(file_get_contents($args['preflight'].'.committed'), true, 512, JSON_THROW_ON_ERROR);
            if ($previous['action'] !== 'apply' || $marker['sha256'] !== hash_file('sha256', $args['preflight'])) {
                throw new RuntimeException('Committed structure journal required');
            }
            $manager->rollback($previous['journal']);
            $result['restored_operations'] = count($previous['journal']);
        }
    }
    $stream = fopen($args['output'], 'x');
    if ($stream === false) {
        throw new RuntimeException('Cannot create receipt');
    }
    chmod($args['output'], 0600);
    $encoded = json_encode($result, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR).PHP_EOL;
    if (fwrite($stream, $encoded) !== strlen($encoded) || !fflush($stream) || !fsync($stream)) {
        throw new RuntimeException('Receipt write failed');
    }
    fclose($stream);
    if ($pdo->inTransaction()) {
        $pdo->commit();
        file_put_contents($args['output'].'.committed', json_encode(['sha256' => hash_file('sha256', $args['output'])], JSON_THROW_ON_ERROR));
    }
    file_put_contents($args['output'].'.log', gmdate('c').' '.$action." completed\n");
} catch (Throwable $error) {
    if (isset($pdo) && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    file_put_contents(($args['output'] ?? sys_get_temp_dir().'/wands-bulk-structure').'.log', gmdate('c').' Failed: '.$error->getMessage().PHP_EOL, FILE_APPEND);
    exit(1);
}
