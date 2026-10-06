<?php
declare(strict_types=1);
require __DIR__ . '/validate_qa_catalog.php';
require __DIR__ . '/expansion_catalog_journal.php';

function qaInstall(): array
{
    $a = getopt('', ['root:', 'package:', 'manifest-sha256:', 'run-dir:', 'apply']);
    $root = realpath($a['root'] ?? ''); $run = realpath($a['run-dir'] ?? '');
    $package = realpath($a['package'] ?? '');
    if (!in_array($root, ['/Users/matt/code/mageos-latest', '/var/www/html'], true)
        || !$run || !str_starts_with($run, $root . '/var/') || (fileperms($run) & 0077)
        || !$package || !str_starts_with($package, $run . '/')) {
        throw new RuntimeException('Existing store, private run directory and staged package required');
    }
    $plan = ['root' => $root, 'manifest_sha256' => $a['manifest-sha256'] ?? '',
        'before_products' => 107688, 'after_products' => 107815, 'creates' => 127,
        'updates_to_existing_products' => 0, 'product_deletes' => 0, 'transaction_records_created' => 0];
    if (!isset($a['apply'])) { return $plan + ['state' => 'dry run; no installation actions']; }
    if (file_exists($run . '/apply-started.json')) { throw new RuntimeException('Previous apply attempt requires reconciliation; no blind retries'); }
    $backup = json_decode(file_get_contents($run . '/database-before.sql.gz.json'), true, 512, JSON_THROW_ON_ERROR);
    if ($backup['root'] !== $root || $backup['wands_products'] !== 107688 || !$backup['uncompressed_bytes']
        || $backup['path'] !== $run . '/database-before.sql.gz'
        || hash_file('sha256', $backup['path']) !== $backup['sha256'] || (fileperms($backup['path']) & 0077)
        || time() - strtotime($backup['created_at']) > 14400) {
        throw new RuntimeException('Fresh private destination SQL backup required');
    }
    $before = json_decode(file_get_contents($run . '/catalog-before/manifest.json'), true, 512, JSON_THROW_ON_ERROR);
    if ($before['root'] !== $root || $before['database_writes'] !== false
        || $before['tool_sha256'] !== hash_file('sha256', __DIR__ . '/expansion_catalog_journal.php')) {
        throw new RuntimeException('Destination rollback journal missing or changed');
    }
    $validation = qaValidate();
    if (!$validation['native']['valid'] || $validation['native']['processed_rows'] !== 127) {
        throw new RuntimeException('Native QA validation did not accept all rows');
    }
    $env = require $root . '/app/etc/env.php'; $c = $env['db']['connection']['default'];
    $dsn = 'mysql:host=' . $c['host'] . ';dbname=' . $c['dbname'] . ';charset=utf8mb4';
    if (!empty($c['port'])) { $dsn .= ';port=' . (int)$c['port']; }
    $pdo = new PDO($dsn, $c['username'], $c['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $journal = new ExpansionCatalogJournal($pdo, $env['db']['table_prefix'] ?? '');
    $current = $journal->capture($run . '/immediate-before');
    foreach ($before['tables'] as $table => $info) {
        if ($current['tables'][$table]['rows'] !== $info['rows']
            || $current['tables'][$table]['row_sha256'] !== $info['row_sha256']) {
            throw new RuntimeException('Destination catalog changed since backup: ' . $table);
        }
    }
    if ($before['protected'] !== $current['protected']) { throw new RuntimeException('Protected destination data changed'); }
    foreach (['wands-qa', 'wands-qa-downloads'] as $namespace) {
        if (file_exists($root . '/pub/media/import/' . $namespace)) { throw new RuntimeException('Fixture media namespace collision'); }
    }
    $manifest = json_decode(file_get_contents($package . '/manifest.json'), true, 512, JSON_THROW_ON_ERROR);
    $staged = [];
    foreach ($manifest['files'] as $name => $item) {
        if (!str_starts_with($name, 'media/import/')) { continue; }
        $relative = substr($name, strlen('media/import/'));
        if (!preg_match('#^(wands-qa|wands-qa-downloads)/[a-zA-Z0-9._-]+$#', $relative)) {
            throw new RuntimeException('Unsafe fixture media staging path');
        }
        $target = $root . '/pub/media/import/' . $relative;
        if (!is_dir(dirname($target)) && !mkdir(dirname($target), 0775, true)) { throw new RuntimeException('Cannot create media stage'); }
        if (!copy($package . '/' . $name, $target) || hash_file('sha256', $target) !== $item['sha256']) {
            throw new RuntimeException('Fixture media staging integrity failed');
        }
        $staged[$target] = $item['sha256'];
    }
    $write = static function (string $name, array $value) use ($run): void {
        $file = fopen($run . '/' . $name, 'x');
        if (!$file) { throw new RuntimeException('Fresh receipt required'); }
        chmod($run . '/' . $name, 0600);
        fwrite($file, json_encode($value, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES) . "\n"); fclose($file);
    };
    $write('apply-started.json', $plan + ['started_at' => gmdate('c'), 'staged_files' => $staged,
        'database_backup_sha256' => $backup['sha256'], 'before_journal_sha256' => hash_file('sha256', $run . '/catalog-before/manifest.json')]);
    $om = \Magento\Framework\App\ObjectManager::getInstance();
    try {
        $native = $om->get(\RocketWeb\LabCatalog\Model\Catalog\ProductImporter::class)
            ->execute($package . '/data/products.csv', false, false, true);
        if (($native['errors'] ?? 0) !== 0 || ($native['invalid_rows'] ?? 0) !== 0) { throw new RuntimeException('Native import reported invalid rows'); }
        $types = $pdo->query('SELECT type_id,COUNT(*) AS n FROM ' . ($env['db']['table_prefix'] ?? '')
            . "catalog_product_entity WHERE LEFT(sku,9)='WANDS-QA-' GROUP BY type_id")->fetchAll(PDO::FETCH_KEY_PAIR);
        if (array_map('intval', $types) != $manifest['counts']['types']) { throw new RuntimeException('Installed fixture type counts differ'); }
        $write('import-complete.json', $plan + ['completed_at' => gmdate('c'), 'native' => $native, 'types' => $types,
            'state' => 'imported; runtime and browser acceptance pending']);
        return $plan + ['state' => 'imported; runtime and browser acceptance pending', 'native' => $native];
    } catch (Throwable $e) {
        $write('import-failed.json', $plan + ['message' => $e->getMessage(), 'state' => 'reconcile exact partial import before retry']);
        throw $e;
    } finally {
        $after = $journal->capture($run . '/catalog-after');
        $after += ['root' => $root, 'prefix' => $env['db']['table_prefix'] ?? '', 'database' => $c['dbname'],
            'env_sha256' => hash_file('sha256', $root . '/app/etc/env.php'), 'created_at' => gmdate('c'),
            'tool_sha256' => hash_file('sha256', __DIR__ . '/expansion_catalog_journal.php')];
        file_put_contents($run . '/catalog-after/manifest.json', json_encode($after, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n");
        chmod($run . '/catalog-after/manifest.json', 0600);
        if ($after['protected'] !== $before['protected']) { throw new RuntimeException('Import changed protected data'); }
    }
}

try { echo json_encode(qaInstall(), JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n"; }
catch (Throwable $e) { fwrite(STDERR, 'QA installation failed: ' . $e->getMessage() . "\n"); exit(1); }
