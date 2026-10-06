<?php
declare(strict_types=1);

// Read-only database transport for the two approved existing installations.
// Backup bytes contain private store data and must never be served or printed.
function qaDatabaseBackup(): void
{
    $a = getopt('', ['root:', 'output:']);
    $root = realpath($a['root'] ?? '');
    if (!in_array($root, ['/Users/matt/code/mageos-latest', '/var/www/html'], true)) {
        throw new RuntimeException('Only the two existing installations are supported');
    }
    $directory = realpath(dirname($a['output'] ?? ''));
    if (!$directory || !str_starts_with($directory, $root . '/var/')
        || (fileperms($directory) & 0077) || file_exists($a['output'])
        || !str_ends_with($a['output'], '.sql.gz')) {
        throw new RuntimeException('Choose a new SQL backup inside a private installation var directory');
    }
    $env = require $root . '/app/etc/env.php';
    $c = $env['db']['connection']['default'];
    $prefix = $env['db']['table_prefix'] ?? '';
    if (!preg_match('/^[a-zA-Z0-9_]*$/', $prefix) || !preg_match('/^[a-zA-Z0-9_]+$/', $c['dbname'])) {
        throw new RuntimeException('Unsupported database identity');
    }
    $dsn = 'mysql:host=' . $c['host'] . ';dbname=' . $c['dbname'] . ';charset=utf8mb4';
    if (!empty($c['port'])) { $dsn .= ';port=' . (int)$c['port']; }
    $db = new PDO($dsn, $c['username'], $c['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $count = (int)$db->query('SELECT COUNT(*) FROM `' . $prefix . 'catalog_product_website` p JOIN `'
        . $prefix . "store_website` w ON w.website_id=p.website_id WHERE w.code='wands'")->fetchColumn();
    if ($count !== 107688) { throw new RuntimeException('The completed WANDS destination changed'); }
    $client = ['mysqldump', '--no-defaults'];
    $host = $c['host']; $port = $c['port'] ?? null;
    if ($root !== '/var/www/html') {
        // This is the existing local database, not a newly provisioned runtime.
        $docker = '/usr/local/bin/docker';
        $process = proc_open([$docker, 'inspect', '--format', '{{json .NetworkSettings.Ports}}',
            'mageos-latest-mysql'], [['pipe', 'r'], ['pipe', 'w'], ['pipe', 'w']], $pipes);
        if (!is_resource($process)) { throw new RuntimeException('Cannot inspect the existing database runtime'); }
        fclose($pipes[0]); $ports = stream_get_contents($pipes[1]); fclose($pipes[1]);
        stream_get_contents($pipes[2]); fclose($pipes[2]);
        if (proc_close($process) !== 0) { throw new RuntimeException('Existing database runtime unavailable'); }
        $bindings = json_decode($ports, true, 512, JSON_THROW_ON_ERROR)['3306/tcp'] ?? [];
        $match = false;
        foreach ($bindings as $binding) {
            $match = $match || $host === '127.0.0.1:' . $binding['HostPort']
                || ($host === '127.0.0.1' && (string)$port === $binding['HostPort']);
        }
        if (!$match) { throw new RuntimeException('Local database port does not match the existing runtime'); }
        $client = [$docker, 'exec', '--env', 'MYSQL_PWD', 'mageos-latest-mysql', ...$client];
        $host = '127.0.0.1'; $port = 3306;
    }
    array_push($client, '--host=' . $host, '--user=' . $c['username'], '--single-transaction',
        '--quick', '--hex-blob', '--no-tablespaces', '--routines', '--triggers');
    if ($port) { $client[] = '--port=' . (int)$port; }
    $client[] = $c['dbname'];
    $previousMask = umask(0077);
    $output = fopen($a['output'], 'x');
    if (!$output) { throw new RuntimeException('Cannot reserve the private backup'); }
    fclose($output); chmod($a['output'], 0600);
    $gzip = gzopen($a['output'], 'wb6');
    $error = fopen($a['output'] . '.errors', 'x');
    if (!$gzip || !$error) { throw new RuntimeException('Cannot create private backup streams'); }
    $process = proc_open($client, [['pipe', 'r'], ['pipe', 'w'], $error], $pipes, null,
        ['PATH' => getenv('PATH'), 'MYSQL_PWD' => $c['password']]);
    if (!is_resource($process)) { throw new RuntimeException('Database backup did not start'); }
    fclose($pipes[0]); $bytes = 0;
    while (!feof($pipes[1])) {
        $data = fread($pipes[1], 1048576);
        if ($data === false || gzwrite($gzip, $data) !== strlen($data)) {
            throw new RuntimeException('Private backup write failed');
        }
        $bytes += strlen($data);
    }
    fclose($pipes[1]); gzclose($gzip); fclose($error); $exit = proc_close($process); umask($previousMask);
    if ($exit !== 0 || $bytes < 1000000) {
        throw new RuntimeException('Backup failed; inspect the private error artifact');
    }
    $receipt = ['root' => $root, 'created_at' => gmdate('c'), 'path' => $a['output'],
        'sha256' => hash_file('sha256', $a['output']), 'bytes' => filesize($a['output']),
        'uncompressed_bytes' => $bytes, 'wands_products' => $count, 'database_writes' => false,
        'tool_sha256' => hash_file('sha256', __FILE__)];
    file_put_contents($a['output'] . '.json', json_encode($receipt, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n");
    chmod($a['output'] . '.json', 0600);
    echo json_encode($receipt, JSON_THROW_ON_ERROR) . "\n";
}

if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) { qaDatabaseBackup(); }
