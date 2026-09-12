<?php

declare(strict_types=1);

use Magento\Framework\App\Bootstrap;
use Magento\Framework\App\ResourceConnection;

$options = getopt('', ['magento-root:', 'data-dir:', 'log-file:']);
$log = $options['log-file'] ?? __DIR__ . '/preflight.log';

try {
    if (!isset($options['magento-root'], $options['data-dir'])) {
        throw new RuntimeException('Explicit --magento-root and --data-dir paths are required.');
    }
    $root = realpath($options['magento-root'] ?? '');
    $data = realpath($options['data-dir'] ?? '');
    if (!$root || !$data || !is_file($root . '/app/bootstrap.php')) {
        throw new RuntimeException('Explicit --magento-root and --data-dir paths are required.');
    }
    foreach (['counts.json', '1-simple.csv', '2-configurable.csv', '3-bundle.csv'] as $file) {
        if (!is_file($data . '/' . $file) || !is_readable($data . '/' . $file)) {
            throw new RuntimeException('Missing or unreadable catalog input: ' . $file);
        }
    }
    $counts = json_decode(file_get_contents($data . '/counts.json'), true, 512, JSON_THROW_ON_ERROR);
    $skus = [];
    foreach (['1-simple.csv', '2-configurable.csv', '3-bundle.csv'] as $file) {
        $stream = fopen($data . '/' . $file, 'r');
        if (!$stream) {
            throw new RuntimeException('Missing catalog CSV: ' . $file);
        }
        $header = fgetcsv($stream, null, ',', '"', '');
        if (!$header || $header[0] !== 'sku') {
            throw new RuntimeException('Unexpected CSV header');
        }
        while (($row = fgetcsv($stream, null, ',', '"', '')) !== false) {
            if (!$row[0] || isset($skus[$row[0]])) {
                throw new RuntimeException('Empty or duplicate SKU');
            }
            $skus[$row[0]] = true;
        }
        fclose($stream);
    }
    if (count($skus) !== $counts['products']) {
        throw new RuntimeException('CSV count does not match verified manifest inventory');
    }
    require $root . '/app/bootstrap.php';
    $bootstrap = Bootstrap::create(BP, $_SERVER);
    $resource = $bootstrap->getObjectManager()->get(ResourceConnection::class);
    $connection = $resource->getConnection();
    $products = (int)$connection->fetchOne(
        $connection->select()->from($resource->getTableName('catalog_product_entity'), ['COUNT(*)'])
    );
    $websites = (int)$connection->fetchOne(
        $connection->select()->from($resource->getTableName('store_website'), ['COUNT(*)'])->where('code = ?', 'wands')
    );
    $stores = (int)$connection->fetchOne(
        $connection->select()->from($resource->getTableName('store'), ['COUNT(*)'])->where('code = ?', 'wands')
    );
    $groups = (int)$connection->fetchOne(
        $connection->select()->from($resource->getTableName('store_group'), ['COUNT(*)'])->where('code = ?', 'wands_catalog')
    );
    $result = [
        'stage' => 'before module installation and provisioning',
        'existing_products' => $products,
        'existing_wands_websites' => $websites,
        'existing_wands_stores' => $stores,
        'existing_wands_store_groups' => $groups,
        'proposed_product_inserts' => count($skus),
        'proposed_media_roles' => $counts['media_roles'],
        'database_writes' => false,
        'requires_empty_baseline_backup' => true,
    ];
    file_put_contents($log, json_encode($result, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . PHP_EOL, FILE_APPEND);
    if ($products !== 0 || $websites !== 0 || $stores !== 0 || $groups !== 0) {
        throw new RuntimeException('Fresh-install preflight refused: destination is not an empty dedicated lab.');
    }
    file_put_contents($log, "Preflight passed. No provisioning or import was performed.\n", FILE_APPEND);
    exit(0);
} catch (Throwable $exception) {
    file_put_contents($log, 'FAILED: ' . $exception->getMessage() . PHP_EOL, FILE_APPEND);
    exit(1);
}
