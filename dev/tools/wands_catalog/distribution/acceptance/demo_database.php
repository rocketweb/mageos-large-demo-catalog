<?php
declare(strict_types=1);

// Exact internal demo backup/restore transport. Never publish its output.
$environment = require '/var/www/html/app/etc/env.php';
$connection = $environment['db']['connection']['default'];
if ($connection['dbname'] !== 'magento' || !is_dir('/var/www/html/var/catalog-enriched-20260913-v2')) {
    throw new RuntimeException('Wrong database destination');
}
$action = $argv[1] ?? '';
if (!in_array($action, ['backup', 'restore'], true)) { throw new RuntimeException('Choose backup or restore'); }
$command = [$action === 'backup' ? 'mysqldump' : 'mysql', '--host=' . $connection['host'],
    '--user=' . $connection['username']];
if (!empty($connection['port'])) { $command[] = '--port=' . $connection['port']; }
if ($action === 'backup') { array_push($command, '--single-transaction', '--routines', '--triggers'); }
$command[] = 'magento';
$process = proc_open($command, [STDIN, STDOUT, STDERR], $pipes, null,
    ['PATH' => getenv('PATH'), 'MYSQL_PWD' => $connection['password']]);
if (!is_resource($process)) { throw new RuntimeException('Database transport did not start'); }
exit(proc_close($process));
