<?php
declare(strict_types=1);

require __DIR__.'/rehearsal_runtime.php';

function mediaFixtureRows($connection): array
{
    $result = [];
    foreach ($connection->fetchCol('SHOW TABLES') as $table) {
        $result[$table] = $connection->fetchAll('SELECT * FROM '.$connection->quoteIdentifier($table));
    }
    ksort($result);
    return $result;
}

function mediaFixtureFiles(string $root): array
{
    $result = [];
    $directory = $root.'/pub/media';
    requireRehearsal(!is_link($directory) && realpath($directory) === $directory, 'Unsafe media root');
    $iterator = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($directory, FilesystemIterator::SKIP_DOTS));
    foreach ($iterator as $file) {
        requireRehearsal(!$file->isLink(), 'Media symlinks are forbidden');
        if ($file->isFile()) {
            $result[substr($file->getPathname(), strlen($root) + 1)] = [
                'sha256' => hash_file('sha256', $file->getPathname()), 'bytes' => $file->getSize()
            ];
        }
    }
    ksort($result);
    return $result;
}

function verifyMediaPacket(string $stage): array
{
    $manifest = json_decode(file_get_contents($stage.'/manifest.json'), true, 512, JSON_THROW_ON_ERROR);
    requireRehearsal($manifest['version'] === 'wands-native-media-rehearsal-v1' && $manifest['publication_approved'] === false, 'Wrong media packet');
    foreach ($manifest['inputs'] as $path => $hash) {
        requireRehearsal(hash_file('sha256', $path) === $hash, 'Media provenance drift');
    }
    foreach ($manifest['outputs'] as $relative => $hash) {
        $source = realpath($stage.'/'.$relative);
        requireRehearsal($source !== false && str_starts_with($source, $stage.'/') && hash_file('sha256', $source) === $hash, 'Staged output drift');
    }
    return $manifest;
}

function verifyMediaSource(string $root, string $stage): void
{
    $manifest = verifyMediaPacket($stage);
    foreach ($manifest['outputs'] as $relative => $hash) {
        if (str_starts_with($relative, 'staging-root/')) {
            $path = $root.'/'.substr($relative, strlen('staging-root/'));
            requireRehearsal(realpath($path) === $path && hash_file('sha256', $path) === $hash, 'Mounted import source changed or escaped');
        }
    }
}

function prepareMediaFixture($connection, string $root, string $stage): array
{
    verifyMediaPacket($stage);
    requireRehearsal(!file_exists($root.'/var/wands/media.review.csv') && mediaFixtureFiles($root) === [], 'Choose a fresh empty media fixture');
    $scope = json_decode(file_get_contents($stage.'/scope.json'), true, 512, JSON_THROW_ON_ERROR);
    requireRehearsal(count($scope['staged']) === 5, 'Wrong file scope');
    foreach ($scope['staged'] as $file) {
        requireRehearsal((bool)preg_match('#^staging-root/pub/media/import/wands/pilot-media-v1/WANDS-[0-9]{6}-import-[a-f0-9]{12}\.jpg$#', $file['path']), 'Unsafe staged image path');
        $destination = $root.'/'.substr($file['path'], strlen('staging-root/'));
        if (!is_dir(dirname($destination))) {
            mkdir(dirname($destination), 0700, true);
        }
        requireRehearsal(copy($stage.'/'.$file['path'], $destination), 'Image copy failed');
    }
    mkdir($root.'/var/wands', 0700, true);
    requireRehearsal(copy($stage.'/staging-root/var/wands/media.review.csv', $root.'/var/wands/media.review.csv'), 'CSV copy failed');
    return installMediaFixtureSchema($connection, $root) + ['stage_manifest_sha256' => hash_file('sha256', $stage.'/manifest.json')];
}

function installMediaFixtureSchema($connection, string $root): array
{
    $schema = $root.'/vendor/mage-os/module-import-export/etc/db_schema.xml';
    requireRehearsal(hash_file('sha256', $schema) === '94457b59c929fd8a0f2c626af79972d1bd48477f58014454a4dd254aebe87983', 'Review changed native import staging schema');
    $translation = $root.'/vendor/mage-os/module-translation/etc/db_schema.xml';
    requireRehearsal(hash_file('sha256', $translation) === 'b940136f341ef6d56b0dcc4c4c4a63a74f93c4916132bf8aa5baf11e284d5eb7', 'Review changed translation schema');
    $ddl = [
        'importexport_importdata' => 'CREATE TABLE importexport_importdata (id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, entity VARCHAR(50) NOT NULL, behavior VARCHAR(10) NOT NULL DEFAULT "append", data LONGTEXT NULL, is_processed SMALLINT NOT NULL DEFAULT 1, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP) ENGINE=InnoDB',
        'import_history' => 'CREATE TABLE import_history (history_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, user_id INT UNSIGNED NOT NULL DEFAULT 0, imported_file VARCHAR(255) NULL, execution_time VARCHAR(255) NULL, summary VARCHAR(255) NULL, error_file VARCHAR(255) NOT NULL) ENGINE=InnoDB',
        'translation' => 'CREATE TABLE translation (key_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, string VARCHAR(255) NOT NULL DEFAULT "Translate String", store_id SMALLINT UNSIGNED NOT NULL DEFAULT 0, translate VARCHAR(255) NULL, locale VARCHAR(20) NOT NULL DEFAULT "en_US", crc_string BIGINT NOT NULL DEFAULT 1591228201, UNIQUE KEY TRANSLATION_STORE_ID_LOCALE_CRC_STRING_STRING (store_id,locale,crc_string,string), CONSTRAINT TRANSLATION_STORE_ID_STORE_STORE_ID FOREIGN KEY (store_id) REFERENCES store(store_id) ON DELETE CASCADE) ENGINE=InnoDB'
    ];
    $created = [];
    foreach ($ddl as $table => $sql) {
        if (!$connection->isTableExists($table)) {
            $connection->query($sql);
            $created[] = $table;
        }
    }
    return ['schema_sha256' => hash_file('sha256', $schema), 'translation_schema_sha256' => hash_file('sha256', $translation), 'local_only_ddl' => $ddl, 'created_tables' => $created];
}

function loadImportCategories($connection, string $path): array
{
    $raw = file_get_contents($path);
    $start = strpos($raw, '{');
    requireRehearsal($start !== false, 'Category capture has no JSON');
    $prefix = substr($raw, 0, $start);
    requireRehearsal($prefix === '' || (bool)preg_match('#^\s*Warning: hash_file\(/proc/[0-9]+/fd/pipe:\[[0-9]+\]\): Failed to open stream: No such file or directory in /proc/[0-9]+/fd/pipe:\[[0-9]+\] on line [0-9]+\s*$#', $prefix), 'Unrecognized capture diagnostic');
    $capture = json_decode(substr($raw, $start), true, 512, JSON_THROW_ON_ERROR);
    requireRehearsal($capture['host'] === 'relevance.comtom.lab' && $capture['consistent_read_only'] === true && time() - strtotime($capture['captured_at']) < 86400, 'Wrong or stale category capture');
    $expected = ['catalog_category_entity'];
    foreach (['varchar','int','text','decimal','datetime'] as $type) {
        $expected[] = 'catalog_category_entity_'.$type;
    }
    $actual = array_keys($capture['rows']); sort($actual); sort($expected);
    requireRehearsal($actual === $expected && count($capture['ancestor_ids']) <= 50, 'Unexpected category scope');
    requireRehearsal(count($capture['ddl']) === 5, 'Unexpected category schema count');
    foreach ($capture['ddl'] as $table => $ddl) {
        requireRehearsal(in_array($table, $expected, true) && $table !== 'catalog_category_entity' && str_starts_with($ddl, 'CREATE TABLE `'.$table.'` (') && !str_contains($ddl, ';'), 'Unsafe category schema');
        requireRehearsal(!$connection->isTableExists($table), 'Category support already installed');
        $connection->query($ddl);
    }
    $counts = [];
    $connection->beginTransaction();
    try {
        foreach ($capture['rows'] as $table => $rows) {
            $counts[$table] = 0;
            foreach ($rows as $row) {
                requireRehearsal(in_array((int)$row['entity_id'], $capture['ancestor_ids'], true), 'Category row outside ancestor scope');
                if ($table === 'catalog_category_entity') {
                    $existing = $connection->fetchRow('SELECT * FROM catalog_category_entity WHERE entity_id=?', [$row['entity_id']]);
                    if ($existing) {
                        requireRehearsal($existing == $row, 'Existing category metadata drift');
                        continue;
                    }
                }
                $connection->insert($table, $row);
                $counts[$table]++;
            }
        }
        $connection->commit();
    } catch (Throwable $e) {
        $connection->rollBack();
        throw $e;
    }
    return ['capture_sha256' => hash_file('sha256', $path), 'capture_diagnostic_retained' => $prefix !== '', 'rows_added' => $counts, 'ancestor_ids' => $capture['ancestor_ids'], 'live_writes' => false];
}

$a = getopt('', ['root:', 'output:', 'plan:', 'stage:', 'action:', 'categories:', 'validation:']);
ini_set('display_errors', '0');
ini_set('log_errors', '1');
ini_set('error_log', ($a['output'] ?? sys_get_temp_dir().'/wands-media-probe').'.php.log');
ob_start();
register_shutdown_function(static function () use ($a): void {
    $output = ob_get_clean();
    if ($output !== false && $output !== '') {
        file_put_contents(($a['output'] ?? sys_get_temp_dir().'/wands-media-probe').'.native-output.log', $output, FILE_APPEND);
    }
});
try {
    requireRehearsal(in_array($a['action'], ['prepare', 'support-schema', 'categories', 'validate', 'import'], true), 'Unsupported action');
    if ($a['action'] === 'import') {
        $validation = isset($a['validation']) && is_file($a['validation'])
            ? json_decode(file_get_contents($a['validation']), true, 512, JSON_THROW_ON_ERROR) : [];
        requireRehearsal(($validation['action'] ?? null) === 'validate'
            && ($validation['result']['validated_only'] ?? false) === true
            && ($validation['result']['processed_rows'] ?? null) === 5
            && ($validation['result']['errors'] ?? null) === 0
            && ($validation['result']['invalid_rows'] ?? null) === 0, 'Successful native validation is required');
    }
    foreach (['root', 'output', 'plan'] as $required) {
        requireRehearsal(isset($a[$required]), 'Missing required argument: '.$required);
    }
    [$om, $connection, $isolation, $entities] = openRehearsal($a);
    $root = $isolation['root'];
    if ($a['action'] === 'categories') {
        saveRehearsal($a['output'], loadImportCategories($connection, $a['categories']) + ['database' => $isolation['database']]);
        exit(0);
    }
    if ($a['action'] === 'support-schema') {
        saveRehearsal($a['output'], installMediaFixtureSchema($connection, $root) + ['database' => $isolation['database'], 'live_writes' => false]);
        exit(0);
    }
    if ($a['action'] === 'prepare') {
        $prepared = prepareMediaFixture($connection, $root, realpath($a['stage']));
        saveRehearsal($a['output'], $prepared + ['database' => $isolation['database'], 'files' => mediaFixtureFiles($root), 'native_import_executed' => false, 'live_writes' => false]);
        exit(0);
    }
    requireRehearsal($connection->fetchOne('SELECT type_id FROM catalog_product_entity WHERE sku="WANDS-000056"') === 'simple', 'Apply the verified definition migration first');
    verifyMediaSource($root, realpath($a['stage']));
    $module = dirname(__DIR__, 3).'/app/code/RocketWeb/LabCatalog/Model/Catalog/';
    requireRehearsal(!class_exists(\RocketWeb\LabCatalog\Model\Catalog\ProductImporter::class, false), 'Importer was loaded before candidate selection');
    require $module.'BundleAssortmentReconciler.php';
    require $module.'ProductImporter.php';
    $before = rehearsalTableHashes($connection);
    if ($a['action'] === 'import') {
        requireRehearsal($validation['database'] === $isolation['database'] && $validation['root'] === $root
            && $validation['after_table_hashes'] === $before && $validation['files'] === mediaFixtureFiles($root)
            && $validation['probe_sha256'] === hash_file('sha256', __FILE__)
            && $validation['importer_sha256'] === hash_file('sha256', $module.'ProductImporter.php'), 'Native validation is stale or belongs to another fixture');
    }
    $backup = ['database' => $isolation['database'], 'root' => $root, 'action' => $a['action'],
        'table_hashes' => $before, 'rows' => mediaFixtureRows($connection), 'files' => mediaFixtureFiles($root),
        'probe_sha256' => hash_file('sha256', __FILE__), 'plan_sha256' => hash_file('sha256', $a['plan']),
        'importer_sha256' => hash_file('sha256', $module.'ProductImporter.php'), 'live_writes' => false];
    saveRehearsal($a['output'].'.before.json', $backup);
    $result = $om->create(\RocketWeb\LabCatalog\Model\Catalog\ProductImporter::class)->execute($root.'/var/wands/media.review.csv', $a['action'] === 'validate', false);
    $after = rehearsalTableHashes($connection);
    saveRehearsal($a['output'], ['database' => $isolation['database'], 'root' => $root, 'action' => $a['action'],
        'result' => $result, 'versions' => $isolation['versions'], 'before_sha256' => hash_file('sha256', $a['output'].'.before.json'),
        'before_table_hashes' => $before, 'after_table_hashes' => $after, 'rows' => mediaFixtureRows($connection),
        'changed_tables' => array_keys(array_diff_assoc($after, $before)), 'files' => mediaFixtureFiles($root),
        'probe_sha256' => hash_file('sha256', __FILE__), 'importer_sha256' => $backup['importer_sha256'],
        'rollback_verified' => false, 'live_writes' => false]);
} catch (Throwable $e) {
    rehearsalFailure($a, $e, isset($before, $connection) ? ['before_table_hashes' => $before,
        'after_table_hashes' => rehearsalTableHashes($connection), 'rows' => mediaFixtureRows($connection),
        'files' => mediaFixtureFiles($root), 'accepted' => false, 'live_writes' => false] : []);
}
