<?php
declare(strict_types=1);

$secrets = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
require '/var/www/html/app/bootstrap.php';
$arguments = ['command'=>'setup:install', '--base-url'=>'http://127.0.0.1:18037/',
    '--db-host'=>'db', '--db-name'=>'lab_recipient', '--db-user'=>'lab_catalog',
    '--db-password'=>$secrets['LAB_DB_PASSWORD'], '--admin-firstname'=>'Lab',
    '--admin-lastname'=>'Operator', '--admin-email'=>'lab@example.test',
    '--admin-user'=>'labadmin', '--admin-password'=>$secrets['LAB_ADMIN_PASSWORD'],
    '--language'=>'en_US', '--currency'=>'USD', '--timezone'=>'America/Indiana/Indianapolis',
    '--use-rewrites'=>'1', '--search-engine'=>'opensearch', '--opensearch-host'=>'search',
    '--opensearch-port'=>'9200', '--opensearch-index-prefix'=>'wands_recipient',
    '--backend-frontname'=>'labadmin'];
$application = new \Magento\Framework\Console\Cli('Magento CLI');
exit($application->run(new \Symfony\Component\Console\Input\ArrayInput($arguments)));
