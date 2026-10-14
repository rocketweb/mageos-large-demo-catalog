<?php

declare(strict_types=1);

/** Private runtime bridge. Requests arrive on stdin; credentials never leave this process. */
class CatalogInstallerFailure extends RuntimeException {}

function installerFail(string $message): never
{
    throw new CatalogInstallerFailure($message);
}

function installerTable(string $name): string
{
    return $GLOBALS['installerResource']->getTableName($name);
}

function installerRows(string $name): array
{
    $db = $GLOBALS['installerDb'];
    return $db->fetchAll($db->select()->from(installerTable($name)));
}

function installerInspect(): array
{
    $db = $GLOBALS['installerDb'];
    $root = $GLOBALS['installerRoot'];
    $config = $GLOBALS['installerConfig'];
    $products = installerRows('catalog_product_entity');
    $categories = installerRows('catalog_category_entity');
    $groups = installerRows('store_group');
    $roots = [1, 2];
    foreach ($groups as $group) {
        if ((int)$group['root_category_id'] > 0) {
            $roots[] = (int)$group['root_category_id'];
        }
    }
    $roots = array_values(array_unique($roots));
    sort($roots);
    $websites = array_column(installerRows('store_website'), 'code');
    $stores = array_column(installerRows('store'), 'code');
    $groupCodes = array_column($groups, 'code');
    $websiteRows = array_column(installerRows('store_website'), null, 'code');
    $storeRows = array_column(installerRows('store'), null, 'code');
    $groupRows = array_column($groups, null, 'code');
    $collision = isset($websiteRows['wands']) || isset($storeRows['wands']) || isset($groupRows['wands_catalog']);
    $validStructure = !$collision;
    if (isset($websiteRows['wands'], $storeRows['wands'], $groupRows['wands_catalog'])) {
        $website = $websiteRows['wands'];
        $group = $groupRows['wands_catalog'];
        $store = $storeRows['wands'];
        $urlKey = $db->fetchOne($db->select()->from(['v' => installerTable('catalog_category_entity_varchar')], ['value'])
            ->join(['a' => installerTable('eav_attribute')], 'a.attribute_id=v.attribute_id', [])
            ->where('v.entity_id = ?', $group['root_category_id'])->where('v.store_id = 0')->where('a.attribute_code = ?', 'url_key'));
        $validStructure = (int)$group['website_id'] === (int)$website['website_id']
            && (int)$store['website_id'] === (int)$website['website_id'] && (int)$store['group_id'] === (int)$group['group_id']
            && $urlKey === 'wands-catalog';
    }
    $hash = hash_init('sha256');
    $tables = ['catalog_product_entity', 'catalog_category_entity', 'catalog_product_website',
        'catalog_category_product', 'catalog_product_super_link', 'catalog_product_super_attribute',
        'catalog_product_super_attribute_label', 'catalog_product_relation', 'catalog_product_link',
        'catalog_product_link_attribute_int', 'catalog_product_link_attribute_decimal',
        'catalog_product_link_attribute_varchar', 'catalog_product_bundle_option',
        'catalog_product_bundle_option_value', 'catalog_product_bundle_selection',
        'catalog_product_bundle_selection_price', 'catalog_product_option', 'catalog_product_option_title',
        'catalog_product_option_price', 'catalog_product_option_type_value', 'catalog_product_option_type_title',
        'catalog_product_option_type_price', 'catalog_product_entity_media_gallery',
        'catalog_product_entity_media_gallery_value', 'catalog_product_entity_media_gallery_value_to_entity',
        'downloadable_link', 'downloadable_link_title', 'downloadable_link_price',
        'downloadable_sample', 'downloadable_sample_title', 'eav_attribute', 'eav_attribute_option',
        'eav_attribute_option_value', 'catalog_eav_attribute', 'store_website', 'store_group', 'store'];
    foreach (['product', 'category'] as $entity) {
        foreach (['varchar', 'int', 'decimal', 'text', 'datetime'] as $type) {
            $tables[] = 'catalog_' . $entity . '_entity_' . $type;
        }
    }
    foreach ($tables as $name) {
        $table = installerTable($name);
        if (!$db->isTableExists($table)) {
            continue;
        }
        $description = $db->describeTable($table);
        $columns = array_values(array_diff(array_keys($description), ['created_at', 'updated_at']));
        $primary = [];
        foreach ($description as $column => $metadata) {
            if ($metadata['PRIMARY']) {
                $primary[] = $column;
            }
        }
        $query = $db->select()->from($table, $columns)->order($primary ?: $columns);
        hash_update($hash, $name . "\n");
        $statement = $db->query($query);
        while ($row = $statement->fetch(PDO::FETCH_ASSOC)) {
            hash_update($hash, json_encode($row, JSON_THROW_ON_ERROR) . "\n");
        }
    }
    $database = $config['db']['connection']['default'];
    $testRecords = [];
    foreach (['customers' => 'customer_entity', 'orders' => 'sales_order', 'quotes' => 'quote'] as $key => $table) {
        $testRecords[$key] = (int)$db->fetchOne($db->select()->from(installerTable($table), ['COUNT(*)']));
    }
    $reservations = $db->isTableExists(installerTable('inventory_reservation'))
        ? (int)$db->fetchOne($db->select()->from(installerTable('inventory_reservation'), ['COUNT(*)'])) : 0;
    $identity = hash('sha256', json_encode([$root, $database['host'], $database['dbname'],
        $config['db']['table_prefix'] ?? '', $config['crypt']['key'] ?? ''], JSON_THROW_ON_ERROR));
    $installed = json_decode(file_get_contents($root . '/vendor/composer/installed.json'), true, 512, JSON_THROW_ON_ERROR);
    $packages = $installed['packages'] ?? $installed;
    $edition = 'unknown';
    $version = 'unknown';
    foreach ($packages as $package) {
        if ($package['name'] === 'mage-os/product-community-edition') {
            $edition = 'mage-os';
            $version = $package['version'];
            break;
        }
        if ($package['name'] === 'magento/product-community-edition') {
            $edition = 'magento';
            $version = $package['version'];
        }
    }
    return ['identity' => $identity, 'database' => $database['dbname'], 'websites' => $websites,
        'database_bytes' => (int)$db->fetchOne('SELECT COALESCE(SUM(data_length + index_length), 0) FROM information_schema.tables WHERE table_schema = ?', [$database['dbname']]),
        'reservations' => $reservations, 'test_records' => $testRecords,
        'edition' => $edition, 'version' => ltrim($version, 'v'), 'php' => PHP_VERSION,
        'mode' => $GLOBALS['installerManager']->get(\Magento\Framework\App\State::class)->getMode(),
        'products' => count($products), 'categories' => count($categories),
        'catalog_products' => count(array_filter($products, static fn(array $row): bool => strncasecmp($row['sku'], 'WANDS-', 6) === 0)),
        'deletable_categories' => count(array_filter($categories, static fn(array $row): bool => !in_array((int)$row['entity_id'], $roots, true))),
        'retained_category_roots' => $roots,
        'catalog_sha256' => hash_final($hash),
        'maintenance' => is_file($root . '/var/.maintenance.flag'),
        'remote_storage' => ($config['remote_storage']['driver'] ?? 'file') !== 'file',
        'running_cron' => (int)$db->fetchOne($db->select()->from(installerTable('cron_schedule'), ['COUNT(*)'])->where('status = ?', 'running')),
        'wands_collision' => $collision, 'wands_structure_valid' => $validStructure];
}

function installerPrivatePath(string $path): string
{
    $parent = realpath(dirname($path));
    $state = realpath($GLOBALS['installerRoot'] . '/var/wands-installer');
    if (!$parent || !$state || !str_starts_with($parent . '/', $state . '/') || is_link($path)) {
        installerFail('Database backup paths must be in the protected installer state directory.');
    }
    return $parent . '/' . basename($path);
}

function installerDatabaseTool(array $request, bool $restore): array
{
    $root = $GLOBALS['installerRoot'];
    $db = $GLOBALS['installerConfig']['db']['connection']['default'];
    $path = installerPrivatePath($request[$restore ? 'source' : 'destination']);
    if (!$restore && file_exists($path)) {
        installerFail('Database backup destination already exists.');
    }
    if ($restore && (!is_file($path) || filesize($path) < 100)) {
        installerFail('Database restore source is missing or empty.');
    }
    $binary = $request['binary'];
    if (!is_string($binary) || $binary === '' || preg_match('/[\x00-\x20]/', $binary)) {
        installerFail('Use a single database executable path, without shell arguments.');
    }
    if (!preg_match('/^[a-zA-Z0-9_]+$/', (string)$db['dbname'])) {
        installerFail('Database transport requires a database name containing letters, digits or underscores.');
    }
    $quote = static fn(string $value): string => '"' . str_replace(["\\", '"', "\n", "\r"], ["\\\\", '\\"', '\\n', '\\r'], $value) . '"';
    $host = (string)$db['host'];
    $port = $db['port'] ?? null;
    if (preg_match('/^([^:]+):(\d+)$/', $host, $match)) {
        $host = $match[1];
        $port = $match[2];
    }
    $options = ['host' => $host, 'user' => (string)$db['username'], 'password' => (string)$db['password']];
    if ($port) {
        $options['port'] = (string)$port;
    }
    if (!empty($db['unix_socket'])) {
        $options['socket'] = (string)$db['unix_socket'];
    }
    $credentials = tempnam(dirname($path), '.db-options-');
    chmod($credentials, 0o600);
    $text = "[client]\n";
    foreach ($options as $key => $value) {
        $text .= $key . '=' . $quote($value) . "\n";
    }
    file_put_contents($credentials, $text);
    $errorPath = dirname($path) . '/database-tool.log';
    $outputPath = $restore ? dirname($path) . '/database-restore.log' : $path;
    try {
        $environment = null;
        if (!empty($request['container'])) {
            $container = $request['container'];
            if (!preg_match('/^[a-zA-Z0-9][a-zA-Z0-9_.-]*$/', $container) || !in_array($host, ['localhost', '127.0.0.1'], true)) {
                installerFail('Database container transport accepts only a named local loopback database.');
            }
            $inspection = proc_open(['docker', 'inspect', '--format', '{{json .NetworkSettings.Ports}}', $container],
                [0 => ['file', '/dev/null', 'r'], 1 => ['pipe', 'w'], 2 => ['file', '/dev/null', 'w']], $pipes);
            if (!is_resource($inspection)) {
                installerFail('Database container is unavailable.');
            }
            $bindings = json_decode(stream_get_contents($pipes[1]), true, 512, JSON_THROW_ON_ERROR);
            fclose($pipes[1]);
            if (proc_close($inspection) !== 0) {
                installerFail('Database container port lookup failed.');
            }
            $matched = false;
            foreach ($bindings['3306/tcp'] ?? [] as $entry) {
                $matched = $matched || (string)$entry['HostPort'] === (string)($port ?: 3306);
            }
            if (!$matched) {
                installerFail('Database container port does not match the installation configuration.');
            }
            $command = ['docker', 'exec', '-i', '--env', 'MYSQL_PWD', $container, $binary, '--no-defaults',
                '--host=127.0.0.1', '--user=' . $db['username']];
            $environment = array_merge(getenv(), ['MYSQL_PWD' => $db['password']]);
        } else {
            $command = [$binary, '--defaults-extra-file=' . $credentials];
        }
        if ($restore) {
            $command[] = '--binary-mode=1';
        } else {
            array_push($command, '--single-transaction', '--quick', '--skip-lock-tables', '--no-tablespaces', '--hex-blob', '--routines', '--triggers');
        }
        $command[] = (string)$db['dbname'];
        $process = proc_open($command, [0 => $restore ? ['file', $path, 'r'] : ['file', '/dev/null', 'r'],
            1 => ['file', $outputPath, 'w'], 2 => ['file', $errorPath, 'w']], $pipes, $root, $environment);
        if (!is_resource($process)) {
            installerFail('Could not start the database backup/restore executable.');
        }
        chmod($outputPath, 0o600);
        chmod($errorPath, 0o600);
        if (proc_close($process) !== 0) {
            installerFail('Database backup/restore failed; inspect the protected database-tool.log.');
        }
        if (!$restore && (filesize($path) < 100 || !str_contains(file_get_contents($path, false, null, 0, 4096), 'SQL'))) {
            installerFail('Database dump is empty or does not contain a SQL dump header.');
        }
        return ['database_sha256' => hash_file('sha256', $path), 'database_bytes' => filesize($path)];
    } finally {
        unlink($credentials);
    }
}

function installerReset(array $request): array
{
    $snapshot = installerInspect();
    if (!$snapshot['maintenance'] || $snapshot['running_cron'] || $snapshot['catalog_sha256'] !== $request['expected_fingerprint']
        || $snapshot['identity'] !== $request['identity'] || $snapshot['reservations'] !== $request['expected_reservations']) {
        installerFail('Reset refused: maintenance, stopped jobs and unchanged target are required.');
    }
    $manager = $GLOBALS['installerManager'];
    $root = $GLOBALS['installerRoot'];
    $state = $manager->get(\Magento\Framework\App\State::class);
    $state->emulateAreaCode(\Magento\Framework\App\Area::AREA_ADMINHTML, static function () use ($manager, $root, $snapshot): void {
        // Complete reservation cleanup here, before reintroducing SKUs. Do not enqueue a later deletion.
        $events = $manager->get(\Magento\Framework\Event\Config\Data::class);
        $eventName = 'catalog_product_import_bunch_delete_after';
        $observers = $events->get($eventName, []);
        $previousDisabled = $observers['process_reservations']['disabled'] ?? false;
        $events->merge([$eventName => ['process_reservations' => ['disabled' => true]]]);
        $reservationSkus = $GLOBALS['installerDb']->isTableExists(installerTable('inventory_reservation'))
            ? $GLOBALS['installerDb']->fetchCol($GLOBALS['installerDb']->select()->from(installerTable('inventory_reservation'), ['sku'])->distinct()) : [];
        $file = tempnam($root . '/var/wands-installer', '.delete-products-');
        chmod($file, 0o600);
        $stream = fopen($file, 'w');
        fputcsv($stream, ['sku'], ',', '"', '');
        foreach (installerRows('catalog_product_entity') as $product) {
            fputcsv($stream, [$product['sku']], ',', '"', '');
        }
        fclose($stream);
        try {
            if ($snapshot['products']) {
                $directory = $manager->get(\Magento\Framework\Filesystem::class)->getDirectoryRead(\Magento\Framework\App\Filesystem\DirectoryList::ROOT);
                $import = $manager->get(\Magento\ImportExport\Model\ImportFactory::class)->create();
                $import->setData(['entity' => 'catalog_product', 'behavior' => \Magento\ImportExport\Model\Import::BEHAVIOR_DELETE,
                    'validation_strategy' => 'validation-stop-on-errors', 'allowed_error_count' => 0,
                    '_import_field_separator' => ',', '_import_multiple_value_separator' => ',',
                    'fields_enclosure' => 1, 'images_base_directory' => $directory]);
                $source = $manager->get(\Magento\ImportExport\Model\Import\Source\CsvFactory::class)->create(['file' => $file, 'directory' => $directory]);
                if (!$import->validateSource($source) || !$import->importSource() || $import->getErrorAggregator()->getErrorsCount()) {
                    installerFail('Native product deletion failed. Restore the backup before retrying.');
                }
            }
        } finally {
            unlink($file);
            $events->merge([$eventName => ['process_reservations' => ['disabled' => $previousDisabled]]]);
        }
        foreach (array_chunk($reservationSkus, 1000) as $skus) {
            $manager->get(\Magento\InventorySales\Model\ResourceModel\DeleteReservationsBySkus::class)->execute($skus);
        }
        $categories = installerRows('catalog_category_entity');
        usort($categories, static fn(array $a, array $b): int => (int)$b['level'] <=> (int)$a['level']);
        $repository = $manager->get(\Magento\Catalog\Api\CategoryRepositoryInterface::class);
        $registry = $manager->get(\Magento\Framework\Registry::class);
        $previousSecureArea = $registry->registry('isSecureArea');
        $registry->unregister('isSecureArea');
        $registry->register('isSecureArea', true);
        try {
            foreach ($categories as $category) {
                if (!in_array((int)$category['entity_id'], $snapshot['retained_category_roots'], true)) {
                    $repository->deleteByIdentifier((int)$category['entity_id']);
                }
            }
        } finally {
            $registry->unregister('isSecureArea');
            if ($previousSecureArea !== null) {
                $registry->register('isSecureArea', $previousSecureArea);
            }
        }
    });
    $after = installerInspect();
    if ($after['products'] !== 0 || $after['deletable_categories'] !== 0 || $after['reservations'] !== 0) {
        installerFail('Reset did not reach an empty catalog; restore before retrying.');
    }
    return ['deleted_products' => $snapshot['products'], 'deleted_categories' => $snapshot['deletable_categories'],
        'deleted_reservations' => $snapshot['reservations'],
        'retained_roots' => $snapshot['retained_category_roots']];
}

function installerPreserved(): array
{
    $db = $GLOBALS['installerDb'];
    $productIds = $db->select()->from(installerTable('catalog_product_entity'), ['entity_id'])->where('sku NOT LIKE ?', 'WANDS-%');
    $skus = $db->select()->from(installerTable('catalog_product_entity'), ['sku'])->where('sku NOT LIKE ?', 'WANDS-%');
    $childIds = static function (string $table, string $id, string $parent, object $query) use ($db): object {
        return $db->select()->from(installerTable($table), [$id])->where($parent . ' IN (?)', $query);
    };
    $links = $childIds('catalog_product_link', 'link_id', 'product_id', $productIds);
    $superAttributes = $childIds('catalog_product_super_attribute', 'product_super_attribute_id', 'product_id', $productIds);
    $bundleOptions = $childIds('catalog_product_bundle_option', 'option_id', 'parent_id', $productIds);
    $bundleSelections = $childIds('catalog_product_bundle_selection', 'selection_id', 'parent_product_id', $productIds);
    $options = $childIds('catalog_product_option', 'option_id', 'product_id', $productIds);
    $optionValues = $childIds('catalog_product_option_type_value', 'option_type_id', 'option_id', $options);
    $gallery = $childIds('catalog_product_entity_media_gallery_value_to_entity', 'value_id', 'entity_id', $productIds);
    $downloadLinks = $childIds('downloadable_link', 'link_id', 'product_id', $productIds);
    $downloadSamples = $childIds('downloadable_sample', 'sample_id', 'product_id', $productIds);
    $categoryIds = $db->select()->from(installerTable('catalog_category_entity'), ['entity_id'])->where('entity_id != 1');
    $wandsRoot = $db->fetchOne($db->select()->from(installerTable('store_group'), ['root_category_id'])->where('code = ?', 'wands_catalog'));
    if ($wandsRoot) {
        $path = $db->fetchOne($db->select()->from(installerTable('catalog_category_entity'), ['path'])->where('entity_id = ?', $wandsRoot));
        $categoryIds->where('entity_id != ?', $wandsRoot)->where('path NOT LIKE ?', $path . '/%');
    }
    $scopes = [
        'catalog_product_entity' => ['entity_id', $productIds],
        'catalog_category_entity' => ['entity_id', $categoryIds],
        'catalog_product_website' => ['product_id', $productIds],
        'catalog_category_product' => ['product_id', $productIds],
        'catalog_product_super_link' => ['parent_id', $productIds],
        'catalog_product_super_attribute' => ['product_id', $productIds],
        'catalog_product_super_attribute_label' => ['product_super_attribute_id', $superAttributes],
        'catalog_product_relation' => ['parent_id', $productIds],
        'catalog_product_link' => ['product_id', $productIds],
        'catalog_product_bundle_option' => ['parent_id', $productIds],
        'catalog_product_bundle_option_value' => ['option_id', $bundleOptions],
        'catalog_product_bundle_selection' => ['parent_product_id', $productIds],
        'catalog_product_bundle_selection_price' => ['selection_id', $bundleSelections],
        'catalog_product_option' => ['product_id', $productIds],
        'catalog_product_option_title' => ['option_id', $options],
        'catalog_product_option_price' => ['option_id', $options],
        'catalog_product_option_type_value' => ['option_id', $options],
        'catalog_product_option_type_title' => ['option_type_id', $optionValues],
        'catalog_product_option_type_price' => ['option_type_id', $optionValues],
        'catalog_product_entity_media_gallery' => ['value_id', $gallery],
        'catalog_product_entity_media_gallery_value' => ['entity_id', $productIds],
        'catalog_product_entity_media_gallery_value_to_entity' => ['entity_id', $productIds],
        'downloadable_link' => ['product_id', $productIds],
        'downloadable_link_title' => ['link_id', $downloadLinks],
        'downloadable_link_price' => ['link_id', $downloadLinks],
        'downloadable_sample' => ['product_id', $productIds],
        'downloadable_sample_title' => ['sample_id', $downloadSamples],
        'cataloginventory_stock_item' => ['product_id', $productIds],
        'inventory_source_item' => ['sku', $skus],
        'inventory_reservation' => ['sku', $skus],
    ];
    foreach (['int', 'decimal', 'varchar'] as $type) {
        $scopes['catalog_product_link_attribute_' . $type] = ['link_id', $links];
    }
    foreach (['varchar', 'int', 'decimal', 'text', 'datetime'] as $type) {
        $scopes['catalog_product_entity_' . $type] = ['entity_id', $productIds];
        $scopes['catalog_category_entity_' . $type] = ['entity_id', $categoryIds];
    }
    $hash = hash_init('sha256');
    foreach ($scopes as $name => [$column, $ids]) {
        $table = installerTable($name);
        if (!$db->isTableExists($table)) {
            continue;
        }
        $description = $db->describeTable($table);
        $primary = [];
        foreach ($description as $field => $metadata) {
            if ($metadata['PRIMARY']) {
                $primary[] = $field;
            }
        }
        $query = $db->select()->from($table)->where($column . ' IN (?)', $ids)->order($primary ?: array_keys($description));
        hash_update($hash, $name . "\n");
        $statement = $db->query($query);
        while ($row = $statement->fetch(PDO::FETCH_ASSOC)) {
            hash_update($hash, json_encode($row, JSON_THROW_ON_ERROR) . "\n");
        }
    }
    return ['sha256' => hash_final($hash), 'products' => count($db->fetchCol($productIds)),
        'scope' => 'Native products, options, relationships, gallery rows, stock and categories outside WANDS'];
}

function installerExpectedCategoryPaths(string $value): array
{
    $paths = preg_split('/\||,\s*(?=WANDS Catalog\/)/', $value);
    $taxonomy = \RocketWeb\LabCatalog\Model\Catalog\NavigationTaxonomy::class;
    return class_exists($taxonomy) ? array_map([$taxonomy, 'normalizePath'], $paths) : $paths;
}

function installerVerify(array $request): array
{
    $db = $GLOBALS['installerDb'];
    $root = $GLOBALS['installerRoot'];
    $expected = $request['expected'];
    $rows = $expected['products'];
    $entities = array_values(array_filter(installerRows('catalog_product_entity'),
        static fn(array $row): bool => str_starts_with($row['sku'], 'WANDS-')));
    $actual = array_column($entities, null, 'sku');
    $ids = array_column($entities, 'sku', 'entity_id');
    $failures = [];
    $checks = 0;
    $check = static function (bool $valid, string $label) use (&$checks, &$failures): void {
        $checks++;
        if (!$valid && count($failures) < 25) {
            $failures[] = $label;
        }
    };
    $check(count($entities) === count($rows), 'exact product count');
    $check(array_diff_key($actual, $rows) === [] && array_diff_key($rows, $actual) === [], 'exact SKU inventory');
    $typeId = $db->fetchOne($db->select()->from(installerTable('eav_entity_type'), ['entity_type_id'])->where('entity_type_code = ?', 'catalog_product'));
    $attributes = $db->fetchPairs($db->select()->from(installerTable('eav_attribute'), ['attribute_id', 'attribute_code'])->where('entity_type_id = ?', $typeId));
    $selected = array_keys(array_filter($attributes, static fn(string $code): bool => in_array($code, ['name', 'price', 'special_price', 'status', 'image', 'small_image', 'thumbnail', 'swatch_image'], true)));
    $values = [];
    foreach (['varchar', 'decimal', 'int'] as $type) {
        $statement = $db->query($db->select()->from(installerTable('catalog_product_entity_' . $type))->where('store_id = 0')->where('attribute_id IN (?)', $selected));
        while ($value = $statement->fetch(PDO::FETCH_ASSOC)) {
            if (isset($ids[$value['entity_id']])) {
                $values[$ids[$value['entity_id']]][$attributes[$value['attribute_id']]] = $value['value'];
            }
        }
    }
    $expectedLinks = [];
    foreach ($rows as $sku => $row) {
        $check(($actual[$sku]['type_id'] ?? null) === $row['product_type'], 'product type: ' . $sku);
        foreach (['name' => 'name', 'product_online' => 'status'] as $field => $attribute) {
            if (isset($row[$field])) {
                $wanted = $field === 'product_online' && $row[$field] === '0' ? '2' : (string)$row[$field];
                $check((string)($values[$sku][$attribute] ?? '') === $wanted, $field . ': ' . $sku);
            }
        }
        foreach (['price', 'special_price'] as $field) {
            if (isset($row[$field]) && !in_array($row['product_type'], ['bundle', 'grouped'], true)) {
                $actualValue = $values[$sku][$field] ?? '';
                $check($row[$field] === '' ? $actualValue === '' || $actualValue === null
                    : abs((float)$actualValue - (float)$row[$field]) < 0.005, $field . ': ' . $sku);
            }
        }
        foreach (['base_image' => 'image', 'small_image' => 'small_image', 'thumbnail_image' => 'thumbnail', 'swatch_image' => 'swatch_image'] as $field => $attribute) {
            if (empty($row[$field]) || $row[$field] === 'no_selection') {
                continue;
            }
            $assigned = $root . '/pub/media/catalog/product/' . ltrim($values[$sku][$attribute] ?? '', '/');
            $sha = $expected['image_sha256'][ltrim($row[$field], '/')] ?? '';
            $check(is_file($assigned) && $sha !== '' && $sha === hash_file('sha256', $assigned), $field . ': ' . $sku);
        }
        if ($row['product_type'] === 'configurable') {
            foreach (explode('|', $row['configurable_variations']) as $variation) {
                if (preg_match('/(?:^|,)sku=([^,]+)/', $variation, $match)) {
                    $expectedLinks[$sku . '|' . $match[1]] = true;
                }
            }
        }
    }
    $galleryExpected = [];
    foreach ($rows as $sku => $row) {
        $files = [];
        foreach (['base_image', 'small_image', 'thumbnail_image', 'swatch_image', 'additional_images'] as $field) {
            foreach (explode(',', $row[$field] ?? '') as $name) {
                if ($name !== '' && $name !== 'no_selection') {
                    $files[ltrim($name, '/')] = true;
                }
            }
        }
        $galleryExpected[$sku] = array_keys($files);
    }
    installerCheckGallery(['expected' => $galleryExpected, 'media_sha256' => $expected['image_sha256']]);
    $actualLinks = [];
    foreach (installerRows('catalog_product_super_link') as $link) {
        if (!isset($ids[$link['parent_id']]) && !isset($ids[$link['product_id']])) {
            continue;
        }
        $actualLinks[($ids[$link['parent_id']] ?? '?') . '|' . ($ids[$link['product_id']] ?? '?')] = true;
    }
    $check(array_diff_key($actualLinks, $expectedLinks) === [] && array_diff_key($expectedLinks, $actualLinks) === [], 'exact configurable relationships');
    $categoryType = $db->fetchOne($db->select()->from(installerTable('eav_entity_type'), ['entity_type_id'])->where('entity_type_code = ?', 'catalog_category'));
    $nameId = $db->fetchOne($db->select()->from(installerTable('eav_attribute'), ['attribute_id'])->where('entity_type_id = ?', $categoryType)->where('attribute_code = ?', 'name'));
    $names = $db->fetchPairs($db->select()->from(installerTable('catalog_category_entity_varchar'), ['entity_id', 'value'])->where('attribute_id = ?', $nameId)->where('store_id = 0'));
    $paths = [];
    foreach (installerRows('catalog_category_entity') as $category) {
        $parts = array_filter(explode('/', $category['path']), static fn(string $id): bool => (int)$id !== 1);
        $path = implode('/', array_map(static fn(string $id): string => $names[$id] ?? '?', $parts));
        $paths[(int)$category['entity_id']] = $path;
    }
    $assignedCategories = [];
    foreach (installerRows('catalog_category_product') as $link) {
        $assignedCategories[$ids[$link['product_id']] ?? '?'][$paths[$link['category_id']] ?? '?'] = true;
    }
    foreach ($rows as $sku => $row) {
        if (!empty($row['categories'])) {
            $wanted = array_fill_keys(installerExpectedCategoryPaths($row['categories']), true);
            $found = $assignedCategories[$sku] ?? [];
            $check(array_diff_key($wanted, $found) === [] && array_diff_key($found, $wanted) === [], 'exact category assignments: ' . $sku);
        }
    }
    foreach (['bundle_options' => 'catalog_product_bundle_option', 'bundle_selections' => 'catalog_product_bundle_selection'] as $field => $table) {
        if (isset($expected['counts'][$field])) {
            $column = $field === 'bundle_options' ? 'parent_id' : 'parent_product_id';
            $bundleRows = array_filter(installerRows($table), static fn(array $row): bool => isset($ids[$row[$column]]));
            $check(count($bundleRows) === $expected['counts'][$field], $field);
        }
    }
    if ($failures !== []) {
        installerFail('Catalog verification failed: ' . implode('; ', $failures));
    }
    return ['passed' => true, 'checks' => $checks, 'products' => count($entities),
        'scope' => 'Exact SKU/type inventory, names/status/prices, image roles, configurable links and declared bundle counts; storefront QA remains separate'];
}

function installerCheckFields(array $request): array
{
    return $GLOBALS['installerManager']->get(\Magento\Framework\App\State::class)->emulateAreaCode(
        \Magento\Framework\App\Area::AREA_ADMINHTML, static fn(): array => installerCheckFieldsInArea($request)
    );
}

function installerCheckFieldsInArea(array $request): array
{
    $db = $GLOBALS['installerDb'];
    $root = $GLOBALS['installerRoot'];
    $typeId = $db->fetchOne($db->select()->from(installerTable('eav_entity_type'), ['entity_type_id'])->where('entity_type_code = ?', 'catalog_product'));
    $metadata = $db->fetchAll($db->select()->from(installerTable('eav_attribute'))->where('entity_type_id = ?', $typeId));
    $attributes = array_column($metadata, null, 'attribute_code');
    $products = array_column(installerRows('catalog_product_entity'), 'entity_id', 'sku');
    $aliases = ['product_online' => 'status', 'base_image' => 'image', 'thumbnail_image' => 'thumbnail',
        'base_image_label' => 'image_label', 'thumbnail_image_label' => 'thumbnail_label'];
    $checks = 0;
    foreach ($request['expected'] as $sku => $fields) {
        if (!isset($products[$sku])) {
            installerFail('Baseline product is missing: ' . $sku);
        }
        foreach ($fields as $field => $expected) {
            $code = $aliases[$field] ?? $field;
            if ($field === 'product_online' && $expected === '0') {
                $expected = '2';
            }
            if (!isset($attributes[$code]) || !in_array($attributes[$code]['backend_type'], ['varchar', 'text', 'int', 'decimal', 'datetime'], true)) {
                installerFail('Updater cannot compare this field safely: ' . $field);
            }
            $attribute = $attributes[$code];
            $actual = $db->fetchOne($db->select()->from(installerTable('catalog_product_entity_' . $attribute['backend_type']), ['value'])
                ->where('entity_id = ?', $products[$sku])->where('attribute_id = ?', $attribute['attribute_id'])->where('store_id = 0'));
            $actual = $actual === false || $actual === null ? '' : (string)$actual;
            if (in_array($code, ['image', 'small_image', 'thumbnail', 'swatch_image'], true)) {
                if ($expected === '' || $expected === 'no_selection') {
                    $valid = in_array($actual, ['', 'no_selection'], true);
                } else {
                    $path = $root . '/pub/media/catalog/product/' . ltrim($actual, '/');
                    $valid = is_file($path) && hash_file('sha256', $path) === ($request['media_sha256'][ltrim($expected, '/')] ?? null);
                }
            } else {
                if ($attribute['frontend_input'] === 'select' && $expected !== '' && !is_numeric($expected)) {
                    $model = $GLOBALS['installerManager']->get(\Magento\Eav\Model\Config::class)->getAttribute('catalog_product', $code);
                    $actual = (string)$model->getSource()->getOptionText($actual);
                }
                if ($code === 'url_key') {
                    $expected = $GLOBALS['installerManager']->get(\Magento\Catalog\Model\Product\Url::class)->formatUrlKey($expected);
                }
                $valid = $expected === '' ? $actual === '' : ($attribute['backend_type'] === 'decimal'
                    ? $actual !== '' && abs((float)$actual - (float)$expected) < 0.00001
                    : ($attribute['backend_type'] === 'datetime' ? strtotime($actual . ' UTC') === strtotime($expected . ' UTC') : $actual === (string)$expected));
            }
            $checks++;
            if (!$valid) {
                installerFail('Local value differs from the pinned baseline: ' . $sku . ':' . $field);
            }
        }
    }
    return ['passed' => true, 'fields_checked' => $checks];
}

function installerGalleryHashes(array $skus): array
{
    $db = $GLOBALS['installerDb'];
    $result = array_fill_keys($skus, []);
    $cache = [];
    foreach (array_chunk($skus, 1000) as $batch) {
        $query = $db->select()->from(['l' => installerTable('catalog_product_entity_media_gallery_value_to_entity')], [])
            ->join(['g' => installerTable('catalog_product_entity_media_gallery')], 'g.value_id=l.value_id', ['value'])
            ->join(['p' => installerTable('catalog_product_entity')], 'p.entity_id=l.entity_id', ['sku'])->where('p.sku IN (?)', $batch);
        foreach ($db->fetchAll($query) as $row) {
            $file = $GLOBALS['installerRoot'] . '/pub/media/catalog/product/' . ltrim($row['value'], '/');
            if (!isset($cache[$file])) {
                if (!is_file($file)) {
                    installerFail('Missing gallery file for ' . $row['sku']);
                }
                $cache[$file] = hash_file('sha256', $file);
            }
            $result[$row['sku']][$cache[$file]] = true;
        }
    }
    foreach ($result as &$hashes) {
        $hashes = array_keys($hashes);
        sort($hashes);
    }
    unset($hashes);
    return $result;
}

function installerCheckGallery(array $request): array
{
    if (!empty($request['guard_scopes']) && $request['expected']) {
        $db = $GLOBALS['installerDb'];
        foreach (array_chunk(array_keys($request['expected']), 1000) as $skus) {
            $query = $db->select()->from(['v' => installerTable('catalog_product_entity_varchar')], ['COUNT(*)'])
                ->join(['a' => installerTable('eav_attribute')], 'a.attribute_id=v.attribute_id', [])
                ->join(['p' => installerTable('catalog_product_entity')], 'p.entity_id=v.entity_id', [])
                ->where('p.sku IN (?)', $skus)->where('v.store_id != 0')
                ->where('a.attribute_code IN (?)', ['image', 'small_image', 'thumbnail', 'swatch_image', 'image_label', 'small_image_label', 'thumbnail_label']);
            if ((int)$db->fetchOne($query)) {
                installerFail('Per-store image overrides require review before gallery replacement.');
            }
            $galleryQuery = $db->select()->from(['v' => installerTable('catalog_product_entity_media_gallery_value')], ['COUNT(*)'])
                ->join(['p' => installerTable('catalog_product_entity')], 'p.entity_id=v.entity_id', [])
                ->where('p.sku IN (?)', $skus)->where('v.store_id != 0');
            if ((int)$db->fetchOne($galleryQuery)) {
                installerFail('Per-store gallery overrides require review before gallery replacement.');
            }
        }
    }
    $actual = installerGalleryHashes(array_keys($request['expected']));
    foreach ($request['expected'] as $sku => $files) {
        $wanted = [];
        foreach ($files as $file) {
            if (!isset($request['media_sha256'][$file])) {
                installerFail('Pinned gallery inventory is incomplete: ' . $sku);
            }
            $wanted[$request['media_sha256'][$file]] = true;
        }
        $wanted = array_keys($wanted);
        sort($wanted);
        if ($actual[$sku] !== $wanted) {
            installerFail('Gallery differs from the pinned release: ' . $sku);
        }
    }
    return ['passed' => true, 'galleries_checked' => count($actual)];
}

function installerClearGallery(array $request): array
{
    return $GLOBALS['installerManager']->get(\Magento\Framework\App\State::class)->emulateAreaCode(
        \Magento\Framework\App\Area::AREA_ADMINHTML, static fn(): array => installerClearGalleryInArea($request)
    );
}

function installerClearGalleryInArea(array $request): array
{
    $db = $GLOBALS['installerDb'];
    if (!is_file($GLOBALS['installerRoot'] . '/var/.maintenance.flag')) {
        installerFail('Gallery updates require maintenance mode.');
    }
    $count = 0;
    foreach (array_chunk($request['skus'], 1000) as $batch) {
        foreach ($batch as $sku) {
            if (!str_starts_with($sku, 'WANDS-')) {
                installerFail('Gallery updates are limited to WANDS SKUs.');
            }
        }
        $ids = $db->fetchCol($db->select()->from(installerTable('catalog_product_entity'), ['entity_id'])->where('sku IN (?)', $batch));
        if (count($ids) !== count($batch)) {
            installerFail('A planned gallery product is missing.');
        }
        $outside = (int)$db->fetchOne($db->select()->from(['w' => installerTable('catalog_product_website')], ['COUNT(*)'])
            ->join(['s' => installerTable('store_website')], 's.website_id=w.website_id', [])
            ->where('w.product_id IN (?)', $ids)->where('s.code != ?', 'wands'));
        if ($outside) {
            installerFail('Gallery product is assigned outside the WANDS website.');
        }
        $db->beginTransaction();
        try {
            foreach (['catalog_product_entity_media_gallery_value', 'catalog_product_entity_media_gallery_value_to_entity'] as $table) {
                $db->delete(installerTable($table), ['entity_id IN (?)' => $ids]);
            }
            // Retain gallery masters and binaries shared by other products; native import restores this product's links.
            $values = ['image' => 'no_selection', 'small_image' => 'no_selection', 'thumbnail' => 'no_selection',
                'swatch_image' => 'no_selection', 'image_label' => '', 'small_image_label' => '', 'thumbnail_label' => ''];
            $available = $db->fetchCol($db->select()->from(installerTable('eav_attribute'), ['attribute_code'])->where('attribute_code IN (?)', array_keys($values)));
            $GLOBALS['installerManager']->get(\Magento\Catalog\Model\Product\Action::class)->updateAttributes($ids, array_intersect_key($values, array_fill_keys($available, true)), 0);
            $db->commit();
            $count += count($ids);
        } catch (Throwable $exception) {
            $db->rollBack();
            throw $exception;
        }
    }
    return ['galleries_cleared' => $count];
}

function installerActivate(): array
{
    $manager = $GLOBALS['installerManager'];
    $db = $GLOBALS['installerDb'];
    $websiteResource = $manager->get(\Magento\Store\Model\ResourceModel\Website::class);
    $websites = $manager->get(\Magento\Store\Model\WebsiteFactory::class)->create()->getCollection();
    $found = false;
    $db->beginTransaction();
    try {
        foreach ($websites as $website) {
            $isWands = $website->getCode() === 'wands';
            $found = $found || $isWands;
            if ($isWands || $website->getIsDefault()) {
                $website->setIsDefault($isWands ? 1 : 0);
                $websiteResource->save($website);
            }
        }
        if (!$found) {
            installerFail('The provisioned WANDS website is missing.');
        }
        $db->commit();
    } catch (Throwable $exception) {
        $db->rollBack();
        throw $exception;
    }
    return ['default_website' => 'wands'];
}

function installerStock(array $request): array
{
    $db = $GLOBALS['installerDb'];
    $result = ['legacy' => [], 'source_items' => [], 'reservations' => []];
    foreach (array_chunk($request['skus'], 1000) as $batch) {
        $query = $db->select()->from(['s' => installerTable('cataloginventory_stock_item')])
            ->join(['p' => installerTable('catalog_product_entity')], 'p.entity_id=s.product_id', ['sku'])->where('p.sku IN (?)', $batch);
        array_push($result['legacy'], ...$db->fetchAll($query));
        foreach (['source_items' => 'inventory_source_item', 'reservations' => 'inventory_reservation'] as $key => $table) {
            if ($db->isTableExists(installerTable($table))) {
                array_push($result[$key], ...$db->fetchAll($db->select()->from(installerTable($table))->where('sku IN (?)', $batch)));
            }
        }
    }
    foreach ($result as &$rows) {
        usort($rows, static fn(array $a, array $b): int => strcmp(json_encode($a), json_encode($b)));
    }
    unset($rows);
    return $result;
}

try {
    $request = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
    $root = realpath($request['root'] ?? '');
    if (!$root || !is_file($root . '/app/bootstrap.php') || !is_file($root . '/app/etc/env.php')) {
        installerFail('An existing installed Magento root is required.');
    }
    if ($request['action'] === 'probe') {
        $probe = realpath($request['path']);
        if (!$probe || !str_starts_with($probe, $root . '/var/wands-installer/mount-probe-')
            || hash_file('sha256', $probe) !== $request['sha256']) {
            installerFail('Host and PHP runtime paths do not refer to the same store files.');
        }
        echo json_encode(['passed' => true], JSON_THROW_ON_ERROR) . PHP_EOL;
        exit(0);
    }
    $GLOBALS['installerRoot'] = $root;
    $GLOBALS['installerConfig'] = require $root . '/app/etc/env.php';
    require $root . '/app/bootstrap.php';
    $manager = \Magento\Framework\App\Bootstrap::create(BP, $_SERVER)->getObjectManager();
    $GLOBALS['installerManager'] = $manager;
    $GLOBALS['installerResource'] = $manager->get(\Magento\Framework\App\ResourceConnection::class);
    $GLOBALS['installerDb'] = $GLOBALS['installerResource']->getConnection();
    $result = match ($request['action']) {
        'inspect' => installerInspect(),
        'backup' => installerDatabaseTool($request, false),
        'restore' => installerDatabaseTool($request, true),
        'reset' => installerReset($request),
        'verify' => installerVerify($request),
        'check-fields' => installerCheckFields($request),
        'activate' => installerActivate(),
        'stock' => installerStock($request),
        'preserved' => installerPreserved(),
        'check-gallery' => installerCheckGallery($request),
        'clear-gallery' => installerClearGallery($request),
        default => throw new CatalogInstallerFailure('Unsupported runtime action.'),
    };
    echo json_encode($result, JSON_THROW_ON_ERROR) . PHP_EOL;
} catch (Throwable $exception) {
    $causes = [];
    for ($cause = $exception; $cause !== null && count($causes) < 5; $cause = $cause->getPrevious()) {
        $causes[] = ['class' => get_class($cause), 'file' => $cause->getFile(), 'line' => $cause->getLine()];
    }
    echo json_encode(['error' => $exception instanceof CatalogInstallerFailure ? $exception->getMessage()
        : 'Runtime failed (' . get_class($exception) . '); check the target runtime and PHP/database prerequisites.',
        'causes' => $causes], JSON_THROW_ON_ERROR) . PHP_EOL;
    exit(1);
}
