<?php
declare(strict_types=1);

/** Private, scoped image-path migration. No product saves or original-file overwrites. */
function whiteLiveWrite(string $path, array $value): void
{
    $temporary = $path . '.tmp';
    $stream = fopen($temporary, 'wb');
    if (!$stream) { throw new RuntimeException('Cannot reserve private receipt'); }
    chmod($temporary, 0600);
    $bytes = json_encode($value, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES);
    if (fwrite($stream, $bytes) !== strlen($bytes) || !fflush($stream) || !fsync($stream)) {
        throw new RuntimeException('Cannot persist private receipt');
    }
    fclose($stream);
    if (!rename($temporary, $path)) { throw new RuntimeException('Cannot install private receipt'); }
}

function whiteLiveContext(string $root): PDO
{
    if (realpath($root) !== '/var/www/html') { throw new RuntimeException('Wrong application root'); }
    $env = require $root . '/app/etc/env.php';
    if (!empty($env['db']['table_prefix'])) { throw new RuntimeException('Unexpected table prefix'); }
    $c = $env['db']['connection']['default'];
    $dsn = 'mysql:host=' . $c['host'] . ';dbname=' . $c['dbname'] . ';charset=utf8mb4';
    if (!empty($c['port'])) { $dsn .= ';port=' . (int)$c['port']; }
    $db = new PDO($dsn, $c['username'], $c['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $urls = $db->query("SELECT DISTINCT value FROM core_config_data WHERE path IN ('web/secure/base_url','web/unsecure/base_url')")->fetchAll(PDO::FETCH_COLUMN);
    if ($urls !== ['https://latest.rocketcode.com/']) { throw new RuntimeException('Only latest.rocketcode.com is authorized'); }
    if ((int)$db->query('SELECT COUNT(*) FROM catalog_product_entity')->fetchColumn() !== 107815) {
        throw new RuntimeException('Unexpected product population');
    }
    return $db;
}

function whiteLiveFile(string $root, string $value): string
{
    if (!preg_match('#^/[a-z0-9_/.-]+\.jpg$#', $value) || str_contains($value, '..')) {
        throw new RuntimeException('Unsafe product image path');
    }
    $base = realpath($root . '/pub/media/catalog/product');
    $path = realpath($root . '/pub/media/catalog/product' . $value);
    if (!$path || !is_file($path) || !str_starts_with($path, $base . '/')) {
        throw new RuntimeException('Missing imported JPEG: ' . $value);
    }
    return $path;
}

function whiteLiveInspect(PDO $db, string $root, array $packet): array
{
    if ($packet['target'] !== 'https://latest.rocketcode.com/' || count($packet['assignments']) !== 107455) {
        throw new RuntimeException('Unapproved deployment packet');
    }
    $wanted = array_filter($packet['assignments'], fn($r) => $r['original_sha256'] !== $r['selected_sha256']);
    $entities = [];
    foreach ($db->query('SELECT entity_id,sku FROM catalog_product_entity') as $row) {
        if (isset($wanted[$row['sku']])) {
            if (str_starts_with($row['sku'], 'WANDS-QA-')) { throw new RuntimeException('QA target is excluded'); }
            $entities[(int)$row['entity_id']] = ['sku' => $row['sku'], ...$wanted[$row['sku']]];
        }
    }
    if (count($entities) !== count($wanted)) { throw new RuntimeException('Unknown selected product SKU'); }
    $roles = [];
    $sql = "SELECT v.* FROM catalog_product_entity_varchar v JOIN eav_attribute a USING(attribute_id) WHERE a.attribute_code IN ('image','small_image','thumbnail') ORDER BY v.value_id";
    foreach ($db->query($sql, PDO::FETCH_ASSOC) as $row) {
        if (isset($entities[(int)$row['entity_id']])) { $roles[(int)$row['entity_id']][] = $row; }
    }
    $plan = ['target' => $packet['target'], 'packet_sha256' => $packet['packet_sha256'],
        'max_gallery_id' => (int)$db->query('SELECT MAX(value_id) FROM catalog_product_entity_media_gallery')->fetchColumn(),
        'roles' => [], 'galleries' => [], 'images' => [], 'source_files' => [], 'entity_files' => []];
    $hashes = []; $changed = []; $already = 0;
    foreach ($entities as $id => $target) {
        $defaults = 0; $new = $target['selected_sha256']; $original = $target['original_sha256'];
        $destination = '/' . $new[0] . '/' . $new[1] . '/' . $new . '.jpg';
        foreach ($roles[$id] ?? [] as $row) {
            $value = $row['value'];
            $path = whiteLiveFile($root, $value);
            $hashes[$value] ??= hash_file('sha256', $path);
            if (!in_array($hashes[$value], [$original, $new], true)) {
                throw new RuntimeException('Image differs from approved source: ' . $target['sku']);
            }
            if ((int)$row['store_id'] === 0) { $defaults++; }
            if ($hashes[$value] === $new) { continue; }
            $plan['roles'][] = ['value_id' => (int)$row['value_id'], 'entity_id' => $id,
                'attribute_id' => (int)$row['attribute_id'], 'store_id' => (int)$row['store_id'],
                'before' => $value, 'after' => $destination];
            $plan['entity_files'][$id][$value] = true;
            $plan['images'][$new] = ['file' => $new . '.jpg', 'destination' => $destination];
            $plan['source_files'][$value] = $original;
            $changed[$id] = $target['sku'];
        }
        if ($defaults !== 3) { throw new RuntimeException('Missing default image roles: ' . $target['sku']); }
        if (!isset($changed[$id])) { $already++; }
    }
    $masters = [];
    foreach ($db->query('SELECT * FROM catalog_product_entity_media_gallery ORDER BY value_id', PDO::FETCH_ASSOC) as $row) {
        $masters[(int)$row['value_id']] = $row;
    }
    $coverage = [];
    foreach ($db->query('SELECT * FROM catalog_product_entity_media_gallery_value ORDER BY record_id', PDO::FETCH_ASSOC) as $row) {
        $id = (int)$row['entity_id']; $gid = (int)$row['value_id']; $master = $masters[$gid];
        if (!isset($plan['entity_files'][$id][$master['value']])) { continue; }
        if ($master['media_type'] !== 'image') { throw new RuntimeException('Non-image gallery entry'); }
        $new = $entities[$id]['selected_sha256'];
        $plan['galleries'][$gid] ??= ['before' => $master, 'after' => '/' . $new[0] . '/' . $new[1] . '/' . $new . '.jpg', 'records' => [], 'entities' => []];
        $plan['galleries'][$gid]['records'][] = ['record_id' => (int)$row['record_id'], 'entity_id' => $id];
        $plan['galleries'][$gid]['entities'][$id] = false;
        $coverage[$id] = true;
    }
    if (count($coverage) !== count($changed)) { throw new RuntimeException('Missing gallery coverage for changed product'); }
    foreach ($db->query('SELECT value_id,entity_id FROM catalog_product_entity_media_gallery_value_to_entity') as $row) {
        if (isset($plan['galleries'][(int)$row['value_id']]['entities'][(int)$row['entity_id']])) {
            $plan['galleries'][(int)$row['value_id']]['entities'][(int)$row['entity_id']] = true;
        }
    }
    foreach ($plan['galleries'] as &$g) {
        if (in_array(false, $g['entities'], true)) { throw new RuntimeException('Missing gallery relationship'); }
        $g['entities'] = array_map('intval', array_keys($g['entities']));
    }
    unset($g);
    $plan['counts'] = ['changed_products' => count($changed), 'image_role_rows' => count($plan['roles']),
        'new_gallery_masters' => count($plan['galleries']), 'new_jpeg_files' => count($plan['images']),
        'source_jpeg_files_verified' => count($plan['source_files']), 'already_selected_products' => $already,
        'gallery_value_rows' => array_sum(array_map(fn($g) => count($g['records']), $plan['galleries'])),
        'gallery_relationships' => array_sum(array_map(fn($g) => count($g['entities']), $plan['galleries']))];
    return $plan;
}

function whiteLiveChange(PDO $db, array $plan, string $journal, bool $reverse = false, ?array $applied = null): array
{
    $newIds = $applied['new_gallery_ids'] ?? [];
    $db->beginTransaction();
    try {
        $insert = $db->prepare('INSERT INTO catalog_product_entity_media_gallery(attribute_id,value,media_type,disabled) VALUES(?,?,?,?)');
        $check = $db->prepare('SELECT * FROM catalog_product_entity_media_gallery WHERE value_id=?');
        if (!$reverse) {
            foreach ($plan['galleries'] as $old => $g) {
                $check->execute([$old]);
                if ($check->fetch(PDO::FETCH_ASSOC) != $g['before']) { throw new RuntimeException('Gallery master drift'); }
                $v = $g['before'];$insert->execute([$v['attribute_id'], $g['after'], $v['media_type'], $v['disabled']]);
                $newIds[$old] = (int)$db->lastInsertId();
            }
        }
        $intent = ['target' => $plan['target'], 'plan_sha256' => hash('sha256', json_encode($plan, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES)),
            'new_gallery_ids' => $newIds, 'reverse' => $reverse, 'committed' => false];
        whiteLiveWrite($journal, $intent);
        $role = $db->prepare('UPDATE catalog_product_entity_varchar SET value=? WHERE value_id=? AND entity_id=? AND attribute_id=? AND store_id=? AND value=?');
        foreach ($plan['roles'] as $row) {
            $role->execute([$reverse ? $row['before'] : $row['after'], $row['value_id'], $row['entity_id'], $row['attribute_id'], $row['store_id'], $reverse ? $row['after'] : $row['before']]);
            if ($role->rowCount() !== 1) { throw new RuntimeException('Image role drift; transaction rolled back'); }
        }
        $record = $db->prepare('UPDATE catalog_product_entity_media_gallery_value SET value_id=? WHERE record_id=? AND entity_id=? AND value_id=?');
        $link = $db->prepare('UPDATE catalog_product_entity_media_gallery_value_to_entity SET value_id=? WHERE value_id=? AND entity_id=?');
        foreach ($plan['galleries'] as $old => $g) {
            $from = $reverse ? $newIds[$old] : (int)$old; $to = $reverse ? (int)$old : $newIds[$old];
            foreach ($g['records'] as $r) {
                $record->execute([$to, $r['record_id'], $r['entity_id'], $from]);
                if ($record->rowCount() !== 1) { throw new RuntimeException('Gallery record drift'); }
            }
            foreach ($g['entities'] as $entity) {
                $link->execute([$to, $from, $entity]);
                if ($link->rowCount() !== 1) { throw new RuntimeException('Gallery relationship drift'); }
            }
        }
        $db->commit();
        $intent['committed'] = true;whiteLiveWrite($journal . '.committed.json', $intent);
        return $intent;
    } catch (Throwable $e) {
        if ($db->inTransaction()) { $db->rollBack(); }
        throw $e;
    }
}

function whiteLiveUnchanged(PDO $db, array $plan, array $newIds = []): array
{
    $roleIds = array_fill_keys(array_column($plan['roles'], 'value_id'), true);
    $recordIds = [];$links = [];
    foreach ($plan['galleries'] as $gid => $g) {
        foreach ($g['records'] as $r) { $recordIds[$r['record_id']] = true; }
        foreach ($g['entities'] as $eid) {
            $links[$gid . ':' . $eid] = true;
            if (isset($newIds[$gid])) { $links[$newIds[$gid] . ':' . $eid] = true; }
        }
    }
    $specs = [
        'products' => ['SELECT * FROM catalog_product_entity ORDER BY entity_id', null],
        'stock' => ['SELECT * FROM cataloginventory_stock_item ORDER BY item_id', null],
        'source_stock' => ['SELECT * FROM inventory_source_item ORDER BY source_item_id', null],
        'websites' => ['SELECT * FROM catalog_product_website ORDER BY product_id,website_id', null],
        'category_products' => ['SELECT * FROM catalog_category_product ORDER BY category_id,product_id', null],
        'product_links' => ['SELECT * FROM catalog_product_relation ORDER BY parent_id,child_id', null],
        'customers' => ['SELECT * FROM customer_entity ORDER BY entity_id', null],
        'orders' => ['SELECT * FROM sales_order ORDER BY entity_id', null],
        'other_varchar' => ['SELECT * FROM catalog_product_entity_varchar ORDER BY value_id', fn($r) => isset($roleIds[$r['value_id']])],
        'other_gallery_records' => ['SELECT * FROM catalog_product_entity_media_gallery_value ORDER BY record_id', fn($r) => isset($recordIds[$r['record_id']])],
        'original_gallery_masters' => ['SELECT * FROM catalog_product_entity_media_gallery WHERE value_id<=' . (int)$plan['max_gallery_id'] . ' ORDER BY value_id', null],
        'other_gallery_links' => ['SELECT * FROM catalog_product_entity_media_gallery_value_to_entity ORDER BY value_id,entity_id', fn($r) => isset($links[$r['value_id'] . ':' . $r['entity_id']])],
    ];
    foreach (['int', 'decimal', 'text', 'datetime'] as $type) {
        $specs['attributes_' . $type] = ['SELECT * FROM catalog_product_entity_' . $type . ' ORDER BY value_id', null];
    }
    $result = [];
    foreach ($specs as $name => [$sql, $skip]) {
        $hash = hash_init('sha256');$count = 0;
        foreach ($db->query($sql, PDO::FETCH_ASSOC) as $row) {
            if ($skip && $skip($row)) { continue; }
            hash_update($hash, json_encode($row, JSON_THROW_ON_ERROR) . "\n");$count++;
        }
        $result[$name] = ['rows' => $count, 'sha256' => hash_final($hash)];
    }
    return $result;
}

function whiteLiveMain(): void
{
    $a = getopt('', ['root:', 'packet:', 'packet-sha256:', 'plan:', 'plan-sha256:', 'directory:', 'action:']);
    $root = $a['root'];$directory = realpath($a['directory']);$action = $a['action'];
    if (!$directory || !str_starts_with($directory, $root . '/var/white-jpeg-') || (fileperms($directory) & 0077)) {
        throw new RuntimeException('A private Alpha var directory is required');
    }
    $db = whiteLiveContext($root);
    if ($action === 'inspect') {
        if (hash_file('sha256', $a['packet']) !== $a['packet-sha256']) { throw new RuntimeException('Packet checksum changed'); }
        $packet = json_decode(file_get_contents($a['packet']), true, 512, JSON_THROW_ON_ERROR);$packet['packet_sha256'] = $a['packet-sha256'];
        $db->exec('SET TRANSACTION READ ONLY');$db->beginTransaction();
        $plan = whiteLiveInspect($db, $root, $packet);$plan['unchanged_before'] = whiteLiveUnchanged($db, $plan);$db->rollBack();
        whiteLiveWrite($directory . '/plan.json', $plan);
        echo json_encode(['counts' => $plan['counts'], 'plan_sha256' => hash_file('sha256', $directory . '/plan.json')]) . "\n";
        return;
    }
    if (hash_file('sha256', $a['plan']) !== $a['plan-sha256']) { throw new RuntimeException('Plan checksum changed'); }
    $plan = json_decode(file_get_contents($a['plan']), true, 512, JSON_THROW_ON_ERROR);
    if ($action === 'apply') {
        if (!is_file($directory . '/backup-verified.json')) { throw new RuntimeException('Verified backup is required'); }
        foreach ($plan['images'] as $sha => $image) {
            if (hash_file('sha256', whiteLiveFile($root, $image['destination'])) !== $sha) { throw new RuntimeException('Staged JPEG checksum failed'); }
        }
        if (whiteLiveUnchanged($db, $plan) !== $plan['unchanged_before']) { throw new RuntimeException('Unrelated data drifted since inspection'); }
        if (is_file($directory . '/apply-intent.json')) { throw new RuntimeException('Existing apply intent requires inspection'); }
        $result = whiteLiveChange($db, $plan, $directory . '/apply-intent.json');
        whiteLiveWrite($directory . '/apply-result.json', $result);
        echo json_encode(['committed' => true, 'counts' => $plan['counts']]) . "\n";
    } elseif ($action === 'rollback') {
        $applied = json_decode(file_get_contents($directory . '/apply-intent.json.committed.json'), true, 512, JSON_THROW_ON_ERROR);
        whiteLiveChange($db, $plan, $directory . '/rollback-intent.json', true, $applied);
        echo "Rollback committed; new unreferenced JPEGs and gallery masters are retained.\n";
    } elseif ($action === 'verify') {
        $applied = json_decode(file_get_contents($directory . '/apply-intent.json.committed.json'), true, 512, JSON_THROW_ON_ERROR);
        $result = ['unchanged' => whiteLiveUnchanged($db, $plan, $applied['new_gallery_ids']), 'counts' => $plan['counts']];
        $result['unrelated_data_preserved'] = $result['unchanged'] === $plan['unchanged_before'];
        whiteLiveWrite($directory . '/preservation-after.json', $result);
        if (!$result['unrelated_data_preserved']) { throw new RuntimeException('Unrelated-data fingerprint differs'); }
        echo json_encode(['unrelated_data_preserved' => true, 'tables' => count($result['unchanged'])]) . "\n";
    } else { throw new RuntimeException('Unsupported action'); }
}

if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) { whiteLiveMain(); }
