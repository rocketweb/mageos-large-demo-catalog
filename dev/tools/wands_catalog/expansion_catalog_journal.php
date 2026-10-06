<?php
declare(strict_types=1);

/** Row snapshots and exact, conflict-checked compensation for native imports. */
final class ExpansionCatalogJournal
{
    public const TABLES = ['catalog_product_entity', 'catalog_product_entity_varchar',
        'catalog_product_entity_int', 'catalog_product_entity_text', 'catalog_product_entity_decimal',
        'catalog_product_entity_datetime', 'catalog_product_website', 'catalog_product_relation',
        'catalog_product_super_link', 'catalog_product_super_attribute', 'catalog_product_super_attribute_label',
        'catalog_product_bundle_option', 'catalog_product_bundle_option_value', 'catalog_product_bundle_selection',
        'catalog_product_bundle_selection_price', 'catalog_product_entity_media_gallery',
        'catalog_product_entity_media_gallery_value', 'catalog_product_entity_media_gallery_value_to_entity',
        'cataloginventory_stock_item', 'inventory_source_item', 'catalog_category_entity',
        'catalog_category_entity_varchar', 'catalog_category_entity_int', 'catalog_category_entity_text',
        'catalog_category_entity_decimal', 'catalog_category_entity_datetime', 'catalog_category_product',
        'eav_attribute', 'catalog_eav_attribute', 'eav_attribute_option', 'eav_attribute_option_value',
        'eav_entity_attribute', 'eav_attribute_group', 'patch_list', 'url_rewrite',
        'catalog_url_rewrite_product_category', 'catalog_product_entity_tier_price', 'catalog_product_entity_group_price',
        'catalog_product_link', 'catalog_product_link_attribute_int', 'catalog_product_link_attribute_decimal',
        'catalog_product_link_attribute_varchar', 'catalog_product_super_attribute_pricing',
        'catalog_product_option', 'catalog_product_option_title', 'catalog_product_option_price',
        'catalog_product_option_type_value', 'catalog_product_option_type_title', 'catalog_product_option_type_price',
        'downloadable_link', 'downloadable_link_title', 'downloadable_link_price',
        'downloadable_sample', 'downloadable_sample_title'];
    public const PROTECTED = ['core_config_data', 'customer_entity', 'sales_order', 'sales_order_item',
        'inventory_reservation', 'quote', 'quote_item', 'quote_item_option', 'quote_address',
        'wishlist', 'wishlist_item', 'wishlist_item_option'];

    public function __construct(private PDO $db, private string $prefix = '')
    {
        if (!preg_match('/^[a-zA-Z0-9_]*$/', $prefix)) { throw new RuntimeException('Invalid table prefix'); }
    }

    private function table(string $name): string
    {
        if (!in_array($name, self::TABLES, true)) { throw new RuntimeException('Table outside catalog scope'); }
        return '`' . $this->prefix . $name . '`';
    }

    public static function canonical(?array $row): ?array
    {
        if ($row === null) { return null; }
        ksort($row);
        return array_map(static fn($v) => $v === null ? null : (string)$v, $row);
    }

    public function validateOperation(array $op): void
    {
        $this->table($op['table']);
        if (!$op['selector'] || ($op['before'] === null && $op['after'] === null)) {
            throw new RuntimeException('Empty or unbounded inverse operation');
        }
        foreach ([$op['selector'], $op['before'] ?? [], $op['after'] ?? []] as $row) {
            foreach ($row as $column => $value) {
                if (!preg_match('/^[a-zA-Z0-9_]+$/', $column) || (!is_scalar($value) && $value !== null)) {
                    throw new RuntimeException('Invalid inverse row');
                }
            }
        }
        foreach ($op['selector'] as $column => $value) {
            foreach (['before', 'after'] as $side) {
                if ($op[$side] !== null && (!array_key_exists($column, $op[$side]) || (string)$op[$side][$column] !== (string)$value)) {
                    throw new RuntimeException('Inverse selector does not identify its row');
                }
            }
        }
    }

    public function current(array $op): ?array
    {
        $this->validateOperation($op);
        $where = implode(' AND ', array_map(static fn($c) => '`' . $c . '`=?', array_keys($op['selector'])));
        $q = $this->db->prepare('SELECT * FROM ' . $this->table($op['table']) . ' WHERE ' . $where);
        $q->execute(array_values($op['selector'])); $rows = $q->fetchAll(PDO::FETCH_ASSOC);
        if (count($rows) > 1) { throw new RuntimeException('Inverse selector is not unique'); }
        return self::canonical($rows[0] ?? null);
    }

    public function compensate(array $op): void
    {
        if (!$this->db->inTransaction()) { throw new RuntimeException('Transactional inverse required'); }
        if ($this->current($op) !== self::canonical($op['after'])) {
            throw new RuntimeException('Catalog changed after the captured import; inverse aborted');
        }
        $where = implode(' AND ', array_map(static fn($c) => '`' . $c . '`=?', array_keys($op['selector'])));
        if ($op['before'] === null) {
            $sql = 'DELETE FROM ' . $this->table($op['table']) . ' WHERE ' . $where;
            $values = array_values($op['selector']);
        } elseif ($op['after'] === null) {
            $sql = 'INSERT INTO ' . $this->table($op['table']) . ' (`' . implode('`,`', array_keys($op['before']))
                . '`) VALUES (' . implode(',', array_fill(0, count($op['before']), '?')) . ')';
            $values = array_values($op['before']);
        } else {
            $sql = 'UPDATE ' . $this->table($op['table']) . ' SET '
                . implode(',', array_map(static fn($c) => '`' . $c . '`=?', array_keys($op['before']))) . ' WHERE ' . $where;
            $values = [...array_values($op['before']), ...array_values($op['selector'])];
        }
        $this->db->prepare($sql)->execute($values);
        if ($this->current($op) !== self::canonical($op['before'])) { throw new RuntimeException('Inverse verification failed'); }
    }

    public function protectedHashes(bool $lock = false): array
    {
        $result = [];
        foreach (self::PROTECTED as $name) {
            $q = $this->db->prepare('SELECT ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=?');
            $q->execute([$this->prefix . $name]);
            if ($q->fetchColumn() === false) { continue; }
            $hash = hash_init('sha256'); $count = 0;
            foreach ($this->db->query('SELECT * FROM `' . $this->prefix . $name . '` ORDER BY 1' . ($lock ? ' FOR UPDATE' : ''), PDO::FETCH_ASSOC) as $row) {
                hash_update($hash, json_encode($row, JSON_THROW_ON_ERROR) . "\n"); ++$count;
            }
            $result[$name] = ['rows' => $count, 'sha256' => hash_final($hash)];
        }
        return $result;
    }

    public function capture(string $directory): array
    {
        // Snapshot complete catalog tables so later compensation can be formed
        // from a row diff. Rows that did not change never enter the inverse.
        if (file_exists($directory) || !mkdir($directory, 0700, true)) { throw new RuntimeException('Fresh private journal directory required'); }
        $tables = [];
        foreach (self::TABLES as $name) {
            $q = $this->db->prepare('SELECT ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=?');
            $q->execute([$this->prefix . $name]); $engine = $q->fetchColumn();
            if ($engine === false) { continue; }
            if (strtolower($engine) !== 'innodb') { throw new RuntimeException('Nontransactional catalog table'); }
            $columns = $this->db->query('SHOW COLUMNS FROM ' . $this->table($name))->fetchAll(PDO::FETCH_ASSOC);
            $keys = array_column(array_filter($columns, static fn($r) => $r['Key'] === 'PRI'), 'Field');
            if (!$keys) { throw new RuntimeException('Catalog journal needs a stable primary key'); }
            $file = $directory . '/' . $name . '.jsonl.gz'; $stream = gzopen($file, 'wb6'); chmod($file, 0600);
            if (!$stream) { throw new RuntimeException('Cannot open private catalog snapshot'); }
            $hash = hash_init('sha256'); $count = 0;
            $q = $this->db->query('SELECT * FROM ' . $this->table($name) . ' ORDER BY `' . implode('`,`', $keys) . '`');
            while ($row = $q->fetch(PDO::FETCH_ASSOC)) {
                $row = self::canonical($row);
                $line = json_encode(['selector' => array_intersect_key($row, array_flip($keys)), 'row' => $row],
                    JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . "\n";
                if (gzwrite($stream, $line) !== strlen($line)) { throw new RuntimeException('Catalog snapshot write failed'); }
                hash_update($hash, $line); ++$count;
            }
            gzclose($stream);
            $tables[$name] = ['rows' => $count, 'row_sha256' => hash_final($hash), 'sha256' => hash_file('sha256', $file),
                'keys' => $keys, 'columns' => $columns];
        }
        return ['tables' => $tables, 'protected' => $this->protectedHashes(), 'database_writes' => false];
    }
}

function expansionCatalogJournalMain(): void
{
    $a = getopt('', ['root:', 'output:']); $root = realpath($a['root'] ?? '');
    if (!in_array($root, ['/Users/matt/code/mageos-latest', '/var/www/html'], true)) { throw new RuntimeException('Wrong existing installation'); }
    $parent = realpath(dirname($a['output'] ?? ''));
    if (!$parent || !str_starts_with($parent, $root . '/var/') || (fileperms($parent) & 0077)) { throw new RuntimeException('Private installation var directory required'); }
    $env = require $root . '/app/etc/env.php'; $c = $env['db']['connection']['default'];
    $dsn = 'mysql:host=' . $c['host'] . ';dbname=' . $c['dbname'] . ';charset=utf8mb4';
    if (!empty($c['port'])) { $dsn .= ';port=' . (int)$c['port']; }
    $db = new PDO($dsn, $c['username'], $c['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $db->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'); $db->exec('SET TRANSACTION READ ONLY'); $db->beginTransaction();
    try {
        $result = (new ExpansionCatalogJournal($db, $env['db']['table_prefix'] ?? ''))->capture($a['output']);
        $db->rollBack();
        $result += ['root' => $root, 'prefix' => $env['db']['table_prefix'] ?? '', 'database' => $c['dbname'],
            'env_sha256' => hash_file('sha256', $root . '/app/etc/env.php'),
            'created_at' => gmdate('c'), 'tool_sha256' => hash_file('sha256', __FILE__)];
        file_put_contents($a['output'] . '/manifest.json', json_encode($result, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n");
        chmod($a['output'] . '/manifest.json', 0600);
        echo json_encode(['root' => $root, 'tables' => count($result['tables']), 'database_writes' => false]) . "\n";
    } catch (Throwable $e) { if ($db->inTransaction()) { $db->rollBack(); } throw $e; }
}

if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) { expansionCatalogJournalMain(); }
