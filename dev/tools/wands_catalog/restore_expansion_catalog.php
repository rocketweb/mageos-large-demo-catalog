<?php
declare(strict_types=1);
require __DIR__ . '/expansion_catalog_journal.php';

function restoreExpansionCatalog(): void
{
    $a = getopt('', ['root:', 'inverse:', 'inverse-sha256:', 'after-store-snapshot:', 'after-store-sha256:', 'output:']);
    $root = realpath($a['root'] ?? ''); $parent = realpath(dirname($a['output'] ?? ''));
    if (!in_array($root, ['/Users/matt/code/mageos-latest', '/var/www/html'], true)
        || !$parent || !str_starts_with($parent, $root . '/var/') || (fileperms($parent) & 0077)
        || file_exists($a['output'])) { throw new RuntimeException('Exact existing root and fresh private receipt directory required'); }
    foreach (['inverse', 'after-store-snapshot'] as $name) {
        $path = realpath($a[$name] ?? '');
        if (!$path || !str_starts_with($path, $root . '/var/') || (fileperms($path) & 0077)
            || hash_file('sha256', $path) !== $a[$name === 'inverse' ? 'inverse-sha256' : 'after-store-sha256']) {
            throw new RuntimeException('Private compensation evidence changed');
        }
    }
    $receipt = json_decode(file_get_contents($a['inverse'] . '.json'), true, 512, JSON_THROW_ON_ERROR);
    $beforePath = realpath($receipt['before']); $afterPath = realpath($receipt['after']);
    foreach ([$beforePath, $afterPath] as $path) {
        if (!$path || !str_starts_with($path, $root . '/var/') || (fileperms($path) & 0077)) { throw new RuntimeException('Untrusted catalog journal path'); }
    }
    if (hash_file('sha256', $beforePath . '/manifest.json') !== $receipt['before_sha256']
        || hash_file('sha256', $afterPath . '/manifest.json') !== $receipt['after_sha256']
        || $receipt['inverse_sha256'] !== $a['inverse-sha256']) { throw new RuntimeException('Compensation manifest changed'); }
    $before = json_decode(file_get_contents($beforePath . '/manifest.json'), true, 512, JSON_THROW_ON_ERROR);
    $after = json_decode(file_get_contents($afterPath . '/manifest.json'), true, 512, JSON_THROW_ON_ERROR);
    $store = json_decode(file_get_contents($a['after-store-snapshot']), true, 512, JSON_THROW_ON_ERROR);
    $env = require $root . '/app/etc/env.php'; $c = $env['db']['connection']['default']; $prefix = $env['db']['table_prefix'] ?? '';
    foreach ([$before, $after] as $snapshot) {
        if ($snapshot['root'] !== $root || $snapshot['prefix'] !== $prefix || $snapshot['database'] !== $c['dbname']
            || $snapshot['env_sha256'] !== hash_file('sha256', $root . '/app/etc/env.php')
            || $snapshot['tool_sha256'] !== hash_file('sha256', __DIR__ . '/expansion_catalog_journal.php')) {
            throw new RuntimeException('Compensation destination or implementation changed');
        }
    }
    if ($store['root'] !== $root || $store['schema'] !== 2 || $store['database_writes'] !== false) { throw new RuntimeException('Wrong after-store evidence'); }
    if (empty($before['protected']) || $before['protected'] !== $after['protected']) {
        throw new RuntimeException('Protected data changed during import; reconcile dependencies before compensation');
    }
    $dsn = 'mysql:host=' . $c['host'] . ';dbname=' . $c['dbname'] . ';charset=utf8mb4';
    if (!empty($c['port'])) { $dsn .= ';port=' . (int)$c['port']; }
    $db = new PDO($dsn, $c['username'], $c['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $manager = new ExpansionCatalogJournal($db, $prefix); mkdir($a['output'], 0700);
    $db->exec('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE'); $db->beginTransaction();
    try {
        // Protect against new orders or reservations depending on added products.
        // These rows are locked and compared, never updated or restored.
        if ($manager->protectedHashes(true) !== $after['protected']) {
            throw new RuntimeException('Protected data changed; compensation requires reconciliation');
        }
        $current = $manager->capture($a['output'] . '/current');
        if (array_keys($current['tables']) !== array_keys($after['tables'])) { throw new RuntimeException('Catalog schema changed'); }
        foreach ($after['tables'] as $name => $expected) {
            foreach (['rows', 'row_sha256', 'keys', 'columns'] as $key) {
                if ($current['tables'][$name][$key] !== $expected[$key]) { throw new RuntimeException('Later catalog changes detected; no inverse applied'); }
            }
        }
        $stream = gzopen($a['inverse'], 'rb'); $count = 0;
        if (!$stream) { throw new RuntimeException('Cannot read exact inverse'); }
        while (($line = gzgets($stream)) !== false) {
            $op = json_decode($line, true, 512, JSON_THROW_ON_ERROR); $manager->validateOperation($op);
            if (!isset($after['tables'][$op['table']]) || array_keys($op['selector']) !== $after['tables'][$op['table']]['keys']) {
                // JSON canonicalization sorts selector keys, so compare as sets.
                $keys = array_keys($op['selector']); $expected = $after['tables'][$op['table']]['keys'] ?? [];
                sort($keys); sort($expected);
                if ($keys !== $expected || !$keys) { throw new RuntimeException('Inverse is not bound to journal primary keys'); }
            }
            if ($manager->current($op) !== ExpansionCatalogJournal::canonical($op['after'])) { throw new RuntimeException('Exact after row changed'); }
            ++$count;
        }
        gzclose($stream);
        if ($count !== $receipt['operations']) { throw new RuntimeException('Inverse operation count changed'); }
        $db->exec('SET FOREIGN_KEY_CHECKS=0'); $stream = gzopen($a['inverse'], 'rb');
        while (($line = gzgets($stream)) !== false) { $manager->compensate(json_decode($line, true, 512, JSON_THROW_ON_ERROR)); }
        gzclose($stream);
        $restored = $manager->capture($a['output'] . '/restored');
        foreach ($before['tables'] as $name => $expected) {
            if ($restored['tables'][$name]['row_sha256'] !== $expected['row_sha256']
                || $restored['tables'][$name]['rows'] !== $expected['rows']) { throw new RuntimeException('Compensation did not restore original catalog rows'); }
        }
        $result = ['root' => $root, 'inverse_sha256' => $a['inverse-sha256'], 'restored_rows' => $count,
            'protected_data_written' => false, 'original_catalog_rows_verified' => true,
            'state' => 'catalog_rows_restored; module_and_indexes_require_restoration'];
        file_put_contents($a['output'] . '/receipt.json', json_encode($result, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n");
        chmod($a['output'] . '/receipt.json', 0600); $db->commit(); $db->exec('SET FOREIGN_KEY_CHECKS=1');
        file_put_contents($a['output'] . '/COMMITTED', hash_file('sha256', $a['output'] . '/receipt.json'));
        echo json_encode($result, JSON_THROW_ON_ERROR) . "\n";
    } catch (Throwable $e) {
        if ($db->inTransaction()) { $db->rollBack(); }
        $db->exec('SET FOREIGN_KEY_CHECKS=1'); throw $e;
    }
}

if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) { restoreExpansionCatalog(); }
