<?php
declare(strict_types=1);

/** Exact WANDS media role/gallery changes with a conflict-checked inverse. */
final class ExpansionMedia
{
    private array $hashes = [];

    public function __construct(private PDO $db, private string $root, private string $prefix = '')
    {
        if (!preg_match('/^[a-zA-Z0-9_]*$/', $prefix)) {
            throw new RuntimeException('Invalid table prefix');
        }
    }

    private function table(string $name): string
    {
        return '`' . $this->prefix . $name . '`';
    }

    private function imageHash(string $name): string
    {
        if (!isset($this->hashes[$name])) {
            $root = realpath($this->root . '/pub/media/catalog/product');
            $path = realpath($this->root . '/pub/media/catalog/product' . $name);
            if (!$root || !$path || !str_starts_with($name, '/') || str_contains($name, '..')
                || !str_starts_with($path, $root . '/') || !is_file($path)) {
                throw new RuntimeException('Invalid or missing imported image');
            }
            $this->hashes[$name] = hash_file('sha256', $path);
        }
        return $this->hashes[$name];
    }

    public function inspect(array $assignments, int $expectedCount = 107688, array $excluded = [], array $quarantined = []): array
    {
        $excludedSkus = array_fill_keys($excluded, true);
        if (count($excludedSkus) !== count($excluded) || array_intersect_key($assignments, $excludedSkus)
            || count($assignments) + count($excluded) !== $expectedCount) {
            throw new RuntimeException('Incomplete accepted media assignments');
        }
        foreach ($excluded as $sku) {
            if (!str_starts_with($sku, 'WANDS-') || (str_starts_with($sku, 'WANDS-SYN-') && !in_array($sku, $quarantined, true))) {
                throw new RuntimeException('Only retained disabled records may be excluded');
            }
        }
        $entities = [];
        $sql = 'SELECT p.entity_id,p.sku,w.website_id,s.code FROM ' . $this->table('catalog_product_entity') . ' p JOIN '
            . $this->table('catalog_product_website') . ' w ON w.product_id=p.entity_id JOIN '
            . $this->table('store_website') . ' s ON s.website_id=w.website_id ORDER BY p.entity_id,w.website_id';
        $outside = [];
        foreach ($this->db->query($sql, PDO::FETCH_ASSOC) as $row) {
            if ($row['code'] === 'wands') {
                if (!str_starts_with($row['sku'], 'WANDS-')
                    || (!isset($assignments[$row['sku']]) && !isset($excludedSkus[$row['sku']]))) {
                    throw new RuntimeException('Unexpected WANDS media target');
                }
                $entities[(int)$row['entity_id']] = $row['sku'];
            } else {
                $outside[(int)$row['entity_id']] = true;
            }
        }
        if (count($entities) !== $expectedCount || array_intersect_key($entities, $outside)) {
            throw new RuntimeException('Missing or shared WANDS media target');
        }
        if ($excluded) {
            $disabled = [];
            $sql = 'SELECT v.entity_id,v.store_id,v.value FROM ' . $this->table('catalog_product_entity_int')
                . ' v JOIN ' . $this->table('eav_attribute') . " a ON a.attribute_id=v.attribute_id WHERE a.attribute_code='status'";
            foreach ($this->db->query($sql, PDO::FETCH_ASSOC) as $row) {
                $id = (int)$row['entity_id'];
                if (isset($entities[$id]) && isset($excludedSkus[$entities[$id]])) {
                    if ((int)$row['value'] !== 2) {
                        throw new RuntimeException('Excluded media target is enabled');
                    }
                    if ((int)$row['store_id'] === 0) { $disabled[$id] = true; }
                }
            }
            if (count($disabled) !== count($excluded)) {
                throw new RuntimeException('Missing disabled status for excluded media target');
            }
            $entities = array_diff_key($entities, $disabled);
        }
        $roles = [];
        $sql = 'SELECT v.value_id,v.entity_id,v.store_id,v.value,a.attribute_code FROM '
            . $this->table('catalog_product_entity_varchar') . ' v JOIN ' . $this->table('eav_attribute')
            . " a ON a.attribute_id=v.attribute_id WHERE a.attribute_code IN ('image','small_image','thumbnail') ORDER BY v.value_id";
        foreach ($this->db->query($sql, PDO::FETCH_ASSOC) as $row) {
            if (isset($entities[(int)$row['entity_id']])) {
                $roles[(int)$row['entity_id']][] = $row;
            }
        }
        $current = [];
        $operations = [];
        foreach ($entities as $id => $sku) {
            $defaults = [];
            foreach ($roles[$id] ?? [] as $row) {
                if ((int)$row['store_id'] === 0) {
                    $defaults[$row['attribute_code']] = $row;
                }
            }
            if (count($defaults) !== 3) {
                throw new RuntimeException('Missing default image roles: ' . $sku);
            }
            foreach ($defaults as $row) {
                if ($this->imageHash($row['value']) !== $assignments[$sku]['sha256']) {
                    throw new RuntimeException('Native imported bytes differ from accepted image: ' . $sku);
                }
            }
            $current[$id] = $defaults['image']['value'];
            foreach ($roles[$id] as $row) {
                $desired = $defaults[$row['attribute_code']]['value'];
                if ($row['value'] !== $desired) {
                    $operations[] = ['table' => 'catalog_product_entity_varchar', 'key' => 'value_id',
                        'id' => $row['value_id'], 'entity_id' => $id, 'column' => 'value',
                        'before' => $row['value'], 'after' => $desired];
                }
            }
        }
        $seen = [];
        $sql = 'SELECT v.record_id,v.entity_id,v.disabled,g.value FROM '
            . $this->table('catalog_product_entity_media_gallery_value') . ' v JOIN '
            . $this->table('catalog_product_entity_media_gallery') . ' g ON g.value_id=v.value_id ORDER BY v.record_id';
        foreach ($this->db->query($sql, PDO::FETCH_ASSOC) as $row) {
            $id = (int)$row['entity_id'];
            if (!isset($entities[$id])) {
                continue;
            }
            $desired = $row['value'] === $current[$id] ? 0 : 1;
            if ($desired === 0) {
                $seen[$id] = true;
            }
            if ((int)$row['disabled'] !== $desired) {
                $operations[] = ['table' => 'catalog_product_entity_media_gallery_value', 'key' => 'record_id',
                    'id' => $row['record_id'], 'entity_id' => $id, 'column' => 'disabled',
                    'before' => (string)$row['disabled'], 'after' => (string)$desired];
            }
        }
        if (count($seen) !== count($assignments)) {
            throw new RuntimeException('Accepted image absent from native gallery');
        }
        return ['verified_products' => count($entities), 'verified_default_roles' => count($entities) * 3,
            'excluded_disabled_skus' => $excluded, 'verified_unique_files' => count($this->hashes),
            'files_deleted' => 0, 'operations' => $operations];
    }

    public function change(array $operations, bool $reverse = false): void
    {
        if (!$this->db->inTransaction()) {
            throw new RuntimeException('Media changes require an enclosing transaction');
        }
        foreach ($reverse ? array_reverse($operations) : $operations as $op) {
            $valid = ($op['table'] === 'catalog_product_entity_varchar' && $op['key'] === 'value_id' && $op['column'] === 'value')
                || ($op['table'] === 'catalog_product_entity_media_gallery_value' && $op['key'] === 'record_id' && $op['column'] === 'disabled');
            if (!$valid) {
                throw new RuntimeException('Unapproved media operation');
            }
            $before = $reverse ? $op['after'] : $op['before'];
            $after = $reverse ? $op['before'] : $op['after'];
            $sql = 'UPDATE ' . $this->table($op['table']) . ' SET `' . $op['column'] . '`=? WHERE `'
                . $op['key'] . '`=? AND entity_id=? AND `' . $op['column'] . '`=?';
            $statement = $this->db->prepare($sql);
            $statement->execute([$after, $op['id'], $op['entity_id'], $before]);
            if ($statement->rowCount() !== 1) {
                throw new RuntimeException('Media row changed since inspection; transaction must roll back');
            }
        }
    }
}

function expansionMediaMain(): void
{
    $a = getopt('', ['root:', 'lineage:', 'quarantine:', 'quarantine-sha256:', 'action:', 'plan:', 'output:']);
    $root = realpath($a['root'] ?? '');
    $action = $a['action'] ?? 'inspect';
    if (!in_array($root, ['/Users/matt/code/mageos-latest', '/var/www/html'], true)
        || !in_array($action, ['inspect', 'apply', 'rollback'], true) || empty($a['output']) || file_exists($a['output'])) {
        throw new RuntimeException('Explicit approved target, action and fresh receipt required');
    }
    $lineage = json_decode(file_get_contents($a['lineage']), true, 512, JSON_THROW_ON_ERROR);
    $quarantined = [];
    if (!empty($a['quarantine'])) {
        $qpath = realpath($a['quarantine']);
        if (!$qpath || !str_starts_with($qpath, $root . '/var/') || hash_file('sha256', $qpath) !== ($a['quarantine-sha256'] ?? '')) {
            throw new RuntimeException('Pinned private quarantine receipt required');
        }
        $q = json_decode(file_get_contents($qpath), true, 512, JSON_THROW_ON_ERROR);
        if (($q['proposal_sha256'] ?? '') !== '27a78eca69ecd2b31b3d97983238d0aeb3b3aefb54d571fb3dbd7c041e72dd79'
            || count($q['entries'] ?? []) !== 213) { throw new RuntimeException('Unapproved quarantine scope'); }
        foreach ($q['entries'] as $entry) {
            if ($entry['product_online_proposed'] !== '2' || $entry['visibility_proposed'] !== 'Not Visible Individually'
                || $entry['sku'] === 'WANDS-SYN-S-KITCHEN-TABLETOP-02007') { throw new RuntimeException('Invalid quarantine fields'); }
            $quarantined[] = $entry['sku'];
        }
        if (count(array_unique($quarantined)) !== 213 || array_diff($quarantined, $lineage['excluded_disabled_skus'] ?? [])) {
            throw new RuntimeException('Quarantine differs from media exclusions');
        }
    }
    $env = require $root . '/app/etc/env.php';
    $c = $env['db']['connection']['default'];
    $dsn = 'mysql:host=' . $c['host'] . ';dbname=' . $c['dbname'] . ';charset=utf8mb4';
    if (!empty($c['port'])) {
        $dsn .= ';port=' . $c['port'];
    }
    $db = new PDO($dsn, $c['username'], $c['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $manager = new ExpansionMedia($db, $root, $env['db']['table_prefix'] ?? '');
    $db->exec('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE');
    if ($action === 'inspect') {
        $db->exec('SET TRANSACTION READ ONLY');
    }
    $db->beginTransaction();
    try {
        $receipt = ['schema' => 1, 'root' => $root, 'action' => $action, 'created_at' => gmdate('c'),
            'database' => $c['dbname'], 'prefix' => $env['db']['table_prefix'] ?? '',
            'quarantine_sha256' => $a['quarantine-sha256'] ?? null,
            'lineage_sha256' => hash_file('sha256', $a['lineage']), 'tool_sha256' => hash_file('sha256', __FILE__)];
        if ($action === 'inspect') {
            $receipt['inspection'] = $manager->inspect($lineage['assignments'], 107688, $lineage['excluded_disabled_skus'] ?? [], $quarantined);
        } else {
            $prior = json_decode(file_get_contents($a['plan']), true, 512, JSON_THROW_ON_ERROR);
            foreach (['root', 'database', 'prefix', 'lineage_sha256', 'tool_sha256', 'quarantine_sha256'] as $key) {
                if ($receipt[$key] !== $prior[$key]) {
                    throw new RuntimeException('Media plan identity changed');
                }
            }
            if ($action === 'apply') {
                if ($prior['action'] !== 'inspect' || time() - strtotime($prior['created_at']) > 3600) {
                    throw new RuntimeException('Fresh inspection required');
                }
                $current = $manager->inspect($lineage['assignments'], 107688, $lineage['excluded_disabled_skus'] ?? [], $quarantined);
                if ($current !== $prior['inspection']) {
                    throw new RuntimeException('Media changed after dry run');
                }
                $receipt['inspection'] = $current;
                $manager->change($current['operations']);
                $receipt['after'] = $manager->inspect($lineage['assignments'], 107688, $lineage['excluded_disabled_skus'] ?? [], $quarantined);
                if ($receipt['after']['operations']) {
                    throw new RuntimeException('Media apply did not reach intended state');
                }
            } else {
                if ($prior['action'] !== 'apply' || !is_file($a['plan'] . '.committed')
                    || trim(file_get_contents($a['plan'] . '.committed')) !== hash_file('sha256', $a['plan'])) {
                    throw new RuntimeException('Exact committed media journal required');
                }
                $manager->change($prior['inspection']['operations'], true);
                $receipt['restored_operations'] = count($prior['inspection']['operations']);
            }
        }
        $stream = fopen($a['output'], 'x');
        if (!$stream) {
            throw new RuntimeException('Cannot create private media receipt');
        }
        chmod($a['output'], 0600);
        $encoded = json_encode($receipt, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n";
        if (fwrite($stream, $encoded) !== strlen($encoded) || !fflush($stream) || !fsync($stream)) {
            throw new RuntimeException('Cannot persist media inverse before commit');
        }
        fclose($stream);
        if ($action === 'inspect') {
            $db->rollBack();
        } else {
            $db->commit();
            file_put_contents($a['output'] . '.committed', hash_file('sha256', $a['output']));
        }
        echo json_encode(['action' => $action, 'receipt' => $a['output'], 'files_deleted' => 0]) . "\n";
    } catch (Throwable $error) {
        if ($db->inTransaction()) {
            $db->rollBack();
        }
        throw $error;
    }
}

if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) {
    expansionMediaMain();
}
