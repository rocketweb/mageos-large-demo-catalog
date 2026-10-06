<?php
declare(strict_types=1);

/** Validate a pinned QA candidate on an existing store, then roll back import staging. */
function qaFingerprint($db, $resource, array $names): array
{
    $result = [];
    foreach ($names as $name) {
        $table = $db->quoteIdentifier($resource->getTableName($name));
        $columns = array_keys($db->describeTable($resource->getTableName($name)));
        $order = implode(',', array_map($db->quoteIdentifier(...), $columns));
        $statement = $db->query('SELECT * FROM ' . $table . ' ORDER BY ' . $order);
        $hash = hash_init('sha256'); $count = 0;
        while ($row = $statement->fetch(PDO::FETCH_ASSOC)) {
            hash_update($hash, json_encode($row, JSON_THROW_ON_ERROR) . "\n"); ++$count;
        }
        $result[$name] = ['rows' => $count, 'sha256' => hash_final($hash)];
    }
    return $result;
}

function qaValidate(): array
{
    $args = getopt('', ['root:', 'package:', 'manifest-sha256:']);
    $root = realpath($args['root'] ?? '');
    $package = realpath($args['package'] ?? '');
    $pin = $args['manifest-sha256'] ?? '';
    if (!in_array($root, ['/Users/matt/code/mageos-latest', '/var/www/html'], true)
        || !$package || !preg_match('/^[a-f0-9]{64}$/', $pin)
        || is_link($package . '/manifest.json') || hash_file('sha256', $package . '/manifest.json') !== $pin) {
        throw new RuntimeException('An existing store and pinned QA package are required');
    }
    $manifest = json_decode(file_get_contents($package . '/manifest.json'), true, 512, JSON_THROW_ON_ERROR);
    if (($manifest['schema'] ?? 0) !== 1 || ($manifest['recipe'] ?? '') !== 'wands-qa-2026.10.06-v1'
        || ($manifest['counts']['products'] ?? 0) !== 127) {
        throw new RuntimeException('Unexpected QA recipe');
    }
    $actual = [];
    foreach (new RecursiveIteratorIterator(new RecursiveDirectoryIterator($package, FilesystemIterator::SKIP_DOTS)) as $file) {
        if (!$file->isFile()) { continue; }
        $name = substr($file->getPathname(), strlen($package) + 1); $actual[] = $name;
        if ($name === 'manifest.json') { continue; }
        $item = $manifest['files'][$name] ?? null;
        if (!$item || $file->isLink() || !str_starts_with($file->getRealPath(), $package . '/')
            || $file->getSize() !== $item['bytes'] || hash_file('sha256', $file->getPathname()) !== $item['sha256']) {
            throw new RuntimeException('QA package inventory or file integrity differs');
        }
    }
    $expected = [...array_keys($manifest['files']), 'manifest.json']; sort($actual); sort($expected);
    if ($actual !== $expected) { throw new RuntimeException('QA package files differ'); }
    $fixtures = json_decode(file_get_contents($package . '/fixtures.json'), true, 512, JSON_THROW_ON_ERROR);
    $skus = array_column(array_column($fixtures, 'product'), 'sku');
    if (count($skus) !== 127 || count(array_unique($skus)) !== 127) { throw new RuntimeException('Invalid fixture SKU inventory'); }
    foreach ($skus as $sku) {
        if (!str_starts_with($sku, 'WANDS-QA-')) { throw new RuntimeException('Non-QA SKU refused'); }
    }
    $csv = fopen($package . '/data/products.csv', 'r');
    $header = fgetcsv($csv, null, ',', '"', ''); $rows = [];
    while (($values = fgetcsv($csv, null, ',', '"', '')) !== false) {
        if (count($values) !== count($header)) { throw new RuntimeException('Invalid CSV row'); }
        $rows[] = array_combine($header, $values);
    }
    fclose($csv);
    if (count($rows) !== 127) { throw new RuntimeException('CSV fixture count differs'); }
    foreach ($rows as $i => $row) {
        $canonical = $fixtures[$i]['product'];
        $nonempty = static fn(array $r): array => array_filter($r, static fn($value): bool => $value !== '');
        if ($nonempty($row) != $nonempty($canonical) || $row['product_websites'] !== 'wands') {
            throw new RuntimeException('CSV differs from QA definitions or website scope');
        }
    }

    require $root . '/app/bootstrap.php';
    $bootstrap = \Magento\Framework\App\Bootstrap::create($root, $_SERVER);
    $om = $bootstrap->getObjectManager();
    $resource = $om->get(\Magento\Framework\App\ResourceConnection::class);
    $db = $resource->getConnection();
    $products = $db->quoteIdentifier($resource->getTableName('catalog_product_entity'));
    $collision = (int)$db->fetchOne('SELECT COUNT(*) FROM ' . $products . " WHERE LEFT(sku,9)='WANDS-QA-'");
    if ($collision !== 0) { throw new RuntimeException('Existing QA products found; append-only candidate refused'); }
    $website = (int)$db->fetchOne('SELECT website_id FROM ' . $db->quoteIdentifier($resource->getTableName('store_website')) . " WHERE code='wands'");
    if (!$website) { throw new RuntimeException('WANDS website missing'); }
    $memberships = $db->quoteIdentifier($resource->getTableName('catalog_product_website'));
    $count = (int)$db->fetchOne('SELECT COUNT(*) FROM ' . $memberships . ' WHERE website_id=?', [$website]);
    if ($count !== 107688) { throw new RuntimeException('Expected completed WANDS baseline differs'); }
    $protected = ['importexport_importdata', 'import_history', 'catalog_product_entity', 'catalog_product_website',
        'catalog_product_entity_int', 'catalog_product_entity_varchar', 'catalog_product_entity_decimal',
        'catalog_product_entity_text', 'catalog_product_entity_datetime', 'catalog_product_entity_tier_price',
        'catalog_product_option', 'catalog_product_option_type_value', 'catalog_product_super_link',
        'catalog_product_link', 'catalog_product_bundle_option', 'catalog_product_bundle_selection',
        'downloadable_link', 'downloadable_sample', 'catalog_category_entity', 'catalog_category_entity_varchar',
        'catalog_category_product', 'eav_attribute_option', 'eav_attribute_option_value',
        'cataloginventory_stock_item', 'inventory_source_item', 'inventory_reservation',
        'core_config_data', 'customer_entity', 'sales_order', 'sales_order_item', 'quote', 'quote_item'];
    $before = qaFingerprint($db, $resource, $protected);
    $stage = $root . '/var/wands-qa-validation-' . bin2hex(random_bytes(8));
    if (!mkdir($stage, 0700) || !copy($package . '/data/products.csv', $stage . '/products.csv')) {
        throw new RuntimeException('Cannot stage validation CSV');
    }
    chmod($stage . '/products.csv', 0600);
    $result = []; $failure = null;
    try {
        $state = $om->get(\Magento\Framework\App\State::class);
        $state->emulateAreaCode(\Magento\Framework\App\Area::AREA_ADMINHTML, function () use ($om, $root, $stage, $db, &$result): void {
            $directory = $om->get(\Magento\Framework\Filesystem::class)->getDirectoryRead(\Magento\Framework\App\Filesystem\DirectoryList::ROOT);
            $import = $om->get(\Magento\ImportExport\Model\ImportFactory::class)->create();
            $import->setData([
                'entity' => 'catalog_product', 'behavior' => \Magento\ImportExport\Model\Import::BEHAVIOR_APPEND,
                \Magento\ImportExport\Model\Import::FIELD_NAME_VALIDATION_STRATEGY => 'validation-stop-on-errors',
                \Magento\ImportExport\Model\Import::FIELD_NAME_ALLOWED_ERROR_COUNT => 100,
                \Magento\ImportExport\Model\Import::FIELD_FIELD_SEPARATOR => ',',
                \Magento\ImportExport\Model\Import::FIELD_FIELD_MULTIPLE_VALUE_SEPARATOR => ',',
                \Magento\ImportExport\Model\Import::FIELD_EMPTY_ATTRIBUTE_VALUE_CONSTANT => \Magento\ImportExport\Model\Import::DEFAULT_EMPTY_ATTRIBUTE_VALUE_CONSTANT,
                \Magento\ImportExport\Model\Import::FIELDS_ENCLOSURE => 1,
                \Magento\ImportExport\Model\Import::FIELD_NAME_IMG_FILE_DIR => 'pub/media/import',
                'images_base_directory' => $directory,
            ]);
            $source = $om->get(\Magento\ImportExport\Model\Import\Source\CsvFactory::class)->create([
                'file' => $stage . '/products.csv', 'directory' => $directory,
            ]);
            if ($db->getTransactionLevel() !== 0) { throw new RuntimeException('Unexpected database transaction'); }
            $db->beginTransaction();
            try {
                $valid = $import->validateSource($source);
                $errors = [];
                foreach ($import->getErrorAggregator()->getAllErrors() as $error) {
                    $errors[] = ['row' => $error->getRowNumber(), 'message' => $error->getErrorMessage()];
                }
                $result = ['valid' => $valid && !$errors, 'processed_rows' => $import->getProcessedRowsCount(),
                    'invalid_rows' => $import->getErrorAggregator()->getInvalidRowsCount(),
                    'errors' => $import->getErrorAggregator()->getErrorsCount(), 'error_messages' => $errors];
                if ($db->getTransactionLevel() !== 1) { throw new RuntimeException('Validation changed transaction boundary'); }
            } finally {
                while ($db->getTransactionLevel() > 0) { $db->rollBack(); }
            }
        });
    } catch (Throwable $exception) {
        $failure = $exception;
    } finally {
        unlink($stage . '/products.csv'); rmdir($stage);
    }
    $after = qaFingerprint($db, $resource, $protected);
    if ($before !== $after) { throw new RuntimeException('Protected database state changed during validation'); }
    if ($failure) { throw $failure; }
    return ['schema' => 1, 'verified_at' => gmdate('c'), 'mode' => 'native validation only; staging rolled back',
        'target_root' => $root, 'manifest_sha256' => $pin, 'before_wands_products' => $count,
        'products_proposed' => 127, 'products_imported' => 0, 'protected_tables_unchanged' => true,
        'protected_tables' => $after, 'native' => $result];
}

if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) {
try {
    $report = qaValidate();
    echo json_encode($report, JSON_THROW_ON_ERROR | JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    exit($report['native']['valid'] && $report['native']['processed_rows'] === 127 ? 0 : 1);
} catch (Throwable $exception) {
    fwrite(STDERR, 'QA validation failed: ' . $exception->getMessage() . "\n"); exit(1);
}
}
