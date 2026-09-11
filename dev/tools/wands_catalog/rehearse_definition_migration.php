<?php
declare(strict_types=1);

/** Database-only rehearsal. Deliberately cannot connect to a live database. */
function demand(bool $condition, string $message): void
{
    if (!$condition) {
        throw new RuntimeException($message);
    }
}
function ident(string $name): string
{
    demand((bool)preg_match('/^[a-zA-Z0-9_]+$/', $name), 'Invalid identifier');
    return '`' . $name . '`';
}
function canonical(array $rows): array
{
    $result = [];
    foreach ($rows as $row) {
        ksort($row);
        $result[] = json_encode(array_map(static fn($v) => $v === null ? null : (string)$v, $row), JSON_THROW_ON_ERROR);
    }
    sort($result);
    return $result;
}
function resolve(array $values, array $bindings): array
{
    foreach ($values as &$value) {
        if (is_string($value) && str_starts_with($value, '@')) {
            demand(array_key_exists(substr($value, 1), $bindings), 'Unresolved generated ID');
            $value = $bindings[substr($value, 1)];
        }
    }
    return $values;
}
function where(array $clauses): array
{
    $alternatives = []; $params = [];
    foreach ($clauses as $clause) {
        $parts = [];
        foreach ($clause as $column => $values) {
            $values = is_array($values) ? $values : [$values];
            demand(count($values) > 0 && !in_array(null, $values, true), 'Empty/null selector');
            $parts[] = ident($column) . ' IN (' . implode(',', array_fill(0, count($values), '?')) . ')';
            array_push($params, ...$values);
        }
        demand((bool)$parts, 'Unbounded selector');
        $alternatives[] = '(' . implode(' AND ', $parts) . ')';
    }
    demand((bool)$alternatives, 'Unbounded query');
    return [implode(' OR ', $alternatives), $params];
}
function rows(PDO $pdo, string $table, array $clauses): array
{
    [$filter, $params] = where($clauses);
    $s = $pdo->prepare('SELECT * FROM ' . ident($table) . ' WHERE ' . $filter);
    $s->execute($params);
    return $s->fetchAll(PDO::FETCH_ASSOC);
}
function matches(array $row, array $clauses): bool
{
    foreach ($clauses as $clause) {
        $yes = true;
        foreach ($clause as $key => $values) {
            if (!in_array((string)($row[$key] ?? ''), array_map('strval', is_array($values) ? $values : [$values]), true)) {
                $yes = false;
            }
        }
        if ($yes) { return true; }
    }
    return false;
}
function change(PDO $pdo, array $op, array &$bindings): array
{
    $table = $op['table']; $before = $op['before']; $after = $op['after'];
    if (!isset($op['generate'])) {
        $selector = resolve($op['selector'], $bindings);
        demand(canonical(rows($pdo, $table, [$selector])) === canonical($before === null ? [] : [$before]), 'Mutation precondition drift: ' . $table);
    } else {
        demand($table === 'eav_attribute_option' && $before === null && $op['generate'] === 'new_option', 'Invalid generated ID operation');
    }
    if ($after === null) {
        [$filter, $params] = where([$selector]);
        $s = $pdo->prepare('DELETE FROM ' . ident($table) . ' WHERE ' . $filter); $s->execute($params);
        demand($s->rowCount() === 1, 'Delete count mismatch');
    } elseif ($before === null) {
        $after = resolve($after, $bindings);
        $s = $pdo->prepare('INSERT INTO ' . ident($table) . ' (' . implode(',', array_map('ident', array_keys($after))) . ') VALUES (' . implode(',', array_fill(0, count($after), '?')) . ')');
        $s->execute(array_values($after));
        demand($s->rowCount() === 1, 'Insert count mismatch');
        if (isset($op['generate'])) {
            $bindings[$op['generate']] = $pdo->lastInsertId();
            $selector = resolve($op['selector'], $bindings);
        }
    } else {
        $after = resolve($after, $bindings);
        [$filter, $params] = where([$selector]);
        $s = $pdo->prepare('UPDATE ' . ident($table) . ' SET ' . implode(',', array_map(static fn($k) => ident($k) . '=?', array_keys($after))) . ' WHERE ' . $filter);
        $s->execute([...array_values($after), ...$params]);
        demand($s->rowCount() === 1, 'Update count mismatch');
    }
    $actual = rows($pdo, $table, [$selector]);
    demand(count($actual) === ($after === null ? 0 : 1), 'Unexpected post-write cardinality');
    if ($after !== null) {
        foreach ($after as $key => $value) {
            demand(array_key_exists($key, $actual[0]) && canonical([[$key => $value]]) === canonical([[$key => $actual[0][$key]]]), 'Unexpected post-write value: ' . $table . '.' . $key);
        }
    }
    return ['table' => $table, 'selector' => $selector, 'before' => $before, 'after' => $actual[0] ?? null];
}
function saveNew(string $path, array $data): void
{
    $f = fopen($path, 'x'); demand($f !== false, 'Receipt already exists'); chmod($path, 0600);
    $bytes = json_encode($data, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . PHP_EOL;
    demand(fwrite($f, $bytes) === strlen($bytes) && fflush($f) && fsync($f), 'Receipt durability failure');
    fclose($f);
}

$a = getopt('', ['plan:', 'plan-sha256:', 'sqlite:', 'action:', 'receipt:', 'fail-after:']);
$action = $a['action'] ?? 'dry-run';
$log = ($a['receipt'] ?? sys_get_temp_dir() . '/wands-rehearsal') . '.log';
try {
    demand(isset($a['plan'], $a['plan-sha256'], $a['receipt']), 'Plan, expected SHA and receipt required');
    demand(in_array($action, ['dry-run', 'apply', 'rollback'], true), 'Invalid action');
    demand(hash_file('sha256', $a['plan']) === $a['plan-sha256'], 'Plan hash mismatch');
    $plan = json_decode(file_get_contents($a['plan']), true, 512, JSON_THROW_ON_ERROR);
    demand($plan['version'] === 1 && $plan['environment'] === 'isolated_rehearsal_only' && $plan['publication_approved'] === false, 'Wrong plan boundary');
    demand(count($plan['operations']) === $plan['expected_operations'] && $plan['expected_operations'] === 105, 'Wrong approved count');
    demand(count($plan['approved_products']) === 17, 'Wrong product scope');
    if ($action !== 'rollback') {
        demand(time() - strtotime($plan['snapshot_captured_at']) <= 86400 && strtotime($plan['snapshot_captured_at']) <= time() + 360, 'Snapshot freshness failed');
    }
    if (isset($a['sqlite'])) {
        demand(is_file($a['sqlite']) && !is_link($a['sqlite']) && basename($a['sqlite']) === 'rehearsal.sqlite', 'Only an existing rehearsal fixture is accepted');
        $dsn = 'sqlite:' . realpath($a['sqlite']);
    } else {
        $dsn = (string)getenv('WANDS_REHEARSAL_DSN');
        demand((bool)preg_match('/^mysql:host=127\.0\.0\.1;port=[0-9]+;dbname=wands_rehearsal_[a-z0-9_]+;charset=utf8mb4$/', $dsn), 'Only loopback rehearsal database names are accepted');
    }
    $pdo = new PDO($dsn, 'root', (string)getenv('WANDS_REHEARSAL_PASSWORD'), [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_EMULATE_PREPARES => false]);
    if ($pdo->getAttribute(PDO::ATTR_DRIVER_NAME) === 'mysql') {
        $database = $pdo->query('SELECT DATABASE()')->fetchColumn();
        demand((bool)preg_match('/^wands_rehearsal_[a-z0-9_]+$/', $database), 'Unexpected database context');
        foreach (array_unique([...array_column($plan['guards'], 'table'), ...array_column($plan['operations'], 'table')]) as $table) {
            $s = $pdo->prepare('SELECT ENGINE FROM information_schema.tables WHERE TABLE_SCHEMA=? AND TABLE_NAME=?');
            $s->execute([$database, $table]);
            demand(strtolower((string)$s->fetchColumn()) === 'innodb', 'Missing or nontransactional rehearsal table');
        }
        $pdo->exec('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE');
        if ($action === 'dry-run') { $pdo->exec('SET TRANSACTION READ ONLY'); }
    }
    $pdo->beginTransaction();
    if ($action === 'rollback') {
        $receipt = json_decode(file_get_contents($a['receipt']), true, 512, JSON_THROW_ON_ERROR);
        demand($receipt['plan_sha256'] === $a['plan-sha256'] && $receipt['dsn_sha256'] === hash('sha256', $dsn), 'Receipt destination or plan mismatch');
        demand(is_file($a['receipt'] . '.committed') && !file_exists($a['receipt'] . '.rolled-back'), 'No committed receipt or already rolled back');
        $marker = json_decode(file_get_contents($a['receipt'] . '.committed'), true, 512, JSON_THROW_ON_ERROR);
        demand(($marker['receipt_sha256'] ?? '') === hash_file('sha256', $a['receipt']), 'Receipt changed after commit');
        foreach ($receipt['post_guards'] as $g) {
            demand(canonical(rows($pdo, $g['table'], $g['clauses'])) === canonical($g['rows']), 'Rollback drift: ' . $g['table']);
        }
        $newId = $receipt['bindings']['new_option'];
        $consumers = rows($pdo, 'catalog_product_entity_int', [['attribute_id' => $plan['new_option_attribute_id'], 'value' => $newId]]);
        $expectedConsumers = array_values(array_filter($receipt['operations'], static fn($op) => $op['table'] === 'catalog_product_entity_int' && (string)($op['after']['value'] ?? '') === (string)$newId && (string)($op['after']['attribute_id'] ?? '') === (string)$plan['new_option_attribute_id']));
        demand(canonical($consumers) === canonical(array_column($expectedConsumers, 'after')), 'New external option consumer; rollback refused');
        $labels = rows($pdo, 'eav_attribute_option_value', [['option_id' => $newId]]);
        $expectedLabels = array_values(array_filter($receipt['operations'], static fn($op) => $op['table'] === 'eav_attribute_option_value'));
        demand(canonical($labels) === canonical(array_column($expectedLabels, 'after')), 'New option label; rollback refused');
        foreach (array_reverse($receipt['operations']) as $op) {
            $bindings = [];
            change($pdo, ['table' => $op['table'], 'selector' => $op['selector'], 'before' => $op['after'], 'after' => $op['before']], $bindings);
        }
        foreach ($plan['guards'] as $g) {
            demand(canonical(rows($pdo, $g['table'], $g['clauses'])) === canonical($g['rows']), 'Inverse parity failed');
        }
        $pdo->commit(); saveNew($a['receipt'] . '.rolled-back', ['verified_before_parity' => true]);
    } else {
        demand(!file_exists($a['receipt']), 'Choose a fresh receipt');
        foreach ($plan['guards'] as $g) {
            demand(canonical(rows($pdo, $g['table'], $g['clauses'])) === canonical($g['rows']), 'Snapshot drift: ' . $g['table']);
        }
        if ($action === 'dry-run') {
            $pdo->rollBack(); saveNew($a['receipt'], ['action' => 'dry-run', 'writes' => 0, 'plan_sha256' => $a['plan-sha256']]);
        } else {
            $bindings = []; $applied = [];
            foreach ($plan['operations'] as $op) {
                $applied[] = change($pdo, $op, $bindings);
                demand((int)($a['fail-after'] ?? 0) !== count($applied), 'Injected rehearsal interruption');
            }
            $postGuards = [];
            foreach ($plan['guards'] as $g) {
                $expected = $g['rows'];
                foreach ($applied as $op) {
                    if ($op['table'] !== $g['table']) { continue; }
                    if ($op['before'] !== null) {
                        $expected = array_values(array_filter($expected, static fn($r) => canonical([$r]) !== canonical([$op['before']])));
                    }
                    if ($op['after'] !== null && matches($op['after'], $g['clauses'])) { $expected[] = $op['after']; }
                }
                $actual = rows($pdo, $g['table'], $g['clauses']);
                demand(canonical($expected) === canonical($actual), 'Unexpected collateral change: ' . $g['table']);
                $postGuards[] = [...$g, 'rows' => $actual];
            }
            saveNew($a['receipt'], ['version' => 1, 'plan_sha256' => $a['plan-sha256'], 'dsn_sha256' => hash('sha256', $dsn),
                'bindings' => $bindings, 'operations' => $applied, 'post_guards' => $postGuards, 'state' => 'prepared_before_commit']);
            $pdo->commit(); saveNew($a['receipt'] . '.committed', ['operations' => count($applied), 'receipt_sha256' => hash_file('sha256', $a['receipt']), 'database_only' => true]);
        }
    }
    file_put_contents($log, gmdate('c') . ' ' . $action . " completed in isolated rehearsal; no live execution\n", FILE_APPEND);
} catch (Throwable $error) {
    if (isset($pdo) && $pdo->inTransaction()) { $pdo->rollBack(); }
    // No connection exception messages, credentials or data values in the log.
    $message = $error instanceof PDOException ? 'Database exception; details suppressed' : $error->getMessage();
    file_put_contents($log, gmdate('c') . ' Stopped: ' . $message . "; inspect receipt markers before retrying\n", FILE_APPEND);
    exit(1);
}
