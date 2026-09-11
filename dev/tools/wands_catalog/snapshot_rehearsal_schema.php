<?php
declare(strict_types=1);

function isCatalogRehearsalTable(string $name): bool
{
    return (bool)preg_match('/^(catalog_|cataloginventory_|eav_|inventory_|store$|store_group$|store_website$|url_rewrite$)/', $name);
}
if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') !== __FILE__) { return; }

// Catalog-only SELECT/SHOW CREATE snapshot. Does not bootstrap Magento or export credentials.
$a = getopt('', ['root:', 'plan:', 'output:']);
try {
    $plan = json_decode(file_get_contents($a['plan']), true, 512, JSON_THROW_ON_ERROR);
    if ($plan['environment'] !== 'isolated_rehearsal_only' || count($plan['approved_products']) !== 17) {
        throw new RuntimeException('Wrong scope');
    }
    $env = require $a['root'] . '/app/etc/env.php'; $c = $env['db']['connection']['default'];
    $prefix = $env['db']['table_prefix'] ?? '';
    if ($prefix !== '') { throw new RuntimeException('Prefixed schema requires explicit adaptation'); }
    $quote = static function (string $name): string {
        if (!preg_match('/^[a-zA-Z0-9_]+$/', $name)) { throw new RuntimeException('Invalid identifier'); }
        return '`' . $name . '`';
    };
    $allowed = static function (string $name): void {
        if (!isCatalogRehearsalTable($name)) {
            throw new RuntimeException('Non-catalog dependency refused');
        }
    };
    $dsn = 'mysql:host=' . $c['host'] . ';dbname=' . $c['dbname'] . ';charset=utf8mb4';
    if (!empty($c['port'])) { $dsn .= ';port=' . (int)$c['port']; }
    $pdo = new PDO($dsn, $c['username'], $c['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    if ($pdo->query('SELECT DATABASE()')->fetchColumn() !== $c['dbname']) { throw new RuntimeException('Wrong database'); }
    $query = static function (string $sql, array $params = []) use ($pdo): array {
        $s = $pdo->prepare($sql); $s->execute($params); return $s->fetchAll(PDO::FETCH_ASSOC);
    };
    $pdo->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'); $pdo->exec('SET TRANSACTION READ ONLY'); $pdo->beginTransaction();
    $urls = $query('SELECT value FROM ' . $quote($c['dbname']) . '.core_config_data WHERE path IN (?,?)', ['web/secure/base_url','web/unsecure/base_url']);
    if (!in_array('relevance.comtom.lab', array_map(static fn($r) => parse_url($r['value'], PHP_URL_HOST), $urls), true)) { throw new RuntimeException('Wrong destination'); }
    $data = []; $ddl = []; $keys = []; $seen = [];
    $ensure = static function (string $table) use (&$ddl, &$keys, &$data, $allowed, $quote, $query, $c): void {
        $allowed($table);
        if (isset($ddl[$table])) { return; }
        $schema = $query('SHOW CREATE TABLE ' . $quote($c['dbname']) . '.' . $quote($table));
        $ddl[$table] = $schema[0]['Create Table']; $data[$table] = [];
        $keys[$table] = $query('SELECT CONSTRAINT_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=? AND TABLE_NAME=? AND REFERENCED_TABLE_NAME IS NOT NULL ORDER BY CONSTRAINT_NAME,ORDINAL_POSITION', [$c['dbname'],$table]);
    };
    $add = static function (string $table, array $row) use (&$data, &$seen, $plan): bool {
        if ($table === 'catalog_product_entity' && !in_array($row['sku'], $plan['approved_products'], true)) { throw new RuntimeException('Closure escaped seventeen products'); }
        $hash = hash('sha256', json_encode($row, JSON_THROW_ON_ERROR));
        if (isset($seen[$table][$hash])) { return false; }
        $seen[$table][$hash] = true; $data[$table][] = $row; return true;
    };
    $normalize = static function (array $rows): array {
        $out = []; foreach ($rows as $r) { ksort($r); $out[] = json_encode(array_map(static fn($v) => $v === null ? null : (string)$v, $r), JSON_THROW_ON_ERROR); } sort($out); return $out;
    };
    foreach ($plan['guards'] as $g) {
        $ensure($g['table']); $parts = []; $params = [];
        foreach ($g['clauses'] as $clause) {
            $and = []; foreach ($clause as $column => $values) {
                if (!$values) { throw new RuntimeException('Empty selector'); }
                $and[] = $quote($column) . ' IN (' . implode(',', array_fill(0,count($values),'?')) . ')'; array_push($params,...$values);
            }
            $parts[] = '(' . implode(' AND ', $and) . ')';
        }
        $rows = $query('SELECT * FROM ' . $quote($c['dbname']) . '.' . $quote($g['table']) . ' WHERE ' . implode(' OR ', $parts), $params);
        if ($normalize($rows) !== $normalize($g['rows'])) { throw new RuntimeException('Guard drift'); }
        foreach ($rows as $row) { $add($g['table'],$row); }
    }
    for ($pass = 0; $pass < 30; $pass++) {
        $changed = false;
        foreach (array_keys($ddl) as $table) {
            $grouped = [];
            foreach ($keys[$table] as $key) { $grouped[$key['CONSTRAINT_NAME']][] = $key; $ensure($key['REFERENCED_TABLE_NAME']); }
            foreach ($data[$table] as $row) {
                foreach ($grouped as $foreign) {
                    $parts = []; $values = []; $parent = $foreign[0]['REFERENCED_TABLE_NAME'];
                    foreach ($foreign as $key) {
                        if ($row[$key['COLUMN_NAME']] === null) { continue 2; }
                        $parts[] = $quote($key['REFERENCED_COLUMN_NAME']) . '=?'; $values[] = $row[$key['COLUMN_NAME']];
                    }
                    foreach ($query('SELECT * FROM ' . $quote($c['dbname']) . '.' . $quote($parent) . ' WHERE ' . implode(' AND ',$parts), $values) as $parentRow) {
                        $changed = $add($parent,$parentRow) || $changed;
                    }
                }
            }
        }
        if (array_sum(array_map('count',$data)) > 10000 || count($ddl) > 100) { throw new RuntimeException('Closure budget exceeded'); }
        if (!$changed) { break; }
    }
    if ($changed) { throw new RuntimeException('Closure did not converge'); }
    $version = $pdo->query('SELECT VERSION()')->fetchColumn(); $pdo->rollBack();
    $result = ['version'=>1,'host'=>'relevance.comtom.lab','captured_at'=>gmdate('c'),'consistent_read_only'=>true,'engine'=>$version,
        'plan_sha256'=>hash_file('sha256',$a['plan']),'collector_sha256'=>hash_file('sha256',__FILE__),'ddl'=>$ddl,'foreign_keys'=>$keys,'rows'=>$data,
        'exclusions'=>['No customers, orders, carts, credentials or non-catalog configuration','Triggers, routines and Magento runtime are not copied']];
    $f = fopen($a['output'],'x'); if (!$f) { throw new RuntimeException('Choose fresh output'); } chmod($a['output'],0600);
    fwrite($f,json_encode($result,JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR).PHP_EOL); fclose($f);
    file_put_contents($a['output'].'.log',gmdate('c')." Read-only schema and catalog closure captured\n");
} catch (Throwable $e) {
    if (isset($pdo) && $pdo->inTransaction()) { $pdo->rollBack(); }
    $reason = get_class($e) === RuntimeException::class ? $e->getMessage() : get_class($e);
    file_put_contents(($a['output'] ?? sys_get_temp_dir().'/wands-schema').'.log',gmdate('c').' Failed: '.$reason."; no catalog writes\n",FILE_APPEND); exit(1);
}
